import enum
from typing import Annotated, Any, cast

from annotated_types import Ge, Le
from pydantic import StringConstraints
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.sql import text
from sqlmodel import (
    Field,
    Relationship,
    SQLModel,
    UniqueConstraint,
    func,
    select,
    update,
)
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

    # Trade off: lock user for battle using DB
    battle_lock: bool = False

    __table_args__ = (UniqueConstraint("name"),)

    @classmethod
    async def count_all(cls, db: AsyncSession) -> int:
        stmt = select(func.count(cast(Any, Player.id)))
        return (await db.exec(stmt)).one()

    @classmethod
    async def get(cls, db: AsyncSession, id: int) -> Player | None:
        try:
            return (await db.exec(select(Player).where(Player.id == id))).one()
        except NoResultFound:
            return None


class BattleStatus(str, enum.Enum):
    NEW = "NEW"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"


class BattleRequest(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    status: BattleStatus = BattleStatus.NEW
    initiator_id: int = Field(foreign_key="player.id")
    initiator: Player = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": lambda: BattleRequest.initiator_id == Player.id,
            "lazy": "joined",
        }
    )
    opponent_id: int = Field(foreign_key="player.id")
    opponent: Player = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": lambda: BattleRequest.opponent_id == Player.id,
            "lazy": "joined",
        }
    )

    @classmethod
    async def get(cls, db: AsyncSession, id: int) -> BattleRequest | None:
        try:
            return (
                await db.exec(select(BattleRequest).where(BattleRequest.id == id))
            ).one()
        except NoResultFound:
            return None

    @classmethod
    async def pop(cls, db: AsyncSession) -> BattleRequest | None:
        req_updt_stmt = text("""
        UPDATE battlerequest
            SET status=:new_status
            WHERE battlerequest.id IN (
                SELECT battlerequest.id
                    FROM battlerequest
                    JOIN player as p1 ON p1.id = battlerequest.initiator_id
                    JOIN player as p2 ON p2.id = battlerequest.opponent_id
                    WHERE
                        battlerequest.status = :where_status
                        AND
                        p1.battle_lock = FALSE
                        AND
                        p2.battle_lock = FALSE
                    ORDER BY battlerequest.id
                    LIMIT 1)
        RETURNING *
        """)
        async with db.bind.begin() as conn:
            res = await cast(AsyncConnection, conn).execute(
                req_updt_stmt,
                {
                    "new_status": BattleStatus.IN_PROGRESS,
                    "where_status": BattleStatus.NEW,
                },
            )
            try:
                m = res.one()._mapping
                updt_stmt = (
                    update(Player)
                    .where(Player.id.in_([m["initiator_id"], m["opponent_id"]]))  # pyright: ignore
                    .values(battle_lock=True)
                )
                await db.exec(updt_stmt)
                return BattleRequest(**m)
            except NoResultFound:
                return None

    async def release(self, db: AsyncSession):
        updt_stmt = (
            update(Player)
            .where(Player.id.in_([self.initiator_id, self.opponent_id]))  # pyright: ignore
            .values(battle_lock=False)
        )
        await db.exec(updt_stmt)
        updt_stmt = (
            update(BattleRequest)
            .where(BattleRequest.id == self.id)  # pyright: ignore
            .values(status=BattleStatus.DONE)
        )
        await db.exec(updt_stmt)


class BattleResult(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    battle_id: int = Field(foreign_key="battlerequest.id")
    battle: BattleRequest = Relationship()
