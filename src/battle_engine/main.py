from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from taskiq import AsyncTaskiqTask

from battle_engine.backend.shared import Backend, get_backend_impl
from battle_engine.settings import settings
from battle_engine.tasks import broker, process_battle_task

from .models import (
    BattleRequest,
    BattleResult,
    BattleResultStats,
    LeaderboardEntry,
    PlayerBase,
    PlayerFull,
    PlayerNameExists,
)
from .security import Protected


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    # Import and intialize the backend
    app.state.backend = get_backend_impl()

    # Optionally init Taskiq broker
    if settings.WITH_TASKIQ and not broker.is_worker_process:
        await broker.startup()

    async with app.state.backend.lifespan(app):
        yield

    # Deinit taskiq
    if settings.WITH_TASKIQ and not broker.is_worker_process:
        await broker.shutdown()


async def get_backend(request: Request):
    yield request.app.state.backend


BackendDep = Annotated[Backend, Depends(get_backend)]

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


@app.post("/player", response_model=PlayerFull)
async def create_player(
    *, _: Protected, backend: BackendDep, player: PlayerBase
) -> PlayerFull:
    """Create player endpoint."""
    try:
        return await backend.create_player(player)
    except PlayerNameExists:
        raise RequestValidationError(["name"])
    except ValidationError as ex:
        raise RequestValidationError(ex.errors())


def battle_result_response(result: BattleResultStats) -> JSONResponse:
    return JSONResponse(
        result.result.model_dump(),
        headers=settings.STAT_HEADER_FLAG
        and {
            settings.STAT_HEADER: str(result.num_lock_attempts),
        }
        or {},
    )


def self_battle_check(initiator_id: str, opponent_id: str):
    if initiator_id == opponent_id:
        raise RequestValidationError(["self-battle not allowed"])


@app.post("/battle/{initiator_id}/{opponent_id}", response_model=BattleResult)
async def request_battle(
    *,
    _: Protected,
    backend: BackendDep,
    initiator_id: str,
    opponent_id: str,
    _check: None = Depends(self_battle_check),
):
    """Submit battle endpoint. Battles are processed inside the request handler to
    ensure immediate processing. This also satisfies spec. conditions:
    - Handle battles in the order they are submitted.
    """

    req = BattleRequest(
        initiator_id=initiator_id,
        opponent_id=opponent_id,
    )
    return battle_result_response(
        await backend.resolve_battle(req),
    )


@app.post("/battle_defer/{initiator_id}/{opponent_id}", response_model=BattleResult)
async def request_battle_defer(
    *,
    _: Protected,
    initiator_id: str,
    opponent_id: str,
    _check: None = Depends(self_battle_check),
):
    """Same as /battle but uses taskiq and a Redis broker."""

    task: AsyncTaskiqTask = await process_battle_task.kiq(  # pyright: ignore[reportCallIssue]
        initiator_id,
        opponent_id,
    )
    task_result = await task.wait_result(
        timeout=5,
    )
    if task_result.error is not None:
        raise task_result.error

    return battle_result_response(
        BattleResultStats(**task_result.return_value),
    )


@app.get("/leaderboard")
async def leaderboard(*, _: Protected, backend: BackendDep) -> list[LeaderboardEntry]:
    """Retrieve sorted leaderboard."""
    return await backend.leaderboard()


def start():
    """Launched with `uv run server` at root level"""
    import uvicorn

    uvicorn.run(
        "battle_engine.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
