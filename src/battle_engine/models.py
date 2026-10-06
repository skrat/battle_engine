import enum
from typing import Annotated, Any, cast

from annotated_types import Ge, Le
from pydantic import StringConstraints
from sqlmodel import Field, Relationship, SQLModel, UniqueConstraint, func, select
from sqlmodel.ext.asyncio.session import AsyncSession


class Player(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: Annotated[str, StringConstraints(max_length=20)] = Field(index=True)
    description: Annotated[str, StringConstraints(max_length=1000)] = ""
    gold: Annotated[int, Ge(0), Le(1_000_000_000)] = 100
    silver: Annotated[int, Ge(0), Le(1_000_000_000)] = 300
    attack: Annotated[int, Ge(0)] = 70
    defense: Annotated[int, Ge(0)] = 70
    hit_points: Annotated[int, Ge(0)] = 100

    __table_args__ = (UniqueConstraint("name"),)

    @classmethod
    async def count_all(cls, db: AsyncSession) -> int:
        stmt = select(func.count(cast(Any, Player.id)))
        return (await db.exec(stmt)).one()


class BattleStatus(str, enum.Enum):
    NEW = "new"
    DONE = "done"


class BattleRequest(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    status: BattleStatus = BattleStatus.NEW
    initiator_id: int = Field(foreign_key="player.id")
    initiator: Player = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": lambda: BattleRequest.initiator_id == Player.id
        }
    )
    opponent_id: int = Field(foreign_key="player.id")
    opponent: Player = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": lambda: BattleRequest.opponent_id == Player.id
        }
    )
