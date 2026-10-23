import math
import random

from .models import (
    BattleRequestReady,
    BattleResult,
    BattleResultRegular,
    BattleResultTie,
    BattleTurn,
    BattleTurnHit,
    BattleTurnMiss,
    PlayerBase,
)


def pstat(p: PlayerBase):
    return f"{p.name} (❤️ {p.hit_points}, a:{p.attack}, d:{p.defense})"


def ploot(p: PlayerBase):
    return f"{p.name} (❤️ {p.hit_points}, Gld:{p.gold}, Slv:{p.silver})"


def process_battle(req: BattleRequestReady, max_turns=20) -> BattleResult:
    """Produces battle outcome. Keeps a report of the battle (intentionally
    unstructured text to keep things simple). Mutates battle request's players
    in place. Doesn't mutate the battle request.

    :param max_turns: used to prevent infinite battles, default is 20
    :type max_turns: int, optional
    """
    report: list[BattleTurn] = []
    p1 = req.initiator
    p2 = req.opponent
    # Keep track of initial attack value
    p1_min = p1.attack / 2
    p2_min = p2.attack / 2
    # The battle ends when one player's Hit Points reach zero.
    steps = 0
    while p1.hit_points != 0 and p2.hit_points != 0:
        if steps >= max_turns:
            # It's a tie when players' defense is too high
            # undefined behavior
            return BattleResultTie(
                initiator=req.initiator,
                opponent=req.opponent,
                report=report,
            )
        steps += 1
        if p2.defense < p1.attack:
            damage = p1.attack
            new_hit_points = max(0, p2.hit_points - damage)
            # If an attacker starts with 100 health and 70 attack,
            # losing 10% of health reduces attack by 10%.
            lost_health = new_hit_points / p2.hit_points
            p2.hit_points = new_hit_points
            # Attack will never drop below 50% of the base value.
            p2.attack = int(max(p2_min, p2.attack * lost_health))
            report.append(
                BattleTurnHit(
                    attacking_player=p1,
                    defending_player=p2,
                    damange=damage,
                )
            )
        else:
            report.append(
                BattleTurnMiss(
                    attacking_player=p1,
                    defending_player=p2,
                )
            )
        # Roles switch after each turn.
        x = p1
        x_min = p1_min
        p1 = p2
        p1_min = p2_min
        p2 = x
        p2_min = x_min

    winner = p1 if p2.hit_points == 0 else p2
    loser = p1 if p1.hit_points == 0 else p2

    # Winner steals resources
    theft_pct = random.randint(5, 10)
    theft_f = theft_pct / 100.0
    loot_gold = math.ceil(loser.gold * theft_f)
    loot_silver = math.ceil(loser.silver * theft_f)
    loser.gold = max(0, loser.gold - loot_gold)
    loser.silver = max(0, loser.silver - loot_silver)
    winner.gold = winner.gold + loot_gold
    winner.silver = winner.silver + loot_silver

    return BattleResultRegular(
        initiator=req.initiator,
        opponent=req.opponent,
        winner=winner,
        report=report,
        stolen=(loot_gold, loot_silver),
    )
