import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from battle_engine.models import BattleRequest, Player
from tests.util import make_player


async def test_player_name_unique(db: AsyncSession):
    p1 = Player(name="one")
    p2 = Player(name="one")
    async with db.begin():
        db.add(p1)
    with pytest.raises(IntegrityError):
        async with db.begin():
            db.add(p2)
    assert await Player.count_all(db) == 1


async def test_battle_request_integrity(db: AsyncSession):
    players = make_player(db)
    p1 = await anext(players)
    assert p1.id is not None
    req = BattleRequest(initiator_id=p1.id, opponent_id=999)
    with pytest.raises(IntegrityError):
        async with db.begin():
            db.add(req)
