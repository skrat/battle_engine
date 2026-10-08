import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from battle_engine.models import Player


async def test_player_name_unique(db: AsyncSession):
    p1 = Player(name="one")
    p2 = Player(name="one")
    async with db.begin():
        db.add(p1)
    with pytest.raises(IntegrityError):
        async with db.begin():
            db.add(p2)
    assert await Player.count_all(db) == 1
