import logging
import os
from typing import Annotated

from taskiq import Context, TaskiqDepends, TaskiqEvents, TaskiqState
from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker

from battle_engine.backend.shared import get_backend_impl
from battle_engine.settings import settings

from .models import BattleRequest

REDIS_URL = os.getenv("REDIS_URL")
assert REDIS_URL

log = logging.getLogger(__name__)

result_backend = RedisAsyncResultBackend(
    redis_url=REDIS_URL,
)

broker = RedisStreamBroker(
    url=REDIS_URL,
).with_result_backend(result_backend)


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def startup(state: TaskiqState) -> None:
    log.info(f"Worker starting up with backend: {settings.BACKEND}")
    backend = get_backend_impl()
    lifespan = backend.lifespan()
    state.backend = backend
    state.backend_lifespan = lifespan
    await lifespan.__aenter__()


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def shutdown(state: TaskiqState) -> None:
    log.info("Worker shutting down")
    await state.backend_lifespan.__aexit__(None, None, None)


@broker.task
async def process_battle_task(
    initiator_id: str,
    opponent_id: str,
    context: Annotated[Context, TaskiqDepends()],
) -> dict:
    req = BattleRequest(initiator_id=initiator_id, opponent_id=opponent_id)
    result = await context.state.backend.resolve_battle(req)
    log.info(f"Processed battle {initiator_id} vs. {opponent_id}")
    return result.model_dump()
