from typing import Annotated, ClassVar

from annotated_types import Ge, Le
from aredis_om import HashModel, NotFoundError
from pydantic import BaseModel, StringConstraints
from redis.asyncio import Redis
from redis.asyncio.client import Pipeline


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

    async def create(self, r: Redis):
        self.Meta.database = r

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

    @classmethod
    async def exists(cls, r: Redis, id: str) -> bool:
        try:
            await Player.get(id)
            return True
        except NotFoundError:
            return False


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


class LeaderboardPlayer(BaseModel):
    """Public API schema."""

    id: str
    name: str


class LeaderboardEntryPublic(BaseModel):
    """Public API schema."""

    rank: int
    score: int
    player: LeaderboardPlayer


class Leaderboard:
    """Entry in the leaderboard. Only one per player is allowed to exist."""

    PLAYER_SET: ClassVar[str] = "player:score"
    PLAYER_KEY: ClassVar[str] = "player:score:{id}"

    @classmethod
    async def ranked(cls, r: Redis) -> list[LeaderboardEntryPublic]:
        """Ordered leaderboard entries, by player's score."""
        players: list[str] = list(await r.smembers(cls.PLAYER_SET))
        scores = [
            int(await r.get(cls.PLAYER_KEY.format(id=pk)) or -1) for pk in players
        ]
        srted = sorted(
            zip(players, scores),
            key=lambda entry: entry[1],
            reverse=True,
        )
        result = []
        for i, (pk, score) in enumerate(srted):
            p = await Player.get(pk)
            assert p is not None
            result.append(
                LeaderboardEntryPublic(
                    rank=i + 1,
                    score=score,
                    player=LeaderboardPlayer(id=pk, name=p.name),
                )
            )
        return result

    @classmethod
    async def update(cls, r: Redis, player_pk: str, score: int):
        total = await r.incrby(cls.PLAYER_KEY.format(id=player_pk), score)
        await r.sadd(cls.PLAYER_SET, player_pk)
        return total
