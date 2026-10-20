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


def test_ingestion_covers_every_dataset_asset() -> None:
    """Periodic ingestion pulls all 25 assets of configs/group_dataset.json."""
    import json
    from pathlib import Path

    contract = json.loads(
        (
            Path(__file__).resolve().parents[3] / "configs" / "group_dataset.json"
        ).read_text(encoding="utf-8")
    )
    schedule = celery_app.conf.beat_schedule
    crypto = {s.replace("/", "") for s in schedule["ingest-crypto-hourly"]["args"][0]}
    stocks = set(schedule["ingest-stocks-daily"]["args"][0])
    assert crypto == set(contract["assets"]["crypto"]["symbols"])
    assert stocks == set(contract["assets"]["stock"]["symbols"])
    assert (
        schedule["ingest-crypto-daily"]["args"][0]
        == schedule["ingest-crypto-hourly"]["args"][0]
    )
