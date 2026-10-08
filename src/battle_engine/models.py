from typing import Annotated, Any, cast

from annotated_types import Ge, Le
from pydantic import BaseModel, StringConstraints
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
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


class PlayerCreate(BaseModel):
    name: Annotated[str, StringConstraints(max_length=20)] = Field(index=True)
    description: Annotated[str, StringConstraints(max_length=1000)] = ""
    gold: Annotated[int, Ge(0), Le(1_000_000_000)] = 100
    silver: Annotated[int, Ge(0), Le(1_000_000_000)] = 300
    attack: Annotated[int, Ge(0)] = 70
    defense: Annotated[int, Ge(0)] = 70
    hit_points: Annotated[int, Ge(0)] = 100


class Player(PlayerCreate, SQLModel, table=True):
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
    initiator_id: int
    opponent_id: int


class BattleRequestReady(BattleRequest):
    initiator: Player
    opponent: Player


class BattleResult(BaseModel):
    battle: BattleRequestReady
    winner: Player
    stolen: tuple[int, int]
    report: list[str]


class LeaderboardEntry(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    player_id: int = Field(foreign_key="player.id")
    player: Player = Relationship(sa_relationship_kwargs={"lazy": "joined"})
    score: Annotated[int, Ge(0)] = 0

    __table_args__ = (UniqueConstraint("player_id"),)

    @classmethod
    async def ranked(cls, db: AsyncSession):
        stmt = select(LeaderboardEntry).order_by(desc("score"))
        return (await db.exec(stmt)).all()

    @classmethod
    async def update(cls, db: AsyncSession, pid: int, score: int):
        ins_stmt = sqlite_upsert(LeaderboardEntry).values(player_id=pid, score=score)
        ups_stmt = ins_stmt.on_conflict_do_update(
            set_={"score": LeaderboardEntry.score + score}
        )
        await db.exec(ups_stmt)


class LeaderboardPlayer(BaseModel):
    id: int
    name: str


class LeaderboardEntryPublic(BaseModel):
    rank: int
    score: int
    player: LeaderboardPlayer
