"""
Local conftest.py for services/ingestion/tests.
Configures test DB and defines session fixtures independently to avoid circular import issues.
"""

from __future__ import annotations

import os
import pytest
from collections.abc import Generator
from sqlalchemy.orm import Session
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Set test environment database configuration
os.environ["POSTGRES_DB"] = "stock_crypto_db_test"
os.environ["DATABASE_URL"] = (
    "postgresql+psycopg2://postgres:postgres_secure_pass_123@localhost:5432/stock_crypto_db_test"
)
os.environ["DATABASE_URL_ASYNC"] = (
    "postgresql+asyncpg://postgres:postgres_secure_pass_123@localhost:5432/stock_crypto_db_test"
)

from shared.config.settings import settings
from shared.db.session import SyncSessionLocal, sync_engine


@pytest.fixture(scope="session", autouse=True)
def setup_test_db() -> None:
    """Khởi tạo database test và apply init.sql."""
    # 1. Connect tới postgres DB mặc định để tạo DB test
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

    # 2. Run init.sql
    sql_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "infra", "postgres", "init.sql",
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
    """Sync session fixture chạy trong transaction và rollback sau mỗi test."""
    session = SyncSessionLocal()
    session.begin()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="session", autouse=True)
def dispose_engines(setup_test_db) -> Generator[None, None, None]:
    yield
    sync_engine.dispose()
