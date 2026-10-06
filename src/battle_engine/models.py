from typing import Annotated, Any, cast

from annotated_types import Ge, Le
from pydantic import StringConstraints
from sqlmodel import Field, SQLModel, UniqueConstraint, func, select
from sqlmodel.ext.asyncio.session import AsyncSession


class Player(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: Annotated[str, StringConstraints(max_length=20)]
    description: Annotated[str, StringConstraints(max_length=1000)] = ""
    gold: Annotated[int, Ge(0), Le(1_000_000_000)] = 0
    silver: Annotated[int, Ge(0), Le(1_000_000_000)] = 0
    attack: Annotated[int, Ge(0)] = 0
    defense: Annotated[int, Ge(0)] = 0
    hit_points: Annotated[int, Ge(0)] = 0

    __table_args__ = (UniqueConstraint("name"),)

    @classmethod
    async def count_all(cls, db: AsyncSession) -> int:
        stmt = select(func.count(cast(Any, Player.id)))
        return (await db.exec(stmt)).one()
