"""
Settings — Cấu hình ứng dụng đọc từ .env qua pydantic-settings.

DATABASE_URL (sync, psycopg2) dành cho Alembic và backward-compat.
DATABASE_URL_ASYNC (asyncpg) dành cho FastAPI async session.
"""

from typing import Optional

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────────────
    ENV: str = "development"
    DEBUG: bool = True

    # ── Database components ──────────────────────────────────────────
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres_secure_pass_123"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "stock_crypto_db"

    # Cho phép override toàn bộ URL nếu cần (ưu tiên nếu đặt trong .env)
    DATABASE_URL: Optional[str] = None
    DATABASE_URL_ASYNC: Optional[str] = None

    # ── Redis ────────────────────────────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── MLflow ───────────────────────────────────────────────────────
    MLFLOW_TRACKING_URI: str = "http://localhost:5000"

    # ── API Security ─────────────────────────────────────────────────
    API_KEY_SECRET: str = "generate_a_secure_long_random_string_here"
    RATE_LIMIT_PER_MINUTE: int = 60

    # ── Data Sources ─────────────────────────────────────────────────
    BINANCE_API_KEY: Optional[str] = None
    BINANCE_API_SECRET: Optional[str] = None

    # ── Error Tracking ───────────────────────────────────────────────
    SENTRY_DSN: Optional[str] = None

    # ── Pydantic-settings ────────────────────────────────────────────
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Computed URLs ────────────────────────────────────────────────

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url_sync(self) -> str:
        """URL đồng bộ (psycopg2) — dùng cho Alembic và sync compat."""
        if self.DATABASE_URL is not None:
            return self.DATABASE_URL
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url_async(self) -> str:
        """URL bất đồng bộ (asyncpg) — dùng cho FastAPI async session."""
        if self.DATABASE_URL_ASYNC is not None:
            return self.DATABASE_URL_ASYNC
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


# Singleton instance
settings = Settings()
