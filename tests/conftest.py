import httpx2
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.asyncio.engine import AsyncEngine
from sqlmodel import StaticPool
from sqlmodel.ext.asyncio.session import AsyncSession

from battle_engine.db import drop_models, init_models
from battle_engine.main import app, db_session

TEST_DB_URL = "sqlite+aiosqlite:///test.sqlite3"


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    engine = create_async_engine(
        TEST_DB_URL,
        # echo=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_sessionmaker(db_engine: AsyncEngine):
    await init_models(db_engine)
    yield async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    await drop_models(db_engine)


@pytest_asyncio.fixture(scope="function")
async def db(db_engine: AsyncEngine, db_sessionmaker: async_sessionmaker[AsyncSession]):
    async with db_sessionmaker() as session:
        yield session


@pytest.fixture(scope="function")
def client(db: AsyncSession):
    def db_session_override():
        yield db

    app.dependency_overrides[db_session] = db_session_override
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
async def aclient(db_sessionmaker: async_sessionmaker[AsyncSession]):
    async def db_session_override():
        async with db_sessionmaker() as session:
            yield session

    app.dependency_overrides[db_session] = db_session_override
    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app)) as client:
        yield client
    app.dependency_overrides.clear()
