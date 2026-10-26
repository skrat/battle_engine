from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from .settings import settings


def create_engine() -> AsyncEngine:
    return create_async_engine(
        settings.DB_URL,
        # echo=True,
        pool_size=100,
        max_overflow=20,
        pool_recycle=3600,
        pool_use_lifo=True,
        pool_pre_ping=True,
        isolation_level="SERIALIZABLE",
    )


def sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def init_models(engine: AsyncEngine):
    """Create DB tables."""
    async with engine.begin() as conn:
        if engine.url.drivername.startswith("sqlite"):
            await conn.exec_driver_sql("PRAGMA foreign_keys=ON;")
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL;")

        await conn.run_sync(SQLModel.metadata.create_all)
        await conn.commit()


async def drop_models(engine: AsyncEngine):
    """Drop DB tables."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
