import pytest
from pydantic import ValidationError
from shared.config.settings import Settings


def test_load_env_example(monkeypatch) -> None:
    """Kiểm tra load cấu hình từ .env.example thành công và đúng giá trị mẫu."""
    monkeypatch.delenv("POSTGRES_DB", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_ASYNC", raising=False)

    settings = Settings(_env_file=".env.example")
    assert settings.ENV == "development"
    assert settings.POSTGRES_DB == "stock_crypto_db"
    assert settings.POSTGRES_PORT == 5432
    assert settings.REDIS_PORT == 6379


def test_dsn_drivers(monkeypatch) -> None:
    """Kiểm tra computed sync_dsn và async_dsn sinh ra đúng driver tương ứng."""
    monkeypatch.delenv("POSTGRES_DB", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_ASYNC", raising=False)

    settings = Settings(_env_file=".env.example")

    # Driver cho sync session phải là psycopg2
    assert "postgresql+psycopg2://" in settings.database_url_sync

    # Driver cho async session phải là asyncpg
    assert "postgresql+asyncpg://" in settings.database_url_async


def test_validation_errors() -> None:
    """Kiểm tra Pydantic quăng lỗi ValidationError khi truyền sai kiểu dữ liệu bắt buộc."""
    with pytest.raises(ValidationError):
        # POSTGRES_PORT phải là kiểu int
        Settings(POSTGRES_PORT="not_an_integer")  # type: ignore


def test_required_fields_validation() -> None:
    """Kiểm tra báo lỗi rõ khi thiếu hoặc truyền sai/None cho biến bắt buộc."""
    with pytest.raises(ValidationError):
        Settings(POSTGRES_USER=None)  # type: ignore
    with pytest.raises(ValidationError):
        Settings(POSTGRES_PASSWORD=None)  # type: ignore
    with pytest.raises(ValidationError):
        Settings(POSTGRES_DB=None)  # type: ignore
