from redis.asyncio import BlockingConnectionPool

from .settings import settings


def make_blocking_pool():
    return BlockingConnectionPool.from_url(
        settings.REDIS_URL,
        max_connections=settings.REDIS_MAX_CONNECTIONS,
        timeout=settings.REDIS_TIMEOUT,
        socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
        socket_connect_timeout=2.0,
        decode_responses=True,
    )
