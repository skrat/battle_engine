import asyncio
import logging
import uuid
from collections.abc import Awaitable
from contextlib import asynccontextmanager

from fastapi import HTTPException
from redis.asyncio import Redis
from redis.exceptions import ConnectionError

from ...logic import process_battle
from ...models import (
    BattleRequest,
    BattleRequestReady,
    BattleResult,
    BattleResultRegular,
    BattleResultStats,
    LeaderboardEntry,
    PlayerBase,
    PlayerFull,
)
from .db import make_blocking_pool
from .models import Leaderboard, Player
from .settings import settings

log = logging.getLogger(__name__)

# KEYS[1] = p1 lock key
# KEYS[2] = p2 lock key
# KEYS[3] = p1 player key
# KEYS[4] = p2 player key
# ARGV[1] = lock token
# ARGV[2] = lock TTL (sec)
SCRIPT_ACQUIRE_PLAYERS_SRC = """
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

# KEYS[1]=leaderboard
# KEYS[2]=p1 lock
# KEYS[3]=p2 lock
# KEYS[4]=p1 hash
# KEYS[5]=p2 hash
# ARGV[1]=lock token
# ARGV[2]=winner id
# ARGV[3]=score delta
# ARGV[4]=p1 field-pair count
# then: p1 field,value pairs, then p2 field,value pairs
SCRIPT_COMMIT_SRC = """
local token = ARGV[1]
local i = 5
local end1 = 5 + tonumber(ARGV[4]) * 2
while i < end1 do
    redis.call('hset', KEYS[4], ARGV[i], ARGV[i + 1])
    i = i + 2
end
while i < #ARGV + 1 do
    redis.call('hset', KEYS[5], ARGV[i], ARGV[i + 1])
    i = i + 2
end
if redis.call('get', KEYS[2]) == token then redis.call('del', KEYS[2]) end
if redis.call('get', KEYS[3]) == token then redis.call('del', KEYS[3]) end
redis.call('zincrby', KEYS[1], tonumber(ARGV[3]), ARGV[2])
return 1
"""

# Prepared scripts. There is no I/O and no connection here, just precomputed
# digest for each script.
_encoder = Redis.from_url(settings.REDIS_URL, decode_responses=True)  # no I/O
script_acquire_players = _encoder.register_script(SCRIPT_ACQUIRE_PLAYERS_SRC)
script_commit = _encoder.register_script(SCRIPT_COMMIT_SRC)


async def health_check(redis: Redis, max_attempts=5, interval=0.1):
    attempts = 0
    last_exc = None
    while attempts < max_attempts:
        try:
            if await redis.ping():
                return
        except ConnectionError as e:
            last_exc = e
        attempts += 1
    raise RuntimeError(f"Failed to connect to {settings.REDIS_URL}") from last_exc


class RedisBackend:
    def __init__(self) -> None:
        self.pool = make_blocking_pool()
        self.client = Redis(
            connection_pool=self.pool,
            decode_responses=True,
        )

    @asynccontextmanager
    async def lifespan(self):
        await health_check(self.client)
        yield
        await self.pool.disconnect()

    async def create_player(self, p: PlayerBase) -> PlayerFull:
        clean = Player.model_validate(p)
        await clean.create(self.client)
        assert isinstance(clean.pk, str)
        return PlayerFull(
            id=clean.pk,
            **clean.model_dump(exclude={"pk"}),
        )

    async def resolve_battle(
        self,
        req: BattleRequest,
        poll_interval=settings.BATTLE_LOCK_POLL_INTERVAL,
        _wait_for: Awaitable[None] | None = None,
    ) -> BattleResultStats:

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
                client=self.client,
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
        result: BattleResult | None = None

        try:
            req_ready = BattleRequestReady(
                initiator=p1,
                opponent=p2,
                **req.model_dump(),
            )
            result = process_battle(req_ready)

            if _wait_for is not None:
                await _wait_for

        finally:
            score_delta = 0
            winner_id = p1_id
            if result and isinstance(result, BattleResultRegular):
                score_delta = sum(result.stolen)
                winner_id = result.winner.pk
            # Release the players' locks, save players, and update leaderbord
            p1_args = p1.to_args()
            p2_args = p2.to_args()
            await script_commit(
                keys=[
                    Leaderboard.PLAYER_SET,
                    p1_lock_key,
                    p2_lock_key,
                    Player.make_primary_key(p1_id),
                    Player.make_primary_key(p2_id),
                ],
                args=[
                    lock_token,
                    str(winner_id),
                    str(score_delta),
                    str(len(p1_args) // 2),
                    *p1_args,
                    *p2_args,
                ],
                client=self.client,
            )

        log.debug(f"Players {p1.pk}, {p2.pk} released")

        assert result
        return BattleResultStats(
            result=result,
            num_lock_attempts=lock_attempts,
        )

    async def leaderboard(self, limit: int = 100) -> list[LeaderboardEntry]:
        return await Leaderboard.ranked(self.client)
