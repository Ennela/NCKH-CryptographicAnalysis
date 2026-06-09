"""
Database Session Management — Async (primary) + Sync (compat).

- ``get_async_session()``: FastAPI dependency cho async endpoints.
- ``get_db()``: FastAPI dependency cho sync endpoints + backward compat
  (binance_client, vnstock_client chạy trong background threads).
- ``SyncSessionLocal``: Session factory cho code sync legacy (client code).

LƯU Ý: Module này KHÔNG gọi ``create_all()``.
Schema chỉ được tạo bởi ``infra/postgres/init.sql`` + Alembic migrations.
"""

import logging
from collections.abc import AsyncGenerator, Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from shared.config.settings import settings

logger = logging.getLogger(__name__)

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Async Engine + Session (primary — dành cho FastAPI async endpoints)     ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

async_engine = create_async_engine(
    settings.database_url_async,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=settings.DEBUG,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency — yield một AsyncSession rồi tự đóng.

    Sử dụng::

        @router.get("/items")
        async def list_items(session: AsyncSession = Depends(get_async_session)):
            result = await session.execute(select(Item))
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as exc:
            logger.error("Async session error: %s", exc)
            await session.rollback()
            raise
        finally:
            await session.close()


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Sync Engine + Session (compat — cho Alembic, client code, legacy)      ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

sync_engine = create_engine(
    settings.database_url_sync,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=settings.DEBUG,
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False,
)

# Backward-compat aliases cho code cũ import `engine` và `SessionLocal`
engine = sync_engine
SessionLocal = SyncSessionLocal


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency — yield một sync Session rồi tự đóng.
    Dùng cho các endpoint/sync code chưa chuyển sang async.
    """
    db = SyncSessionLocal()
    try:
        yield db
    except Exception as exc:
        logger.error("Sync session error: %s", exc)
        db.rollback()
        raise
    finally:
        db.close()
