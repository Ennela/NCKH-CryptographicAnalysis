"""
Tests kiểm tra kết nối DB và tính đúng đắn ORM models.

Yêu cầu integration tests:
- PostgreSQL + TimescaleDB đang chạy (docker-compose up postgres).
- .env hoặc biến môi trường POSTGRES_* đã cấu hình đúng.

Chạy:
    pytest tests/test_db_connection.py -v
"""

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from shared.config.settings import settings
from shared.db.base import Base
from shared.db.session import SyncSessionLocal


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Sanity tests — không cần DB chạy                                      ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


class TestModelImports:
    """Kiểm tra tất cả ORM models import được và đúng schema.

    Chỉ 9 models có ORM class (bảng lookup/metadata).
    Bảng hypertable (ohlcv, prediction, job_log, …) không có ORM model.
    """

    def test_import_all_models(self) -> None:
        """Import tất cả 9 models từ shared.db.models mà không lỗi."""
        from shared.db.models import (
            BacktestResult,
            BacktestRun,
            DataQualityCheck,
            Exchange,
            FeatureSet,
            MLModel,
            ModelMetric,
            ModelVersion,
            Symbol,
        )

        all_models = [
            Exchange,
            Symbol,
            FeatureSet,
            MLModel,
            ModelVersion,
            ModelMetric,
            BacktestRun,
            BacktestResult,
            DataQualityCheck,
        ]
        for model in all_models:
            assert issubclass(model, Base), f"{model.__name__} không kế thừa Base"

    def test_market_schema(self) -> None:
        """Models market phải có schema='market'."""
        from shared.db.models import Exchange, Symbol

        for model in [Exchange, Symbol]:
            schema = model.__table__.schema
            assert schema == "market", (
                f"{model.__name__}.__table__.schema = {schema!r}, expected 'market'"
            )

    def test_ml_schema(self) -> None:
        """Models ml phải có schema='ml'."""
        from shared.db.models import (
            BacktestResult,
            BacktestRun,
            FeatureSet,
            MLModel,
            ModelMetric,
            ModelVersion,
        )

        for model in [
            FeatureSet,
            MLModel,
            ModelVersion,
            ModelMetric,
            BacktestRun,
            BacktestResult,
        ]:
            schema = model.__table__.schema
            assert schema == "ml", (
                f"{model.__name__}.__table__.schema = {schema!r}, expected 'ml'"
            )

    def test_ops_schema(self) -> None:
        """Models ops phải có schema='ops'."""
        from shared.db.models import DataQualityCheck

        for model in [DataQualityCheck]:
            schema = model.__table__.schema
            assert schema == "ops", (
                f"{model.__name__}.__table__.schema = {schema!r}, expected 'ops'"
            )

    def test_hypertable_models_not_in_module(self) -> None:
        """Bảng hypertable KHÔNG nên có ORM model trong shared.db.models."""
        import shared.db.models as models_module

        for name in ["Ohlcv", "OhlcvRaw", "FeatureValue", "Prediction", "JobLog"]:
            assert not hasattr(models_module, name), (
                f"shared.db.models KHÔNG nên có class {name} (hypertable — dùng raw SQL)"
            )


class TestSettingsUrls:
    """Kiểm tra settings tạo URL đúng format."""

    def test_sync_url_contains_psycopg2(self) -> None:
        url = settings.database_url_sync
        assert "psycopg2" in url or "postgresql://" in url

    def test_async_url_contains_asyncpg(self) -> None:
        url = settings.database_url_async
        assert "asyncpg" in url

    def test_urls_not_hardcoded_password_in_code(self) -> None:
        """Settings phải build URL từ components, không hardcode."""
        # Nếu không đặt DATABASE_URL trong .env, URL phải được build từ POSTGRES_*
        s = settings
        expected_host = s.POSTGRES_HOST
        assert expected_host in s.database_url_sync
        assert expected_host in s.database_url_async


class TestNoCreateAll:
    """Đảm bảo không có create_all() trong session module."""

    def test_session_module_no_create_all(self) -> None:
        import ast
        import inspect

        import shared.db.session as session_module

        source = inspect.getsource(session_module)
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "create_all":
                    pytest.fail(
                        "shared.db.session chứa lời gọi create_all() "
                        f"ở dòng {node.lineno} — KHÔNG ĐƯỢC PHÉP"
                    )


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Integration tests — cần DB chạy                                       ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


@pytest.mark.integration
class TestSyncConnection:
    """Test kết nối sync — rollback sau mỗi test."""

    def test_connect_and_query(self) -> None:
        """Kết nối DB sync và chạy SELECT 1."""
        db: Session = SyncSessionLocal()
        try:
            result = db.execute(sa.text("SELECT 1 AS x"))
            row = result.fetchone()
            assert row is not None
            assert row[0] == 1
        finally:
            db.rollback()
            db.close()

    def test_schema_exists(self) -> None:
        """Kiểm tra 3 schema market/ml/ops tồn tại."""
        db: Session = SyncSessionLocal()
        try:
            result = db.execute(
                sa.text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name IN ('market', 'ml', 'ops') "
                    "ORDER BY schema_name"
                )
            )
            schemas = [row[0] for row in result.fetchall()]
            assert "market" in schemas, "Schema 'market' không tồn tại"
            assert "ml" in schemas, "Schema 'ml' không tồn tại"
            assert "ops" in schemas, "Schema 'ops' không tồn tại"
        finally:
            db.rollback()
            db.close()

    def test_hypertables_exist(self) -> None:
        """Kiểm tra các bảng hypertable tồn tại (sync)."""
        db: Session = SyncSessionLocal()
        try:
            result = db.execute(
                sa.text("""
                    SELECT table_schema, table_name 
                    FROM information_schema.tables 
                    WHERE (table_schema = 'market' AND table_name = 'ohlcv')
                       OR (table_schema = 'ml' AND table_name = 'feature_value')
                       OR (table_schema = 'ml' AND table_name = 'prediction')
                       OR (table_schema = 'ops' AND table_name = 'job_log')
                """)
            )
            tables = {(row[0], row[1]) for row in result.fetchall()}
            assert ("market", "ohlcv") in tables, "Table market.ohlcv khong ton tai"
            assert ("ml", "feature_value") in tables, (
                "Table ml.feature_value khong ton tai"
            )
            assert ("ml", "prediction") in tables, "Table ml.prediction khong ton tai"
            assert ("ops", "job_log") in tables, "Table ops.job_log khong ton tai"
        finally:
            db.rollback()
            db.close()


@pytest.mark.integration
class TestAsyncConnection:
    """Test kết nối async — rollback sau mỗi test."""

    @pytest.mark.asyncio
    async def test_connect_and_query(self) -> None:
        """Kết nối DB async và chạy SELECT 1."""
        from shared.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            result = await session.execute(sa.text("SELECT 1 AS x"))
            row = result.fetchone()
            assert row is not None
            assert row[0] == 1
            await session.rollback()

    @pytest.mark.asyncio
    async def test_schema_exists(self) -> None:
        """Kiểm tra 3 schema market/ml/ops tồn tại (async)."""
        from shared.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                sa.text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name IN ('market', 'ml', 'ops') "
                    "ORDER BY schema_name"
                )
            )
            schemas = [row[0] for row in result.fetchall()]
            assert "market" in schemas
            assert "ml" in schemas
            assert "ops" in schemas
            await session.rollback()

    @pytest.mark.asyncio
    async def test_hypertables_exist(self) -> None:
        """Kiểm tra các bảng hypertable tồn tại (async)."""
        from shared.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                sa.text("""
                    SELECT table_schema, table_name 
                    FROM information_schema.tables 
                    WHERE (table_schema = 'market' AND table_name = 'ohlcv')
                       OR (table_schema = 'ml' AND table_name = 'feature_value')
                       OR (table_schema = 'ml' AND table_name = 'prediction')
                       OR (table_schema = 'ops' AND table_name = 'job_log')
                """)
            )
            tables = {(row[0], row[1]) for row in result.fetchall()}
            assert ("market", "ohlcv") in tables
            assert ("ml", "feature_value") in tables
            assert ("ml", "prediction") in tables
            assert ("ops", "job_log") in tables
            await session.rollback()
