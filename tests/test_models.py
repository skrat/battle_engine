import asyncio
import itertools

import pytest
from redis.asyncio import Redis

from battle_engine.models import Leaderboard, Player


async def test_player_name_unique(redis: Redis):
    # Conflicting names, separate instance, sequential
    p1 = Player(name="one")
    p2 = Player(name="one")
    await p1.create(redis)
    with pytest.raises(Player.NameExists):
        await p2.create(redis)
    assert len([p async for p in await Player.all_pks()]) == 1

    # Concurrent
    p3 = Player(name="two")
    result = await asyncio.gather(
        *[p3.create(redis) for _ in range(10)], return_exceptions=True
    )
    key = lambda x: isinstance(x, Player.NameExists)
    srt = sorted(result, key=key)
    groups = {k: list(g) for k, g in itertools.groupby(srt, key=key)}
    assert len(groups[True]) == 9  # Exceptions
    assert len(groups[False]) == 1  # Successes


async def test_leaderboard_updates(redis: Redis):
    p1 = Player(name="one")
    await p1.create(redis)
    assert p1.pk is not None

    total = await Leaderboard.update(redis, p1.pk, 100)
    assert total == 100

    lb = await Leaderboard.ranked(redis)
    assert len(lb) == 1
    assert lb[0].rank == 1
    assert lb[0].score == 100
    assert lb[0].player == p1.pk

    p2 = Player(name="two")
    await p2.create(redis)
    assert p2.pk is not None
    await Leaderboard.update(redis, p2.pk, 200)
    total = await Leaderboard.update(redis, p1.pk, 200)
    assert total == 300

    lb = await Leaderboard.ranked(redis)
    assert len(lb) == 2
    assert lb[0].rank == 1
    assert lb[0].score == 300
    assert lb[0].player == p1.pk
    assert lb[1].player == p2.pk
