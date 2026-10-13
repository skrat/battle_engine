import asyncio
import logging
import math
import random
import uuid
from collections.abc import Awaitable
from typing import Any

from aredis_om import NotFoundError
from fastapi import HTTPException
from redis.asyncio import Redis

from battle_engine.settings import settings

from .models import (
    BattleRequest,
    BattleRequestReady,
    BattleResult,
    BattleResultStats,
    Player,
)

log = logging.getLogger(__name__)

SCRIPT_ACQUIRE_PLAYERS_SRC = """
-- KEYS[1] = p1 lock key
-- KEYS[2] = p2 lock key
-- KEYS[3] = p1 player key
-- KEYS[4] = p2 player key
-- ARGV[1] = lock token
-- ARGV[2] = lock TTL (sec)

if redis.call('exists', KEYS[1]) == 1 or redis.call('exists', KEYS[2]) == 1 then
    -- locked by someone, retry
    return 0
end

local p1 = redis.call('hgetall', KEYS[3])
local p2 = redis.call('hgetall', KEYS[4])

if #p1 == 0 then return -1 end      -- initiator not found
if #p2 == 0 then return -2 end      -- opponent not found

redis.call('set', KEYS[1], ARGV[1], 'EX', ARGV[2])
redis.call('set', KEYS[2], ARGV[1], 'EX', ARGV[2])
return {1, p1, p2}
"""

SCRIPT_RELEASE_PLAYERS_SRC = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    redis.call('del', KEYS[1])
end
if redis.call('get', KEYS[2]) == ARGV[1] then
    redis.call('del', KEYS[2])
end
"""

# Prepared scripts. There is no I/O and no connection here, just precomputed
# digest for each script.
_encoder = Redis.from_url(settings.REDIS_URL, decode_responses=True)  # no I/O
script_acquire_players = _encoder.register_script(SCRIPT_ACQUIRE_PLAYERS_SRC)
script_release_players = _encoder.register_script(SCRIPT_RELEASE_PLAYERS_SRC)


def pstat(p: Player):
    return f"{p.name} (❤️ {p.hit_points}, a:{p.attack}, d:{p.defense})"


def ploot(p: Player):
    return f"{p.name} (❤️ {p.hit_points}, Gld:{p.gold}, Slv:{p.silver})"


def process_battle(req: BattleRequestReady, max_turns=20):
    """Produces battle outcome. Keeps a report of the battle (intentionally
    unstructured text to keep things simple). Mutates battle request's players
    in place. Doesn't mutate the battle request.

    :param max_turns: used to prevent infinite battles, default is 20
    :type max_turns: int, optional
    """
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
        if steps >= max_turns:
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
        winner=winner,
        report=report,
        stolen=(loot_gold, loot_silver),
    )


async def resolve_battle(
    redis: Redis,
    req: BattleRequest,
    poll_interval=settings.BATTLE_LOCK_POLL_INTERVAL,
    wait_for: Awaitable[Any] | None = None,
) -> BattleResultStats:
    """Wait for battle players to become available (until all battles they are in are
    finished), then processes the battle and returns the outcome."""

    p1_id = req.initiator_id
    p2_id = req.opponent_id
    p1: Player | None = None
    p2: Player | None = None

    p1_lock_key = Player.LOCK_KEY.format(id=p1_id)
    p2_lock_key = Player.LOCK_KEY.format(id=p2_id)
    lock_token = uuid.uuid7().hex

    lock_attempts = 1
    while True:
        res = await script_acquire_players(
            keys=[
                Player.LOCK_KEY.format(id=p1_id),
                Player.LOCK_KEY.format(id=p2_id),
                Player.make_primary_key(p1_id),
                Player.make_primary_key(p2_id),
            ],
            args=[lock_token, settings.BATTLE_LOCK_TTL],
            client=redis,
        )
        if isinstance(res, int):
            if res == 0:
                lock_attempts += 1
                await asyncio.sleep(poll_interval)
                poll_interval = min(
                    poll_interval * 2,
                    settings.BATTLE_LOCK_MAX_POLL,
                )
                continue
            missing_id = p1_id if res == -1 else p2_id
            raise HTTPException(404, [f"player {missing_id} not found"])
        _, p1_doc, p2_doc = res
        p1 = Player.rehydrate(p1_id, p1_doc)
        p2 = Player.rehydrate(p2_id, p2_doc)
        break

    log.debug(f"Players {p1_id}, {p2_id} locked")

    try:
        req_ready = BattleRequestReady(
            initiator=p1,
            opponent=p2,
            **req.model_dump(),
        )
        result = process_battle(req_ready)

        if wait_for is not None:
            await wait_for

        async with redis.pipeline(transaction=True) as pipe:
            pipe.multi()
            await p1.save(pipeline=pipe)
            await p2.save(pipeline=pipe)
            await pipe.execute()

    except NotFoundError as ex:
        # We can raise to HTTP server safely
        raise HTTPException(404, [f"{ex.args} not found"])
    finally:
        # Release the players' locks, so they'll become available for future battles
        await script_release_players(
            keys=[p1_lock_key, p2_lock_key],
            args=[lock_token],
            client=redis,
        )

    log.debug(f"Players {p1.pk}, {p2.pk} released")

    return BattleResultStats(
        num_lock_attempts=lock_attempts,
        **result.model_dump(),
    )
