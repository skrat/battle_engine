from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from .settings import settings


async def init_models(engine: AsyncEngine):
    async with engine.begin() as conn:
        if engine.url.drivername.startswith("sqlite"):
            await conn.exec_driver_sql("PRAGMA foreign_keys=ON;")
        await conn.run_sync(SQLModel.metadata.create_all)
        await conn.commit()


async def drop_models(engine: AsyncEngine):
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)


engine = create_async_engine(settings.DB_URL)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def db_session():
    async with async_session() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(db_session)]
