import httpx2
import pytest
from redis.asyncio import BlockingConnectionPool, Redis

from battle_engine.db import make_blocking_pool
from battle_engine.main import app, get_redis
from battle_engine.models import REDIS
from battle_engine.settings import settings


@pytest.fixture(scope="session")
async def redis_pool():
    pool = make_blocking_pool()
    yield pool
    await pool.disconnect()


@pytest.fixture
async def redis(redis_pool: BlockingConnectionPool):
    async with Redis(connection_pool=redis_pool) as r:
        await r.flushdb()
        with REDIS.set(r):
            yield r


@pytest.fixture
async def client(redis: Redis):
    async def redis_override():
        yield redis

    app.dependency_overrides[get_redis] = redis_override
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app),
        headers={settings.API_KEY_HEADER: settings.API_KEY_SECRET},
    ) as client:
        yield client
    app.dependency_overrides.clear()
