from collections.abc import Callable
from typing import Annotated, Any, cast

from annotated_types import Ge, Le
from pydantic import BaseModel, StringConstraints
from sqlalchemy.dialects.postgresql import Insert as pg_Insert
from sqlalchemy.dialects.postgresql import insert as pg_upsert
from sqlalchemy.dialects.sqlite import Insert as sqlite_Insert
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
from sqlalchemy.sql._typing import _DMLTableArgument
from sqlmodel import (
    Field,
    Relationship,
    SQLModel,
    UniqueConstraint,
    desc,
    func,
    select,
)
from sqlmodel.ext.asyncio.session import AsyncSession

from .settings import settings

upsert: Callable[[_DMLTableArgument], sqlite_Insert | pg_Insert]

match settings.DB_URL:
    case s if s.startswith("sqlite"):
        upsert = sqlite_upsert
    case s if s.startswith("postgres"):
        upsert = pg_upsert
    case _:
        raise ValueError(f"No UPSERT for DB: {settings.DB_URL}")


class PlayerCreate(BaseModel):
    """Base player model."""

    name: Annotated[str, StringConstraints(max_length=20)] = Field(index=True)
    description: Annotated[str, StringConstraints(max_length=1000)] = ""
    gold: Annotated[int, Ge(0), Le(1_000_000_000)] = 100
    silver: Annotated[int, Ge(0), Le(1_000_000_000)] = 300
    attack: Annotated[int, Ge(0)] = 70
    defense: Annotated[int, Ge(0)] = 70
    hit_points: Annotated[int, Ge(0)] = 100


class Player(PlayerCreate, SQLModel, table=True):
    """Extends base player model with DB ID and a locking field.
    Locking field is used to ensure no more than one battle is processed
    at a time, involving the same player."""

    id: int | None = Field(default=None, primary_key=True)

    # Trade off: lock user for battle using DB
    battle_lock: bool = False

    __table_args__ = (UniqueConstraint("name"),)

    @classmethod
    async def count_all(cls, db: AsyncSession) -> int:
        stmt = select(func.count(cast(Any, Player.id)))
        return (await db.exec(stmt)).one()

    @classmethod
    async def exists(cls, db: AsyncSession, id: int) -> int:
        stmt = select(func.count(cast(Any, Player.id))).where(Player.id == id)
        return (await db.exec(stmt)).one() == 1


class BattleRequest(BaseModel):
    """For submission to battle engine."""

    initiator_id: int
    opponent_id: int


class BattleRequestReady(BattleRequest):
    """For submission to battle engine. Filled with player data."""

    initiator: Player
    opponent: Player


class BattleResult(BaseModel):
    """Battle engine output model."""

    winner: Player
    stolen: tuple[int, int]
    report: list[str]


class BattleResultStats(BattleResult):
    num_lock_attempts: int = 1


class LeaderboardEntry(SQLModel, table=True):
    """Entry in the leaderboard. Only one per player is allowed to exist."""

    id: int | None = Field(default=None, primary_key=True)
    player_id: int = Field(foreign_key="player.id")
    player: Player = Relationship(sa_relationship_kwargs={"lazy": "joined"})
    score: Annotated[int, Ge(0)] = 0

    __table_args__ = (UniqueConstraint("player_id", name="unique_player_id"),)

    @classmethod
    async def ranked(cls, db: AsyncSession):
        """Ordered leaderboard entries, by player's score."""
        stmt = select(LeaderboardEntry).order_by(desc("score"))
        return (await db.exec(stmt)).all()

    @classmethod
    async def update(cls, db: AsyncSession, pid: int, score: int):
        """UPSERT operation to insert, or add to an existing leaderboard entry."""
        ins_stmt = upsert(LeaderboardEntry).values(player_id=pid, score=score)
        ups_stmt = ins_stmt.on_conflict_do_update(
            index_elements=["player_id"],
            set_={"score": LeaderboardEntry.score + score},
        )
        await db.exec(ups_stmt)
        await db.commit()


class LeaderboardPlayer(BaseModel):
    """Public API schema."""

    id: int
    name: str


class LeaderboardEntryPublic(BaseModel):
    """Public API schema."""

    rank: int
    score: int
    player: LeaderboardPlayer
