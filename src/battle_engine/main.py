import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from .db import get_engine, init_models
from .models import BattleRequest, Player

load_dotenv()
log = logging.getLogger(__name__)


def db_engine():
    yield get_engine(os.getenv("DB_URL") or "sqlite+aiosqlite:///db.sqlite3")


async def db_session(db_engine: AsyncEngine = Depends(db_engine)):
    async with AsyncSession(db_engine) as session:
        yield session


@asynccontextmanager
async def lifespan(app: FastAPI, db_engine: AsyncEngine = Depends(get_engine)):
    await init_models(db_engine)
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.post("/player", response_model=Player)
async def create_player(
    *, db: AsyncSession = Depends(db_session), player: Player
) -> Player:
    try:
        clean = Player.model_validate(player)
        db.add(clean)
        await db.commit()
        await db.refresh(clean)
        return clean
    except IntegrityError:
        log.exception("Invalid player")
        raise RequestValidationError(["name"])
    except ValidationError as ex:
        log.exception("Invalid player")
        raise RequestValidationError([ex.json()])


@app.post("/battle/{initiator_id}/{opponent_id}")
async def request_battle(
    *, db: AsyncSession = Depends(db_session), initiator_id: int, opponent_id: int
) -> BattleRequest:
    try:
        clean = BattleRequest(initiator_id=initiator_id, opponent_id=opponent_id)
        db.add(clean)
        await db.commit()
        await db.refresh(clean)
        return clean
    except ValidationError as ex:
        log.exception("Invalid battle request")
        raise RequestValidationError([ex.json()])
    except IntegrityError as ex:
        # Player's not found
        log.exception("Invalid battle request")
        raise RequestValidationError([*ex.detail])
