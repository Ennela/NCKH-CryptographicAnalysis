import os
import pytest
from collections.abc import AsyncGenerator, Generator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Force environment variables for the test database
os.environ["POSTGRES_DB"] = "stock_crypto_db_test"
os.environ["DATABASE_URL"] = (
    "postgresql+psycopg2://postgres:postgres_secure_pass_123@localhost:5432/stock_crypto_db_test"
)
os.environ["DATABASE_URL_ASYNC"] = (
    "postgresql+asyncpg://postgres:postgres_secure_pass_123@localhost:5432/stock_crypto_db_test"
)

from shared.config.settings import settings
from shared.db.session import SyncSessionLocal, AsyncSessionLocal


@pytest.fixture(scope="session", autouse=True)
def setup_test_db() -> None:
    """
    Create the test database and run init.sql once per session.
    """
    # 1. Connect to postgres database to check/create stock_crypto_db_test
    conn = psycopg2.connect(
        dbname="postgres",
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM pg_database WHERE datname='stock_crypto_db_test'")
    exists = cursor.fetchone()
    if not exists:
        cursor.execute("CREATE DATABASE stock_crypto_db_test")
    cursor.close()
    conn.close()

    # 2. Run the initialization SQL script (init.sql) on the test DB
    sql_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "infra", "postgres", "init.sql"
    )
    with open(sql_path, "r", encoding="utf-8") as f:
        init_sql = f.read()

    test_conn = psycopg2.connect(
        dbname="stock_crypto_db_test",
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    test_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    test_cursor = test_conn.cursor()
    test_cursor.execute(init_sql)
    test_cursor.close()
    test_conn.close()


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """
    Sync database session fixture.
    Runs inside a transaction and rolls back after the test completes.
    """
    session = SyncSessionLocal()
    session.begin()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
async def async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Async database session fixture.
    Runs inside a transaction and rolls back after the test completes.
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            try:
                yield session
            finally:
                await session.rollback()


@pytest.fixture(autouse=True)
async def cleanup_async_engine():
    yield
    from shared.db.session import async_engine

    await async_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def dispose_engines(setup_test_db) -> Generator[None, None, None]:
    yield
    from shared.db.session import sync_engine

    sync_engine.dispose()
