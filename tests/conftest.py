import os

# Must precede any app import — app/database.py creates the SQLAlchemy engine
# at module load time from settings.DATABASE_URL.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://tulsajobspot:tulsajobspot@localhost:5432/tulsajobspot_test",
)

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

import app.models  # registers all ORM models with Base.metadata
from app.models.base import Base
from app.models.user import User
from app.database import get_db

TEST_DATABASE_URL = os.environ["DATABASE_URL"]


@pytest.fixture(scope="session")
async def engine():
    _engine = create_async_engine(TEST_DATABASE_URL)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield _engine
    await _engine.dispose()


@pytest.fixture
async def db(engine):
    """Per-test DB session. All writes roll back after each test."""
    async with engine.connect() as conn:
        await conn.begin()
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
        yield session
        await session.close()
        await conn.rollback()


@pytest.fixture
async def user(db):
    """A plain authenticated user with no company role or staff flags."""
    u = User(
        email="test@example.com",
        full_name="Test User",
        oauth_provider="test",
        oauth_subject="test-subject-123",
    )
    db.add(u)
    await db.flush()
    return u


@pytest.fixture
async def client(db):
    """Async HTTP test client wired to the per-test DB session."""
    from app.main import app

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
