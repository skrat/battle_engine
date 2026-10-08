from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from .db import SessionDep, engine, init_models
from .logic import resolve_battle
from .models import (
    BattleRequest,
    LeaderboardEntry,
    LeaderboardEntryPublic,
    LeaderboardPlayer,
    Player,
    PlayerCreate,
)
from .security import Protected


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    await init_models(engine)
    yield


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
):
    """Submit battle endpoint. Battles are processed inside the request handler to
    facilitate immediate processing. This also satisfies spec. conditions:
    - Handle battles in the order they are submitted.
    - Handle battles in the order they are submitted.
    """
    try:
        if not (
            await Player.exists(db, initiator_id)
            and await Player.exists(db, opponent_id)
        ):
            raise HTTPException(404)
        req = BattleRequest(initiator_id=initiator_id, opponent_id=opponent_id)
        result = await resolve_battle(db, req)
        await LeaderboardEntry.update(db, result.winner.id, sum(result.stolen))
        return {
            "winner": result.winner.name,
            "report": result.report,
        }
    except ValidationError as ex:
        raise RequestValidationError([ex.json()])


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

    uvicorn.run("battle_engine.main:app", host="0.0.0.0", port=8000, reload=True)
