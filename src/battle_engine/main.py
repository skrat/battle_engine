import asyncio
import logging
import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from battle_engine.logic import process_battle

from .db import get_engine, init_models
from .models import BattleRequest, Player

load_dotenv()
log = logging.getLogger("app")


def db_engine():
    db_url = os.getenv("DB_URL")
    if db_url is None:
        raise RuntimeError("Missing DB_URL")
    yield get_engine(db_url)


async def db_session(db_engine: AsyncEngine = Depends(db_engine)):
    await init_models(db_engine)
    async with AsyncSession(db_engine) as session:
        yield session


app = FastAPI()


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


async def get_free_player(db: AsyncSession, id: int):
    return (
        await db.exec(
            select(Player).where(Player.id == id).where(Player.battle_lock == False)
        )
    ).one_or_none()


@app.post("/battle/{initiator_id}/{opponent_id}")
async def request_battle(
    *, db: AsyncSession = Depends(db_session), initiator_id: int, opponent_id: int
):
    try:
        clean = BattleRequest(initiator_id=initiator_id, opponent_id=opponent_id)
        db.add(clean)
        await db.commit()
        await db.refresh(clean)
        await db.commit()
        async with db.begin():  # tx
            p1 = await get_free_player(db, initiator_id)
            p2 = await get_free_player(db, opponent_id)
            while p1 is None or p2 is None:
                await asyncio.sleep(1 / 30)
                p1 = await get_free_player(db, initiator_id)
                p2 = await get_free_player(db, opponent_id)
            await db.exec(
                update(Player)
                .where(Player.id.in_([initiator_id, opponent_id]))
                .values(battle_lock=True)
            )
            clean.initiator = p1
            clean.opponent = p2
            _, report = process_battle(clean)
            await db.exec(
                update(Player)
                .where(Player.id.in_([initiator_id, opponent_id]))
                .values(battle_lock=False)
            )
        return {**clean.model_dump(), "report": report}
    except ValidationError as ex:
        raise RequestValidationError([ex.json()])
    except IntegrityError as ex:
        # Player's not found
        raise RequestValidationError([*ex.detail])
