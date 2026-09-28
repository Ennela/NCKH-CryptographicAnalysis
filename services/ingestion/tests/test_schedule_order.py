"""Beat schedule ordering: stock cleaning must run after stock ingestion."""

from __future__ import annotations

from services.ingestion.app.scheduler import SchedulerSettings
from services.ingestion.celery_app import celery_app


def test_stock_cleaning_runs_after_stock_ingestion() -> None:
    ingest = celery_app.conf.beat_schedule["ingest-stocks-daily"]["schedule"]
    (ingest_hour,) = ingest.hour
    clean_hour = SchedulerSettings().CLEAN_STOCK_HOUR_UTC
    # Cleaning before ingestion leaves the day's raw bars uncleaned until the
    # next trading day (the default was 09:00 UTC vs ingestion at 10:00 UTC).
    assert clean_hour > ingest_hour
