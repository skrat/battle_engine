import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlmodel import StaticPool
from sqlmodel.ext.asyncio.session import AsyncSession

from battle_engine.db import drop_models, get_engine, init_models
from battle_engine.main import app, db_session

TEST_DB = "test.sqlite3"


@pytest_asyncio.fixture(scope="function")
async def db():
    engine = get_engine(
        f"sqlite+aiosqlite:///{TEST_DB}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with AsyncSession(engine) as session:
        await init_models(engine)
        yield session
        await drop_models(engine)
        await session.close()


@pytest.fixture(scope="function")
def client(db: AsyncSession):
    def db_session_override():
        yield db

    app.dependency_overrides[db_session] = db_session_override
    yield TestClient(app)
    app.dependency_overrides.clear()
