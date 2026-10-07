import asyncio
import random
from asyncio.queues import Queue
from typing import Any, cast

import pytest
from sqlalchemy.sql.expression import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from battle_engine import worker
from battle_engine.models import BattleRequest, BattleStatus, Player
from tests.util import cancel, make_battle, make_player


@pytest.mark.asyncio
async def test_read_battles(db_sessionmaker):
    n = 3
    async with db_sessionmaker() as sess:
        players = make_player(sess)
        for _ in range(n):
            await make_battle(sess, players)
    q = Queue(1000)
    r = asyncio.create_task(worker.read_battles(db_sessionmaker, q))
    await asyncio.sleep(6 / 30)
    assert q.qsize() == n
    await cancel(r)


@pytest.mark.asyncio
async def test_worker_processing(db_sessionmaker):
    battles: list[BattleRequest] = []
    async with db_sessionmaker() as db:
        players = make_player(db)
        for _ in range(100):
            battles.append(await make_battle(db, players))

    q = Queue(1000)
    r = asyncio.create_task(worker.read_battles(db_sessionmaker, q))
    await asyncio.sleep(1)
    assert q.qsize() == 100

    num_workers = 10
    workers = [
        asyncio.create_task(worker.worker(db_sessionmaker, q, i))
        for i in range(num_workers)
    ]

    await asyncio.sleep(1)
    assert q.qsize() == 0

    for b in battles:
        assert b.initiator.battle_lock == False
        assert b.opponent.battle_lock == False

    await cancel(r)
    await asyncio.gather(*[cancel(w) for w in workers])


async def print_db(db: AsyncSession):
    stmt = select(func.count(cast(Any, Player.id)))
    cnt = (await db.exec(stmt)).one()
    print(f"=== PLAYERS ({cnt})")
    for p in (await db.exec(select(Player))).all():
        print(f"id={p.id} - lock [{p.battle_lock and 'x' or ' '}]")

    stmt = select(func.count(cast(Any, BattleRequest.id)))
    cnt = (await db.exec(stmt)).one()
    print(f"=== BATTLES ({cnt})")
    for b in (await db.exec(select(BattleRequest))).all():
        print(f"id={b.id} - status = {b.status}")


@pytest.mark.asyncio
async def test_worker_concurrent_nonoverlapping(db_sessionmaker):
    players: list[Player] = []
    battles: list[BattleRequest] = []

    n_players = 20
    n_battles = 40

    async with db_sessionmaker() as db:
        pgen = make_player(db)
        for _ in range(n_players):
            players.append(await anext(pgen))
        for _ in range(n_battles):
            p1 = random.choice(players)
            p2 = p1
            while p1 is p2:
                p2 = random.choice(players)
            battles.append(await make_battle(db, pgen, p1, p2))

        stmt = select(func.count(cast(Any, BattleRequest.id)))
        cnt = (await db.exec(stmt)).one()
        assert cnt == n_battles
        await print_db(db)

    q = Queue(1000)
    r = asyncio.create_task(worker.read_battles(db_sessionmaker, q))

    await asyncio.sleep(1)
    assert q.qsize() == n_battles

    await cancel(r)
    return

    num_workers = 1
    workers = [
        asyncio.create_task(worker.worker(db_sessionmaker, q, i))
        for i in range(num_workers)
    ]

    await asyncio.sleep(3)
    assert q.qsize() == 0

    async with db_sessionmaker() as db:
        await print_db(db)

        for b in battles:
            assert b.id is not None
            b_ = await BattleRequest.get(db, b.id)
            assert b_ is not None
            assert b_.status == BattleStatus.DONE, "all battles are done"

        for p in players:
            await db.refresh(p)
            assert p.battle_lock == False, "all players are unlocked"

    await cancel(r)
    await asyncio.gather(*[cancel(w) for w in workers])
