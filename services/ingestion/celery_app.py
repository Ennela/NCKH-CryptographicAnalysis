import logging

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init
from shared.config.settings import settings
from shared.db.session import sync_engine

try:
    from app.scheduler import SchedulerSettings, generate_beat_schedule
except ImportError:
    from services.ingestion.app.scheduler import (
        SchedulerSettings,
        generate_beat_schedule,
    )

# Initialize Celery app
celery_app = Celery(
    "ingestion_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["tasks"],
)


@worker_process_init.connect
def reset_db_pool_after_fork(**_kwargs: object) -> None:
    """Give each forked worker process its own database connections.

    The prefork pool forks children after this module (and shared.db.session)
    is imported, so without this every child inherits the parent's pooled
    psycopg2 connections and concurrent tasks interleave on the same socket
    ("result object does not return rows", lost savepoints, jobs stuck in
    'running'). dispose(close=False) drops the inherited pool without closing
    the parent's sockets; the child then opens fresh connections on demand.
    """
    sync_engine.dispose(close=False)


# Celery Configuration
celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
)

# Symbol lists come from config (INGEST_CRYPTO_SYMBOLS / INGEST_STOCK_SYMBOLS),
# not from this file — AGENTS.md §5: no hardcoded symbols.
scheduler_settings = SchedulerSettings()

# Configure Celery Beat Periodic Schedules
celery_app.conf.beat_schedule = {
    # 1. Ingest Cryptocurrencies (Hourly: every hour at minute 5)
    "ingest-crypto-hourly": {
        "task": "tasks.ingest_crypto_task",
        "schedule": crontab(minute=5),
        "args": (scheduler_settings.INGEST_CRYPTO_SYMBOLS, "1h"),
    },
    # 2. Ingest Cryptocurrencies (Daily: every day at 00:10 UTC)
    "ingest-crypto-daily": {
        "task": "tasks.ingest_crypto_task",
        "schedule": crontab(hour=0, minute=10),
        "args": (scheduler_settings.INGEST_CRYPTO_SYMBOLS, "1d"),
    },
    # 3. Ingest Vietnamese Stocks (Daily: Monday to Friday at 10:00 UTC / 17:00 VN Time)
    "ingest-stocks-daily": {
        "task": "tasks.ingest_stocks_task",
        "schedule": crontab(day_of_week="1-5", hour=10, minute=0),
        "args": (scheduler_settings.INGEST_STOCK_SYMBOLS, "1d"),
    },
}

# Tích hợp dynamic cleaning schedules từ scheduler.py
try:
    cleaning_schedule = generate_beat_schedule()
    celery_app.conf.beat_schedule.update(cleaning_schedule)
except Exception as exc:
    logging.getLogger("celery").warning(
        "Không thể tải dynamic cleaning schedules cho Celery Beat: %s", exc
    )
