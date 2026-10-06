import random
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from battle_engine.models import BattleRequest, Player


async def make_player(db: AsyncSession) -> AsyncGenerator[Player]:
    cnt = 0
    while True:
        n = random.choice(["Jane", "Joe", "Joseph"])
        p = Player(name=f"{n}{cnt}")
        async with db.begin():
            db.add(p)
        await db.refresh(p)
        await db.commit()
        yield p
        cnt += 1


@pytest.mark.asyncio
async def test_player_name_unique(db: AsyncSession):
    p1 = Player(name="one")
    p2 = Player(name="one")
    async with db.begin():
        db.add(p1)
    with pytest.raises(IntegrityError):
        async with db.begin():
            db.add(p2)
    assert await Player.count_all(db) == 1


@pytest.mark.asyncio
async def test_battle_request_integrity(db: AsyncSession):
    req = BattleRequest(initiator_id=12, opponent_id=999)
    with pytest.raises(IntegrityError):
        async with db.begin():
            db.add(req)
