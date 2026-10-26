from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from taskiq import AsyncTaskiqTask

from .backend.shared import Backend, get_backend_impl
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
from .settings import settings
from .tasks import broker, process_battle_task


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    # Import and intialize the backend
    app.state.backend = get_backend_impl()

    # Optionally init Taskiq broker
    if settings.WITH_TASKIQ and not broker.is_worker_process:
        await broker.startup()

    async with app.state.backend.lifespan():
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


@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder({"detail": exc.errors()}),
    )


@app.exception_handler(PlayerNameExists)
async def player_name_exception_handler(request: Request, exc: PlayerNameExists):
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder(
            {
                "detail": [
                    {
                        "loc": ["body", "name"],
                        "msg": "player name exists",
                    }
                ]
            }
        ),
    )


@app.post("/player", response_model=PlayerFull)
async def create_player(
    *, _: Protected, backend: BackendDep, player: PlayerBase
) -> PlayerFull:
    """Create player endpoint."""
    return await backend.create_player(player)


def battle_result_response(result: BattleResultStats) -> JSONResponse:
    return JSONResponse(
        result.result.model_dump(),
        headers=settings.STAT_HEADER_FLAG
        and {
            settings.STAT_HEADER: str(result.num_lock_attempts),
        }
        or {},
    )


@app.post("/battle/{initiator_id}/{opponent_id}", response_model=BattleResult)
async def request_battle(
    *,
    _: Protected,
    backend: BackendDep,
    initiator_id: str,
    opponent_id: str,
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


if settings.WITH_TASKIQ:

    @app.post("/battle_defer/{initiator_id}/{opponent_id}", response_model=BattleResult)
    async def request_battle_defer(
        *,
        _: Protected,
        initiator_id: str,
        opponent_id: str,
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


if __name__ == "__main__":
    start()
