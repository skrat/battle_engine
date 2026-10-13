from typing import Annotated

from redis.asyncio import Redis
from taskiq import Context, TaskiqDepends, TaskiqEvents, TaskiqState
from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker

from .db import REDIS, make_blocking_pool
from .logic import resolve_battle
from .models import BattleRequest
from .settings import settings

result_backend = RedisAsyncResultBackend(
    redis_url=settings.REDIS_URL,
)

broker = RedisStreamBroker(
    url=settings.REDIS_URL,
).with_result_backend(result_backend)

redis_pool = make_blocking_pool()


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def startup(state: TaskiqState) -> None:
    state.redis_pool = make_blocking_pool()


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def shutdown(state: TaskiqState) -> None:
    await state.redis_pool.disconnect()


@broker.task
async def process_battle_task(
    initiator_id: str,
    opponent_id: str,
    context: Annotated[Context, TaskiqDepends()],
) -> dict:
    async with Redis(connection_pool=context.state.redis_pool) as r:
        with REDIS.set(r):
            req = BattleRequest(initiator_id=initiator_id, opponent_id=opponent_id)
            result = await resolve_battle(r, req)
            print(f"Processed battle {initiator_id} vs. {opponent_id}")
            return result.model_dump()
