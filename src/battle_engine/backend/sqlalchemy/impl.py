import asyncio
import logging
from collections.abc import Awaitable
from contextlib import asynccontextmanager
from typing import cast

from fastapi import HTTPException
from sqlmodel import select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from battle_engine.backend.sqlalchemy.settings import settings
from battle_engine.logic import process_battle

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
from .db import create_engine, init_models, sessionmaker
from .models import Leaderboard, Player

log = logging.getLogger(__name__)


class SQLBackend:
    def __init__(self) -> None:
        self.engine = create_engine()
        self.sessionmaker = sessionmaker(self.engine)

    @asynccontextmanager
    async def lifespan(self):
        await init_models(self.engine)
        yield
        await self.engine.dispose()

    async def create_player(self, p: PlayerBase) -> PlayerFull:
        async with self.sessionmaker() as sess:
            return await Player.create(sess, p)

    async def resolve_battle(
        self,
        req: BattleRequest,
        poll_interval=settings.BATTLE_LOCK_POLL_INTERVAL,
        max_attempts=5,
        _wait_for: Awaitable[None] | None = None,
    ) -> BattleResultStats:
        """Wait for battle players to become available (until all battles they are in are
        finished), then processes the battle and returns the outcome."""

        p1_id = int(req.initiator_id)
        p2_id = int(req.opponent_id)
        if p1_id == p2_id:
            raise ValueError("Self-battle not allowed")

        p1: Player | None = None
        p2: Player | None = None
        async with self.sessionmaker() as sess:
            # Ensure players exist
            await self._ensure_exist(sess, (p1_id, p2_id))
            # Ensure no transaction
            await sess.commit()

            lock_attempts = 0
            while p1 is None or p2 is None:
                # Poll the DB for players
                lock_attempts += 1
                if lock_attempts > max_attempts:
                    raise RuntimeError(
                        f"Max attempts ({max_attempts}) to lock players reached"
                    )
                async with sess.begin():
                    # For each attempt, start a transaction to ensure isolation
                    r = await sess.exec(
                        update(Player)
                        .where(Player.id.in_([p1_id, p2_id]))  # pyright: ignore
                        .where(Player.battle_lock == False)  # pyright: ignore[reportArgumentType]
                        .values(battle_lock=True)
                        .returning(Player)
                    )
                    # UPDATE locks the row exclusively during this transaction
                    rows = r.all()
                    if len(rows) != 2:
                        # We failed to lock both players, rollback
                        await sess.rollback()
                    else:
                        await sess.commit()
                        pmap = {
                            rows[0][0].id: rows[0][0],
                            rows[1][0].id: rows[1][0],
                        }
                        p1 = pmap[p1_id]
                        p2 = pmap[p2_id]
                        break

                await asyncio.sleep(poll_interval)
                poll_interval = min(
                    poll_interval * 2,
                    settings.BATTLE_LOCK_MAX_POLL,
                )

            assert p1 is not None and p2 is not None
            log.debug(f"Players {p1.id}, {p2.id} locked")

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
                # Release the players' locks, so they'll become available for future battles
                await sess.commit()
                async with sess.begin():
                    await sess.exec(
                        update(Player)
                        .where(Player.id.in_([p1_id, p2_id]))  # pyright: ignore
                        .values(battle_lock=False)
                    )
                    if result and isinstance(result, BattleResultRegular):
                        winner_id = p1_id if p1 == result.winner else p2_id
                        await Leaderboard.update(sess, winner_id, sum(result.stolen))
                log.debug(f"Players {p1.id}, {p2.id} released")

            assert result
            return BattleResultStats(
                result=result,
                num_lock_attempts=lock_attempts,
            )

    async def leaderboard(self, limit: int = 100) -> list[LeaderboardEntry]:
        async with self.sessionmaker() as sess:
            result = await Leaderboard.ranked(sess, limit)
            return [
                LeaderboardEntry(
                    rank=i + 1,
                    score=row.score,
                    player=str(row.player_id),
                )
                for i, row in enumerate(result)
            ]

    async def _ensure_exist(self, sess: AsyncSession, ids: tuple[int, int]):
        found = set(
            (
                await sess.exec(
                    select(cast(int, Player.id)).where(
                        Player.id.in_(ids)  # pyright: ignore
                    )
                )
            ).all()
        )
        if len(found) != 2:
            missing = set(ids) - found
            raise HTTPException(404, [f"player {missing.pop()} not found"])
