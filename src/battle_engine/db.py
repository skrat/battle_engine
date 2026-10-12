from redis.asyncio import BlockingConnectionPool

from .settings import settings


def make_blocking_pool():
    return BlockingConnectionPool.from_url(
        settings.REDIS_URL,
        max_connections=settings.REDIS_MAX_CONNECTIONS,
        timeout=5,
        socket_timeout=5,
        socket_connect_timeout=2.0,
        decode_responses=True,
    )
