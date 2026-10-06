from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession


def get_engine(db_url: str, echo=False, **kwargs) -> AsyncEngine:
    return create_async_engine(db_url, echo=echo, **kwargs)


async def get_session(engine: AsyncEngine):
    async with AsyncSession(engine) as session:
        yield session


async def init_models(engine: AsyncEngine):
    async with engine.begin() as conn:
        if engine.url.drivername.startswith("sqlite"):
            await conn.exec_driver_sql("PRAGMA foreign_keys=ON;")
        await conn.run_sync(SQLModel.metadata.create_all)


async def drop_models(engine: AsyncEngine):
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
