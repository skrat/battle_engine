import httpx2
import pytest
from redis import Redis as RedisSync
from redis.asyncio import BlockingConnectionPool, Redis

from battle_engine.db import make_blocking_pool
from battle_engine.main import app, get_redis
from battle_engine.models import REDIS
from battle_engine.settings import settings


@pytest.fixture(scope="session")
def redis_service(docker_ip, docker_services):
    """Ensure that Redis service is up and responsive."""
    port = docker_services.port_for("battleengine_pytest_redis", 6379)
    url = f"redis://{docker_ip}:{port}"

    def is_responsive(url: str) -> bool:
        with RedisSync.from_url(url) as redis:
            return redis.ping()

    docker_services.wait_until_responsive(
        timeout=30.0, pause=0.1, check=lambda: is_responsive(url)
    )
    return url


@pytest.fixture(scope="session")
async def redis_pool(redis_service):
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
