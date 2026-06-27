"""
Alembic Environment Configuration
===================================
Đọc DATABASE_URL từ shared.config.settings (pydantic-settings).
Hỗ trợ cả offline mode (sinh SQL ra file) và online mode (chạy trực tiếp trên DB).
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Đảm bảo project root nằm trong sys.path để import shared.*
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from shared.config.settings import settings  # noqa: E402
from shared.db.base import Base  # noqa: E402

# ---------- Alembic Config ----------

config = context.config

# Override sqlalchemy.url bằng giá trị từ .env / settings (sync URL cho Alembic)
config.set_main_option("sqlalchemy.url", settings.database_url_sync)

# Cấu hình logging từ alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata cho autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Chạy migration ở chế độ offline — sinh ra SQL script mà không cần kết nối DB.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Chạy migration ở chế độ online — kết nối DB thực và thực thi trực tiếp.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
