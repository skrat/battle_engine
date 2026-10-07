import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio.engine import AsyncEngine
from sqlmodel import StaticPool
from sqlmodel.ext.asyncio.session import AsyncSession

from battle_engine.db import drop_models, get_engine, init_models
from battle_engine.main import app, db_session

TEST_DB_URL = "sqlite+aiosqlite:///test.sqlite3"
# TEST_DB_URL = "postgresql+asyncpg://myuser:mypassword@localhost/mydatabase"


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    engine = get_engine(
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
        await session.close()


@pytest.fixture(scope="function")
def client(db: AsyncSession):
    def db_session_override():
        yield db

    app.dependency_overrides[db_session] = db_session_override
    yield TestClient(app)
    app.dependency_overrides.clear()
