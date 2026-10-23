from battle_engine.logic import process_battle
from battle_engine.models import (
    BattleRequestReady,
    BattleResultRegular,
    PlayerBase,
)


def test_process_battle_base():
    p1 = PlayerBase(name="Joe", defense=30, attack=70)
    p2 = PlayerBase(name="Jane", defense=50, attack=90)
    req = BattleRequestReady(
        initiator_id=1,
        initiator=p1,
        opponent_id=2,
        opponent=p2,
    )
    result = process_battle(req)
    assert isinstance(result, BattleResultRegular)
    print("\n")
    for l in result.report:
        print(l)
    assert result.winner == p2


def test_process_battle_base_equals():
    p1 = PlayerBase(name="Joe", defense=70, attack=80)
    p2 = PlayerBase(name="Jane", defense=70, attack=90)
    req = BattleRequestReady(
        initiator_id=1,
        initiator=p1,
        opponent_id=2,
        opponent=p2,
    )
    result = process_battle(req)
    assert isinstance(result, BattleResultRegular)
    print("\n")
    for l in result.report:
        print(l)
    assert result.winner == p1


def test_resources_stolen():
    p1 = PlayerBase(name="Joe", defense=70, attack=80, gold=100, silver=100)
    p2 = PlayerBase(name="Jane", defense=70, attack=90, gold=100, silver=100)
    req = BattleRequestReady(
        initiator_id=1,
        initiator=p1,
        opponent_id=2,
        opponent=p2,
    )
    result = process_battle(req)
    assert isinstance(result, BattleResultRegular)

    assert result.winner is p1
    assert p2.silver < p1.silver
