from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession


def get_engine(db_url: str, **kwargs) -> AsyncEngine:
    return create_async_engine(db_url, echo=True, **kwargs)


async def get_session(engine: AsyncEngine):
    async with AsyncSession(engine) as session:
        yield session


async def init_models(engine: AsyncEngine):
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def drop_models(engine: AsyncEngine):
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
