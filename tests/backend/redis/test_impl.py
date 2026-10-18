import asyncio
import logging

from redis.asyncio import BlockingConnectionPool, Redis

from battle_engine.backend.redis.db import REDIS
from battle_engine.backend.redis.impl import RedisBackend
from battle_engine.backend.redis.models import Player
from battle_engine.models import BattleRequest


async def test_concurrent_battles_dont_overlap_players(
    redis: Redis, redis_pool: BlockingConnectionPool, caplog
):
    caplog.set_level(logging.DEBUG, logger="battle_engine.logic")
    p1 = Player(name="Joe", defense=70, attack=80, gold=100, silver=100)
    p2 = Player(name="Jane", defense=70, attack=90, gold=100, silver=100)

    await asyncio.gather(
        p1.create(redis),
        p2.create(redis),
    )

    backend = RedisBackend()

    async def make_battle():
        assert p1.pk is not None and p2.pk is not None
        async with Redis(connection_pool=redis_pool) as r:
            with REDIS.set(r):
                return await backend.resolve_battle(
                    BattleRequest(
                        initiator_id=p1.pk,
                        opponent_id=p2.pk,
                    ),
                    _wait_for=asyncio.sleep(0.05),
                )

    rs = await asyncio.gather(*(make_battle() for _ in range(3)))

    assert any(r.num_lock_attempts > 1 for r in rs)
