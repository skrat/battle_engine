import random
from asyncio import CancelledError, Task
from collections.abc import AsyncGenerator

from sqlmodel import insert
from sqlmodel.ext.asyncio.session import AsyncSession

from battle_engine.models import BattleRequest, BattleStatus, Player


async def cancel(t: Task):
    t.cancel()
    try:
        await t
    except CancelledError:
        ...


def random_player(i: int) -> Player:
    n = random.choice(["Jane", "Joe", "Joseph"])
    return Player(
        name=f"{n}{i}",
        defense=random.randint(20, 60),
        attack=random.randint(50, 80),
    )


async def make_player(db: AsyncSession) -> AsyncGenerator[Player]:
    cnt = 0
    while True:
        cnt += 1
        n = random.choice(["Jane", "Joe", "Joseph"])
        p = Player(
            name=f"{n}{cnt}",
            defense=random.randint(20, 60),
            attack=random.randint(50, 80),
        )
        stmt = (
            insert(Player).values(**p.model_dump(exclude_unset=True)).returning(Player)
        )
        rslt = await db.exec(stmt)
        await db.commit()
        yield rslt.scalar_one()


async def make_battle(
    db: AsyncSession,
    pgen: AsyncGenerator[Player],
    p1: Player | None = None,
    p2: Player | None = None,
):
    if p1 is None:
        p1 = await anext(pgen)
    if p2 is None:
        p2 = await anext(pgen)
    assert p1.id is not None
    assert p2.id is not None
    assert p1.id != p2.id
    req = BattleRequest(status=BattleStatus.NEW, initiator_id=p1.id, opponent_id=p2.id)
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return req
