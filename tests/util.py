import random
from asyncio import CancelledError, Task
from collections.abc import AsyncGenerator

from sqlmodel import insert
from sqlmodel.ext.asyncio.session import AsyncSession

from battle_engine.models import Player


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
