import asyncio
import logging

from redis.asyncio import Redis

from battle_engine.backend.redis.impl import RedisBackend
from battle_engine.models import BattleRequest, PlayerBase


async def test_concurrent_battles_dont_overlap_players(
    redis: Redis, redis_service: str, caplog
):
    caplog.set_level(logging.DEBUG, logger="battle_engine.logic")
    p1 = PlayerBase(name="Joe", defense=70, attack=80, gold=100, silver=100)
    p2 = PlayerBase(name="Jane", defense=70, attack=90, gold=100, silver=100)

    backend = RedisBackend()

    p1_id, p2_id = [
        p.id
        for p in await asyncio.gather(
            backend.create_player(p1),
            backend.create_player(p2),
        )
    ]

    async def make_battle():
        return await backend.resolve_battle(
            BattleRequest(
                initiator_id=p1_id,
                opponent_id=p2_id,
            ),
            _wait_for=asyncio.sleep(0.05),
        )

    rs = await asyncio.gather(*(make_battle() for _ in range(3)))

    assert any(r.num_lock_attempts > 1 for r in rs)
