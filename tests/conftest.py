import base64
import json
import os
import secrets

# Must precede any app import — app/database.py creates the SQLAlchemy engine
# at module load time from settings.DATABASE_URL.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://tulsajobspot:tulsajobspot@localhost:5432/tulsajobspot_test",
)

import pytest
from httpx import AsyncClient, ASGITransport
from itsdangerous import TimestampSigner
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

import app.models  # ensures all ORM relationships are registered
from app.models.company import Company
from app.models.reference import CompanyType
from app.models.user import User
from app.database import get_db

TEST_DATABASE_URL = os.environ["DATABASE_URL"]


@pytest.fixture(scope="session")
async def engine():
    # Schema comes from the cloned production DB — no setup/teardown needed.
    # Per-test rollback (SAVEPOINT) ensures writes never persist between tests.
    _engine = create_async_engine(TEST_DATABASE_URL)
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


@pytest.fixture
def make_session_cookie():
    """Return a callable that builds a signed Starlette session cookie."""
    from app.config import settings
    def _make(data: dict) -> str:
        payload = base64.b64encode(json.dumps(data).encode()).decode()
        return TimestampSigner(settings.SECRET_KEY).sign(payload).decode()
    return _make


@pytest.fixture
async def staff_user(db):
    """An admin user (is_staff == True)."""
    u = User(
        email=f"staff_{secrets.token_hex(4)}@example.com",
        full_name="Staff User",
        oauth_provider="test",
        oauth_subject=f"staff-{secrets.token_hex(8)}",
        is_admin=True,
    )
    db.add(u)
    await db.flush()
    return u


@pytest.fixture
async def company_type(db):
    """A minimal active CompanyType for use in company fixtures."""
    ct = CompanyType(name=f"_test_{secrets.token_hex(6)}", is_active=True)
    db.add(ct)
    await db.flush()
    return ct


@pytest.fixture
async def company(db, company_type):
    """An approved, active company."""
    c = Company(
        slug=f"test-co-{secrets.token_hex(6)}",
        common_name="Test Company",
        company_type=company_type.id,
        approved=True,
        defunct=False,
    )
    db.add(c)
    await db.flush()
    return c
