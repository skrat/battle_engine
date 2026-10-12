import asyncio
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from redis.asyncio import Redis

from battle_engine.db import make_blocking_pool

from .logic import resolve_battle
from .models import (
    BattleRequest,
    BattleResult,
    BattleResultStats,
    Leaderboard,
    LeaderboardEntryPublic,
    LeaderboardPlayer,
    Player,
    PlayerCreate,
)
from .security import Protected
from .settings import settings
from .tasks import broker, process_battle_task


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    app.state.redis = make_blocking_pool()
    if settings.WITH_TASKIQ and not broker.is_worker_process:
        await broker.startup()
    yield
    if settings.WITH_TASKIQ and not broker.is_worker_process:
        await broker.shutdown()
    await app.state.redis.disconnect()


async def get_redis(request: Request):
    async with Redis(connection_pool=request.app.state.redis) as r:
        Player.Meta.database = r
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
    try:
        ex = await asyncio.gather(
            Player.exists(r, initiator_id),
            Player.exists(r, opponent_id),
        )
        if not ex[0]:
            raise HTTPException(404, [f"{initiator_id} not found"])
        if not ex[1]:
            raise HTTPException(404, [f"{opponent_id} not found"])
        req = BattleRequest(
            initiator_id=initiator_id,
            opponent_id=opponent_id,
        )
        result = await resolve_battle(r, req)
        assert result.winner.pk is not None
        await Leaderboard.update(
            r,
            result.winner.pk,
            sum(result.stolen),
        )
        return JSONResponse(
            result.model_dump(exclude={"num_lock_attempts": True}),
            headers=settings.STAT_HEADER_FLAG
            and {
                settings.STAT_HEADER: str(result.num_lock_attempts),
            }
            or {},
        )
    except ValidationError as ex:
        raise RequestValidationError(ex.errors())


@app.post("/battle_defer/{initiator_id}/{opponent_id}")
async def request_battle_defer(
    *, _: Protected, r: RedisDep, initiator_id: str, opponent_id: str
):
    """Same as /battle but uses taskiq and a Redis broker."""
    try:
        if not (
            await Player.exists(r, initiator_id) and await Player.exists(r, opponent_id)
        ):
            raise HTTPException(404)
        task = await process_battle_task.kiq(  # pyright: ignore[reportCallIssue]
            initiator_id,
            opponent_id,
        )
        task_result = await task.wait_result(timeout=1)
        result = BattleResultStats(**task_result.return_value)
        assert result.winner.pk
        await Leaderboard.update(
            r,
            result.winner.pk,
            sum(result.stolen),
        )
        return JSONResponse(
            result.model_dump(exclude={"num_lock_attempts": True}),
            headers=settings.STAT_HEADER_FLAG
            and {
                settings.STAT_HEADER: str(result.num_lock_attempts),
            }
            or {},
        )
    except ValidationError as ex:
        raise RequestValidationError(ex.errors())


@app.get("/leaderboard")
async def leaderboard(*, _: Protected, r: RedisDep) -> list[LeaderboardEntryPublic]:
    """Retrieve sorted leaderboard."""
    board = await Leaderboard.ranked(r)
    return [
        LeaderboardEntryPublic(
            rank=i + 1,
            score=ent.score,
            player=LeaderboardPlayer(
                id=ent.player.id,
                name=ent.player.name,
            ),
        )
        for i, ent in enumerate(board)
    ]


def start():
    """Launched with `uv run server` at root level"""
    import uvicorn

    uvicorn.run(
        "battle_engine.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
