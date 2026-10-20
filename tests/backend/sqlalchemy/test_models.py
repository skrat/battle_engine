import asyncio
import itertools

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from battle_engine.backend.sqlalchemy.models import Leaderboard, Player
from battle_engine.models import PlayerBase, PlayerNameExists


async def test_player_name_unique(sql_sessionmaker: async_sessionmaker[AsyncSession]):
    # Conflicting names, separate instance, sequential
    p1 = PlayerBase(name="one")
    p2 = PlayerBase(name="one")
    async with sql_sessionmaker() as sess:
        await Player.create(sess, p1)
        with pytest.raises(PlayerNameExists):
            await Player.create(sess, p2)

    # Concurrent
    p3 = PlayerBase(name="two")

    async def make_player():
        async with sql_sessionmaker() as sess:
            return await Player.create(sess, p3)

    result = await asyncio.gather(
        *[make_player() for _ in range(10)],
        return_exceptions=True,
    )
    key = lambda x: isinstance(x, PlayerNameExists)
    srt = sorted(result, key=key)
    groups = {k: list(g) for k, g in itertools.groupby(srt, key=key)}
    assert len(groups[True]) == 9  # Exceptions
    assert len(groups[False]) == 1  # Successes


async def test_leaderboard_updates(sql_session: AsyncSession):
    sess = sql_session
    p1 = PlayerBase(name="one")
    p1_id = (await Player.create(sess, p1)).id

    await Leaderboard.update(sess, p1_id, 100)
    lb = await Leaderboard.ranked(sess)

    assert len(lb) == 1
    assert lb[0].score == 100
    assert str(lb[0].player_id) == p1_id

    p2 = PlayerBase(name="two")
    with pytest.raises(IntegrityError):
        await Leaderboard.update(sess, 123, 100)

    p2_id = (await Player.create(sess, p2)).id
    await Leaderboard.update(sess, p2_id, 200)

    lb = await Leaderboard.ranked(sess)

    assert len(lb) == 2
    assert lb[0].score == 200
    assert str(lb[0].player_id) == p2_id
