import httpx2
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio.engine import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from battle_engine.settings import settings

settings.DB_URL = "sqlite+aiosqlite:///test.sqlite3"

from battle_engine.db import async_session, db_session, drop_models, engine, init_models
from battle_engine.main import app


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    yield engine


@pytest_asyncio.fixture
async def db_sessionmaker(db_engine: AsyncEngine):
    await init_models(db_engine)
    yield async_session
    await drop_models(db_engine)


@pytest_asyncio.fixture
async def db(db_engine: AsyncEngine, db_sessionmaker: async_sessionmaker[AsyncSession]):
    async with db_sessionmaker() as session:
        yield session


@pytest.fixture
def client(db: AsyncSession):
    def db_session_override():
        yield db

    app.dependency_overrides[db_session] = db_session_override
    yield TestClient(app, headers={settings.API_KEY_HEADER: settings.API_KEY_SECRET})
    app.dependency_overrides.clear()


@pytest.fixture
async def aclient(db_sessionmaker: async_sessionmaker[AsyncSession]):
    async def db_session_override():
        async with db_sessionmaker() as session:
            yield session

    app.dependency_overrides[db_session] = db_session_override
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app),
        headers={settings.API_KEY_HEADER: settings.API_KEY_SECRET},
    ) as client:
        yield client
    app.dependency_overrides.clear()
