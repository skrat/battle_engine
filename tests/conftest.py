import asyncio

import httpx2
import pytest
from redis import Redis as RedisSync
from redis.asyncio import BlockingConnectionPool, Redis
from taskiq.api import run_receiver_task

from battle_engine.backend.redis.db import make_blocking_pool
from battle_engine.backend.redis.impl import RedisBackend
from battle_engine.backend.redis.settings import settings as redis_settings
from battle_engine.backend.shared import Backend
from battle_engine.main import app, get_backend
from battle_engine.tasks import broker


@pytest.fixture(scope="session")
def redis_service(docker_ip, docker_services) -> str:
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
async def redis_pool(redis_service: str):
    redis_settings.REDIS_URL = redis_service
    pool = make_blocking_pool()
    yield pool
    await pool.disconnect()


@pytest.fixture
async def redis(redis_pool: BlockingConnectionPool):
    async with Redis(connection_pool=redis_pool) as r:
        await r.flushdb()
        yield r


@pytest.fixture
async def client(redis):
    """We need redis dependency to call flushdb."""
    backend = RedisBackend()
    assert isinstance(backend, Backend), "backend supports Backend protocol"

    async def backend_override():
        yield backend

    app.dependency_overrides[get_backend] = backend_override

    async with (
        backend.lifespan(app),
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            headers={
                redis_settings.API_KEY_HEADER: redis_settings.API_KEY_SECRET,
            },
        ) as client,
    ):
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
async def worker():
    broker.is_worker_process = True
    await broker.startup()
    worker_task = asyncio.create_task(run_receiver_task(broker))
    yield
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        ...
    await broker.shutdown()
