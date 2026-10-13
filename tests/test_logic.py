import asyncio
import logging

from redis.asyncio import BlockingConnectionPool, Redis

from battle_engine.logic import process_battle, resolve_battle
from battle_engine.models import BattleRequest, BattleRequestReady, Player


def test_process_battle_base():
    p1 = Player(name="Joe", defense=30, attack=70)
    p2 = Player(name="Jane", defense=50, attack=90)
    req = BattleRequestReady(
        initiator_id="",
        initiator=p1,
        opponent_id="",
        opponent=p2,
    )
    result = process_battle(req)
    print("\n")
    for l in result.report:
        print(l)
    assert result.winner == p2


def test_process_battle_base_equals():
    p1 = Player(name="Joe", defense=70, attack=80)
    p2 = Player(name="Jane", defense=70, attack=90)
    req = BattleRequestReady(
        initiator_id="",
        initiator=p1,
        opponent_id="",
        opponent=p2,
    )
    result = process_battle(req)
    print("\n")
    for l in result.report:
        print(l)
    assert result.winner == p1


def test_resources_stolen():
    p1 = Player(name="Joe", defense=70, attack=80, gold=100, silver=100)
    p2 = Player(name="Jane", defense=70, attack=90, gold=100, silver=100)
    req = BattleRequestReady(
        initiator_id="",
        initiator=p1,
        opponent_id="",
        opponent=p2,
    )
    result = process_battle(req)

    assert result.winner is p1
    assert p2.silver < p1.silver


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

    async def make_battle():
        assert p1.pk is not None and p2.pk is not None
        async with Redis(connection_pool=redis_pool) as r:
            return await resolve_battle(
                r,
                BattleRequest(
                    initiator_id=p1.pk,
                    opponent_id=p2.pk,
                ),
                wait_for=asyncio.sleep(0.05),
            )

    rs = await asyncio.gather(*(make_battle() for _ in range(3)))

    assert any(r.num_lock_attempts > 1 for r in rs)
