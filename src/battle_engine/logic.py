from battle_engine.models import BattleRequest, Player


def pstat(p: Player):
    return f"{p.name} (❤️ {p.hit_points}, a:{p.attack}, d:{p.defense})"


def process_battle(req: BattleRequest):
    """Produces battle outcome. Keeps a report of the battle (intentionally as
    unstructured text to keep things simple). Mutates battle request's players
    in place."""
    report = [
        f"= Player {pstat(req.initiator)} initiated battle against player {pstat(req.opponent)}"
    ]
    p1 = req.initiator
    p1_min = p1.attack / 2
    p2 = req.opponent
    p2_min = p2.attack / 2
    while p1.hit_points != 0 and p2.hit_points != 0:
        report.append(f" - {pstat(p1)} is attacking {pstat(p2)}")
        if p2.defense < p1.attack:
            damage = p1.attack
            new_hit_points = min(0, p2.hit_points - damage)
            # If an attacker starts with 100 health and 70 attack,
            # losing 10% of health reduces attack by 10%.
            lost_health = new_hit_points / p2.hit_points
            p2.hit_points = new_hit_points
            # Attack will never drop below 35, which is 50% of the base value.
            p2.attack = int(min(p2_min, lost_health * p2.attack))
            report.append(
                f" + {p1.name} hit {p2.name} with d:{damage}, {p2.name}'s ❤️ {p2.hit_points}"
            )
        else:
            report.append(f" - {p1.name} missed")
        # Roles switch after each turn.
        x = p1
        x_min = p1_min
        p1 = p2
        p1_min = p2_min
        p2 = x
        p2_min = x_min
    winner = p1 if p2.hit_points == 0 else p2
    report.append(f" ~ {winner.name} is victorious!")
    return winner, report
