from typing import Annotated, ClassVar

from annotated_types import Ge, Le
from aredis_om import HashModel
from pydantic import BaseModel, StringConstraints
from redis.asyncio import Redis
from redis.asyncio.client import Pipeline

from .db import REDIS


class PlayerCreate(BaseModel):
    """Base player model."""

    name: Annotated[str, StringConstraints(max_length=20)]
    description: Annotated[str, StringConstraints(max_length=1000)] = ""
    gold: Annotated[int, Ge(0), Le(1_000_000_000)] = 100
    silver: Annotated[int, Ge(0), Le(1_000_000_000)] = 300
    attack: Annotated[int, Ge(0)] = 70
    defense: Annotated[int, Ge(0)] = 70
    hit_points: Annotated[int, Ge(0)] = 100


class Player(PlayerCreate, HashModel, index=True):
    """Extends base player model with DB ID and a locking field.
    Locking field is used to ensure no more than one battle is processed
    at a time, involving the same player."""

    class NameExists(ValueError):
        def __init__(self, name: str) -> None:
            super().__init__(f"Player with name '{name}' exists")

    NAME_SET: ClassVar[str] = "player:name"
    LOCK_KEY: ClassVar[str] = "player:lock:{id}"

    @classmethod
    def db(cls):
        return REDIS.get()

    @classmethod
    def rehydrate(cls, pk: str, doc: dict):
        """Similar to Player.get. It works because we only have int & str fields."""
        return Player.model_validate(
            {
                **dict(zip(doc[::2], doc[1::2])),
                "pk": pk,
            }
        )

    async def create(self, r: Redis):
        async def tx(pipe: Pipeline):
            exists = await r.sismember(self.NAME_SET, self.name)
            if exists:
                return
            pipe.multi()
            pipe.sadd(self.NAME_SET, self.name)
            await self.save(pipeline=pipe)

        result = await r.transaction(tx, self.NAME_SET)
        if not len(result):
            raise self.NameExists(self.name)


class BattleRequest(BaseModel):
    """For submission to battle engine."""

    initiator_id: str
    opponent_id: str


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


class LeaderboardEntry(BaseModel):
    """Public API schema."""

    rank: int
    score: int
    player: str


class Leaderboard:
    """Leaderboard implemented using Redis sorted set."""

    PLAYER_SET: ClassVar[str] = "player:score"

    @classmethod
    async def ranked(cls, r: Redis[str]) -> list[LeaderboardEntry]:
        """Ordered leaderboard entries, by player's score."""
        xs = await r.zrevrange(cls.PLAYER_SET, 0, 100, withscores=True)
        return [
            LeaderboardEntry(
                rank=i + 1,
                score=int(score),
                player=player,
            )
            for i, (player, score) in enumerate(xs)
        ]

    @classmethod
    async def update(cls, r: Redis, player_id: str, score: int):
        return await r.zincrby(cls.PLAYER_SET, score, player_id)
