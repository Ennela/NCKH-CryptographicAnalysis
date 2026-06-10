from celery import Celery
from celery.schedules import crontab
from shared.config.settings import settings

# Initialize Celery app
celery_app = Celery(
    "ingestion_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["tasks"],
)

# Celery Configuration
celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
)

# Configure Celery Beat Periodic Schedules
celery_app.conf.beat_schedule = {
    # 1. Ingest Cryptocurrencies (Hourly: every hour at minute 5)
    "ingest-crypto-hourly": {
        "task": "tasks.ingest_crypto_task",
        "schedule": crontab(minute=5),
        "args": (["BTC/USDT", "ETH/USDT"], "1h"),
    },
    # 2. Ingest Cryptocurrencies (Daily: every day at 00:10 UTC)
    "ingest-crypto-daily": {
        "task": "tasks.ingest_crypto_task",
        "schedule": crontab(hour=0, minute=10),
        "args": (["BTC/USDT", "ETH/USDT"], "1d"),
    },
    # 3. Ingest Vietnamese Stocks (Daily: Monday to Friday at 10:00 UTC / 17:00 VN Time)
    "ingest-stocks-daily": {
        "task": "tasks.ingest_stocks_task",
        "schedule": crontab(day_of_week="1-5", hour=10, minute=0),
        "args": (["FPT", "VCB", "MSN"], "1d"),
    },
}
