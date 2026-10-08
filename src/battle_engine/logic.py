import asyncio
import math
import random

from sqlmodel import select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from battle_engine.models import BattleRequest, BattleRequestReady, BattleResult, Player


def pstat(p: Player):
    return f"{p.name} (❤️ {p.hit_points}, a:{p.attack}, d:{p.defense})"


def ploot(p: Player):
    return f"{p.name} (❤️ {p.hit_points}, Gld:{p.gold}, Slv:{p.silver})"


def process_battle(req: BattleRequestReady, max_steps=10):
    """Produces battle outcome. Keeps a report of the battle (intentionally
    unstructured text to keep things simple). Mutates battle request's players
    in place. Doesn't mutate the battle request."""
    report = [
        f"= Player {pstat(req.initiator)} initiated battle against player {pstat(req.opponent)}"
    ]
    p1 = req.initiator
    p2 = req.opponent
    # Keep track of initial attack value
    p1_min = p1.attack / 2
    p2_min = p2.attack / 2
    # The battle ends when one player's Hit Points reach zero.
    steps = 0
    while p1.hit_points != 0 and p2.hit_points != 0:
        if steps >= max_steps:
            # It's a tie when players' defense is too high
            # undefined behavior
            report.append(" ! max steps reached")
            p2.hit_points = 0
            break
        steps += 1
        report.append(f" ~ {pstat(p1)} is attacking {pstat(p2)}")
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
                f" > {p1.name} hit {p2.name} with d:{damage}, {p2.name}'s ❤️ {p2.hit_points}"
            )
        else:
            report.append(f" < {p1.name} missed")
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

    report.append(f" @ {ploot(winner)} is victorious!")
    report.append(f" @ {winner.name} stole gold:{loot_gold} and silver:{loot_silver} !")

    return BattleResult(
        battle=req, winner=winner, report=report, stolen=(loot_gold, loot_silver)
    )


async def get_free_player(db: AsyncSession, id: int):
    return (
        await db.exec(
            select(Player).where(Player.id == id).where(Player.battle_lock == False)
        )
    ).one_or_none()


async def resolve_battle(db: AsyncSession, req: BattleRequest, poll_interval=1 / 30):
    """Wait for battle players to become available (until all battles they are in are
    finished), then processes the battle and returns the outcome."""
    p1: Player | None = None
    p2: Player | None = None
    await db.commit()
    while p1 is None or p2 is None:
        # Poll the DB for players
        async with db.begin():
            # For each attempt, start a transaction
            p1 = await get_free_player(db, req.initiator_id)
            p2 = await get_free_player(db, req.opponent_id)
            if p1 and p2:
                # Once both players are available for battle, lock them, so no
                # other battle involving these two players can be processes
                await db.exec(
                    update(Player)
                    .where(Player.id.in_([req.initiator_id, req.opponent_id]))  # pyright: ignore
                    .values(battle_lock=True)
                )
                await db.commit()
                break
        await asyncio.sleep(poll_interval)
    req_ready = BattleRequestReady(initiator=p1, opponent=p2, **req.model_dump())
    result = process_battle(req_ready)
    p1.battle_lock = False
    p2.battle_lock = False
    await db.commit()
    # Release the player locks, so they become available for further battles
    async with db.begin():
        db.add(p1)
        db.add(p2)
    return result
