from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from redis.asyncio import Redis
from taskiq import AsyncTaskiqTask

from battle_engine.db import make_blocking_pool

from .logic import resolve_battle
from .models import (
    REDIS,
    BattleRequest,
    BattleResult,
    BattleResultStats,
    Leaderboard,
    LeaderboardEntry,
    Player,
    PlayerCreate,
)
from .security import Protected
from .settings import settings
from .tasks import broker, process_battle_task


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    # Init Redis pool and client
    app.state.redis_pool = make_blocking_pool()
    app.state.redis = Redis(connection_pool=app.state.redis_pool)
    # Optionallyt init Taskiq broker
    if settings.WITH_TASKIQ and not broker.is_worker_process:
        await broker.startup()

    yield

    # Deinit taskiq
    if settings.WITH_TASKIQ and not broker.is_worker_process:
        await broker.shutdown()
    # Deinit Redis
    await app.state.redis_pool.disconnect()


async def get_redis(request: Request):
    r = request.app.state.redis
    with REDIS.set(r):
        yield r


RedisDep = Annotated[Redis, Depends(get_redis)]

app = FastAPI(
    title="Battle Engine",
    version="1.0",
    swagger_ui_parameters={
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "filter": True,
    },
    lifespan=app_lifespan,
)


@app.post("/player", response_model=Player)
async def create_player(*, _: Protected, r: RedisDep, player: PlayerCreate) -> Player:
    """Create player endpoint."""
    try:
        clean = Player.model_validate(player)
        await clean.create(r)
        return clean
    except Player.NameExists:
        raise RequestValidationError(["name"])
    except ValidationError as ex:
        raise RequestValidationError(ex.errors())


@app.post("/battle/{initiator_id}/{opponent_id}", response_model=BattleResult)
async def request_battle(
    *, _: Protected, r: RedisDep, initiator_id: str, opponent_id: str
):
    """Submit battle endpoint. Battles are processed inside the request handler to
    ensure immediate processing. This also satisfies spec. conditions:
    - Handle battles in the order they are submitted.
    """
    if initiator_id == opponent_id:
        raise RequestValidationError(["self-battle not allowed"])

    req = BattleRequest(
        initiator_id=initiator_id,
        opponent_id=opponent_id,
    )
    result = await resolve_battle(r, req)

    return JSONResponse(
        result.model_dump(exclude={"num_lock_attempts": True}),
        headers=settings.STAT_HEADER_FLAG
        and {
            settings.STAT_HEADER: str(result.num_lock_attempts),
        }
        or {},
    )


@app.post("/battle_defer/{initiator_id}/{opponent_id}")
async def request_battle_defer(
    *, _: Protected, r: RedisDep, initiator_id: str, opponent_id: str
):
    """Same as /battle but uses taskiq and a Redis broker."""
    if initiator_id == opponent_id:
        raise RequestValidationError(["self-battle not allowed"])

    task: AsyncTaskiqTask = await process_battle_task.kiq(  # pyright: ignore[reportCallIssue]
        initiator_id,
        opponent_id,
    )
    task_result = await task.wait_result(
        timeout=settings.BATTLE_LOCK_TTL,
    )
    if task_result.error is not None:
        raise task_result.error

    result = BattleResultStats(**task_result.return_value)

    return JSONResponse(
        result.model_dump(exclude={"num_lock_attempts": True}),
        headers=settings.STAT_HEADER_FLAG
        and {
            settings.STAT_HEADER: str(result.num_lock_attempts),
        }
        or {},
    )


@app.get("/leaderboard")
async def leaderboard(*, _: Protected, r: RedisDep) -> list[LeaderboardEntry]:
    """Retrieve sorted leaderboard."""
    return await Leaderboard.ranked(r)


def start():
    """Launched with `uv run server` at root level"""
    import uvicorn

    uvicorn.run(
        "battle_engine.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
