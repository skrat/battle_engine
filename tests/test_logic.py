import asyncio
import logging

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from battle_engine.logic import process_battle, resolve_battle
from battle_engine.models import BattleRequest, BattleRequestReady, Player


def test_process_battle_base():
    p1 = Player(name="Joe", defense=30, attack=70)
    p2 = Player(name="Jane", defense=50, attack=90)
    req = BattleRequestReady(
        initiator_id=0,
        initiator=p1,
        opponent_id=0,
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
        initiator_id=0,
        initiator=p1,
        opponent_id=0,
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
        initiator_id=0,
        initiator=p1,
        opponent_id=0,
        opponent=p2,
    )
    result = process_battle(req)

    assert result.winner is p1
    assert p2.silver < p1.silver


async def test_concurrent_battles_dont_overlap_players(
    db_sessionmaker: async_sessionmaker[AsyncSession], caplog
):
    caplog.set_level(logging.DEBUG, logger="battle_engine.logic")
    p1 = Player(name="Joe", defense=70, attack=80, gold=100, silver=100)
    p2 = Player(name="Jane", defense=70, attack=90, gold=100, silver=100)
    async with db_sessionmaker() as session:
        session.add(p1)
        session.add(p2)
        await session.commit()
        await session.refresh(p1)
        await session.refresh(p2)

    async def make_battle():
        assert p1.id is not None and p2.id is not None
        async with db_sessionmaker() as session:
            return await resolve_battle(
                session,
                BattleRequest(
                    initiator_id=p1.id,
                    opponent_id=p2.id,
                ),
                wait_for=asyncio.sleep(0.01),
            )

    rs = await asyncio.gather(*(make_battle() for _ in range(3)))

    attempts_max = max(*(r.num_lock_attempts for r in rs))
    assert attempts_max > 1
