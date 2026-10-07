import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from battle_engine.models import BattleRequest, Player
from tests.util import make_battle, make_player


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
    players = make_player(db)
    p1 = await anext(players)
    assert p1.id is not None
    req = BattleRequest(initiator_id=p1.id, opponent_id=999)
    with pytest.raises(IntegrityError):
        async with db.begin():
            db.add(req)


@pytest.mark.asyncio
async def test_battle_request_pop_and_release(db: AsyncSession):
    players = make_player(db)
    req_in = await make_battle(db, players)
    assert req_in.id is not None

    req_out = await BattleRequest.pop(db)
    assert req_out is not None
    assert req_out.id == req_in.id

    p1 = await Player.get(db, req_out.initiator_id)
    p2 = await Player.get(db, req_out.opponent_id)
    assert p1 is not None and p2 is not None
    assert p1.battle_lock == True and p2.battle_lock == True

    req_out = await BattleRequest.pop(db)
    assert req_out is None
