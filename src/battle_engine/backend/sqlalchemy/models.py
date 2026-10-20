from collections.abc import Callable
from typing import Annotated

from annotated_types import Ge
from sqlalchemy.dialects.postgresql import Insert as pg_Insert
from sqlalchemy.dialects.postgresql import insert as pg_upsert
from sqlalchemy.dialects.sqlite import Insert as sqlite_Insert
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql._typing import _DMLTableArgument
from sqlmodel import (
    Field,
    Relationship,
    SQLModel,
    UniqueConstraint,
    desc,
    select,
)
from sqlmodel.ext.asyncio.session import AsyncSession

from ...models import PlayerBase, PlayerFull, PlayerNameExists
from .settings import settings

upsert: Callable[[_DMLTableArgument], sqlite_Insert | pg_Insert]

match settings.DB_URL:
    case s if s.startswith("sqlite"):
        upsert = sqlite_upsert
    case s if s.startswith("postgres"):
        upsert = pg_upsert
    case _:
        raise ValueError(f"No UPSERT for DB: {settings.DB_URL}")


class Player(PlayerBase, SQLModel, table=True):
    """Extends base player model with DB ID and a locking field.
    Locking field is used to ensure no more than one battle is processed
    at a time, involving the same player."""

    id: int | None = Field(default=None, primary_key=True)

    # Trade off: lock user for battle using DB
    battle_lock: bool = False

    __table_args__ = (UniqueConstraint("name"),)

    @classmethod
    async def create(cls, sess: AsyncSession, p: PlayerBase) -> PlayerFull:
        try:
            clean = Player.model_validate(p)
            sess.add(clean)
            await sess.commit()
            await sess.refresh(clean)
            return PlayerFull(
                id=str(clean.id),
                **clean.model_dump(exclude={"id"}),
            )
        except IntegrityError as e:
            raise PlayerNameExists(p.name) from e


class Leaderboard(SQLModel, table=True):
    """Entry in the leaderboard. Only one per player is allowed to exist."""

    id: int | None = Field(default=None, primary_key=True)
    player_id: int = Field(foreign_key="player.id")
    player: Player = Relationship(sa_relationship_kwargs={"lazy": "joined"})
    score: Annotated[int, Ge(0)] = 0

    __table_args__ = (UniqueConstraint("player_id", name="unique_player_id"),)

    @classmethod
    async def ranked(cls, sess: AsyncSession, limit=100):
        """Ordered leaderboard entries, by player's score."""
        stmt = select(Leaderboard).order_by(desc("score")).limit(limit)
        return (await sess.exec(stmt)).all()

    @classmethod
    async def update(cls, sess: AsyncSession, pid: int, score: int):
        """UPSERT operation to insert, or add to an existing leaderboard entry."""
        ins_stmt = upsert(Leaderboard).values(player_id=pid, score=score)
        ups_stmt = ins_stmt.on_conflict_do_update(
            index_elements=["player_id"],
            set_={"score": Leaderboard.score + score},
        ).returning(Leaderboard)
        await sess.exec(ups_stmt)
        await sess.commit()
