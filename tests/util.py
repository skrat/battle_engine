import random
import subprocess
import sys
from asyncio import CancelledError, Task
from collections.abc import AsyncGenerator
from threading import Thread
from typing import IO, Any

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


def _wait_for_string(stream: IO[Any], pattern: str):
    bpat = pattern.encode()
    for line in iter(stream.readline, b""):
        if bpat in line:
            break


def subprocess_wait_for(
    args: list[str], pattern: str, env: dict | None = None
) -> subprocess.Popen:
    p = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        close_fds=("posix" in sys.builtin_module_names),
        env=env or {},
    )
    t = Thread(target=_wait_for_string, args=(p.stdout, pattern))
    t.daemon = True
    t.start()
    t.join()
    return p
