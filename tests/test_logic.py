from battle_engine.logic import process_battle
from battle_engine.models import BattleRequest, Player


def test_process_battle_base():
    p1 = Player(name="Joe", defense=30, attack=70)
    p2 = Player(name="Jane", defense=50, attack=90)
    req = BattleRequest(
        initiator_id=0,
        initiator=p1,
        opponent_id=0,
        opponent=p2,
    )
    winner = process_battle(req)[0]
    assert winner == p1
