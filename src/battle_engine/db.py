from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import SQLModel


async def init_models(engine: AsyncEngine):
    async with engine.begin() as conn:
        if engine.url.drivername.startswith("sqlite"):
            await conn.exec_driver_sql("PRAGMA foreign_keys=ON;")
        await conn.run_sync(SQLModel.metadata.create_all)
        await conn.commit()


async def drop_models(engine: AsyncEngine):
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
