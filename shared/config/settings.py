import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # App Settings
    ENV: str = "development"
    DEBUG: bool = True
    
    # Database
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres_secure_pass_123@localhost:5432/stock_crypto_db"

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_URL: str = "redis://localhost:6379/0"

    # MLflow
    MLFLOW_TRACKING_URI: str = "http://localhost:5000"

    # API Security
    API_KEY_SECRET: str = "generate_a_secure_long_random_string_here"
    RATE_LIMIT_PER_MINUTE: int = 60

    # APIs Keys
    BINANCE_API_KEY: Optional[str] = None
    BINANCE_API_SECRET: Optional[str] = None

    # Error Tracking
    SENTRY_DSN: Optional[str] = None

    # Configuration source - loads from .env if present
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Instantiate singleton
settings = Settings()
