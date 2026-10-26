import asyncio

import pytest
from sqlmodel import select

from battle_engine.backend.sqlalchemy.impl import SQLBackend
from battle_engine.backend.sqlalchemy.models import Player
from battle_engine.models import BattleRequest, PlayerBase


async def test_concurrent_battles_dont_overlap_players(backend_sql: SQLBackend):
    backend = backend_sql
    p1 = PlayerBase(name="Joe", defense=70, attack=80, gold=100, silver=100)
    p2 = PlayerBase(name="Jane", defense=70, attack=90, gold=100, silver=100)

    p1_id, p2_id = [
        p.id
        for p in await asyncio.gather(
            backend.create_player(p1),
            backend.create_player(p2),
        )
    ]

    async def make_battle(wait: float):
        result = await backend.resolve_battle(
            BattleRequest(
                initiator_id=p1_id,
                opponent_id=p2_id,
            ),
            _wait_for=asyncio.create_task(asyncio.sleep(wait)),
        )
        return result

    rs = await asyncio.gather(*(make_battle(0.02) for _ in range(3)))
    assert any(r.num_lock_attempts > 1 for r in rs)

    with pytest.raises(RuntimeError):
        await asyncio.gather(*(make_battle(0.05) for _ in range(3)))


async def test_battle_updates_player(backend_sql: SQLBackend):
    backend = backend_sql
    p1 = PlayerBase(name="Joe", defense=70, attack=90, gold=100, silver=100)
    p2 = PlayerBase(name="Jane", defense=70, attack=60, gold=100, silver=100)

    p1_id, p2_id = [
        p.id
        for p in await asyncio.gather(
            backend.create_player(p1),
            backend.create_player(p2),
        )
    ]

    await backend.resolve_battle(
        BattleRequest(
            initiator_id=p1_id,
            opponent_id=p2_id,
        )
    )

    async with backend.sessionmaker() as sess:
        stmt = select(Player).where(Player.id == p2_id)
        looser = (await sess.exec(stmt)).one()
        assert looser.gold < 100 and looser.silver < 100
