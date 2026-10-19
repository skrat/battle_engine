from typing import ClassVar

from aredis_om import HashModel
from redis.asyncio import Redis
from redis.asyncio.client import Pipeline

from ...models import LeaderboardEntry, PlayerBase, PlayerNameExists


class Player(PlayerBase, HashModel, index=True):
    """Extends base player model with DB ID and a locking field.
    Locking field is used to ensure no more than one battle is processed
    at a time, involving the same player."""

    NAME_SET: ClassVar[str] = "player:name"
    LOCK_KEY: ClassVar[str] = "player:lock:{id}"

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
            raise PlayerNameExists(self.name)

    def to_args(self) -> list:
        doc = self.model_dump()
        flat: list = []
        for k, v in doc.items():
            if v is None:
                continue
            if isinstance(v, bool):
                v = "1" if v else "0"
            flat += [k, v]
        return flat


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
