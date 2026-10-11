from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker

from .db import async_session
from .logic import resolve_battle
from .models import BattleRequest
from .settings import settings

result_backend = RedisAsyncResultBackend(
    redis_url=settings.REDIS_URL,
)

broker = RedisStreamBroker(
    url=settings.REDIS_URL,
).with_result_backend(result_backend)


@broker.task
async def process_battle_task(initiator_id: int, opponent_id: int) -> dict:
    async with async_session() as session:
        req = BattleRequest(initiator_id=initiator_id, opponent_id=opponent_id)
        result = await resolve_battle(session, req)
        print(f"Processed battle {initiator_id} vs. {opponent_id}")
        return result.model_dump()
