import os
from contextlib import asynccontextmanager
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from .db import init_models
from .logic import resolve_battle
from .models import BattleRequest, Player

load_dotenv()


DB_URL = os.getenv("DB_URL")
if DB_URL is None:
    raise RuntimeError("Missing DB_URL")


engine = create_async_engine(DB_URL, echo=True)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def db_session():
    async with async_session() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(db_session)]


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    await init_models(engine)
    yield


app = FastAPI(lifespan=app_lifespan)


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.post("/player", response_model=Player)
async def create_player(*, db: SessionDep, player: Player) -> Player:
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
async def request_battle(*, db: SessionDep, initiator_id: int, opponent_id: int):
    """Submit battle endpoint. Battles are processed inside the request handler to
    facilitate immediate processing. This also satisfies spec. conditions:
    - Handle battles in the order they are submitted.
    - Handle battles in the order they are submitted.
    """
    try:
        req = BattleRequest(initiator_id=initiator_id, opponent_id=opponent_id)
        db.add(req)
        await db.commit()
        await db.refresh(req)
        result = await resolve_battle(db, req)
        return {
            "winner": result.winner.name,
            "report": result.report,
        }
    except ValidationError as ex:
        raise RequestValidationError([ex.json()])
    except IntegrityError as ex:
        # Player's not found
        raise RequestValidationError([*ex.detail])
