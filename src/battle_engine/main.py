from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from .db import SessionDep, engine, init_models
from .logic import resolve_battle
from .models import (
    BattleRequest,
    BattleResult,
    BattleResultStats,
    LeaderboardEntry,
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
    await init_models(engine)
    if settings.WITH_REDIS and not broker.is_worker_process:
        await broker.startup()
    yield
    if settings.WITH_REDIS and not broker.is_worker_process:
        await broker.shutdown()


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
async def create_player(
    *, _: Protected, db: SessionDep, player: PlayerCreate
) -> Player:
    """Create player endpoint."""
    try:
        clean = Player.model_validate(player)
        db.add(clean)
        await db.commit()
        await db.refresh(clean)
        return clean
    except IntegrityError:
        raise RequestValidationError(["name"])
    except ValidationError as ex:
        raise RequestValidationError(ex.errors())


@app.post("/battle/{initiator_id}/{opponent_id}")
async def request_battle(
    *, _: Protected, db: SessionDep, initiator_id: int, opponent_id: int
) -> BattleResult:
    """Submit battle endpoint. Battles are processed inside the request handler to
    ensure immediate processing. This also satisfies spec. conditions:
    - Handle battles in the order they are submitted.
    """
    try:
        if not (
            await Player.exists(db, initiator_id)
            and await Player.exists(db, opponent_id)
        ):
            raise HTTPException(404)
        req = BattleRequest(
            initiator_id=initiator_id,
            opponent_id=opponent_id,
        )
        result = await resolve_battle(db, req)
        await LeaderboardEntry.update(
            db,
            result.winner.id,
            sum(result.stolen),
        )
        return JSONResponse(
            result.model_dump(exclude=["num_lock_attempts"]),
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
    *, _: Protected, db: SessionDep, initiator_id: int, opponent_id: int
):
    """Same as /battle but uses taskiq and a Redis broker."""
    try:
        if not (
            await Player.exists(db, initiator_id)
            and await Player.exists(db, opponent_id)
        ):
            raise HTTPException(404)
        task = await process_battle_task.kiq(
            initiator_id,
            opponent_id,
        )
        task_result = await task.wait_result(timeout=1)
        result = BattleResultStats(**task_result.return_value)
        await LeaderboardEntry.update(
            db,
            result.winner.id,
            sum(result.stolen),
        )
        return JSONResponse(
            result.model_dump(exclude=["num_lock_attempts"]),
            headers=settings.STAT_HEADER_FLAG
            and {
                settings.STAT_HEADER: str(result.num_lock_attempts),
            }
            or {},
        )
    except ValidationError as ex:
        raise RequestValidationError(ex.errors())


@app.get("/leaderboard")
async def leaderboard(*, _: Protected, db: SessionDep) -> list[LeaderboardEntryPublic]:
    """Retrieve sorted leaderboard."""
    board = await LeaderboardEntry.ranked(db)
    return [
        LeaderboardEntryPublic(
            rank=i + 1,
            score=ent.score,
            player=LeaderboardPlayer(
                id=ent.player_id,
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
