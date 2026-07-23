"""
Celery Beat Scheduler Configuration Builder — Tạo beat schedule động.

Xác định lịch chạy làm sạch dữ liệu (clean_and_store_task) cho tất cả symbols active:
- Crypto (BINANCE): định kỳ hàng giờ, được stagger (phân bổ) theo các phút khác nhau
  để tránh DB lock / nghẽn.
- VN Stocks (HOSE): định kỳ hàng ngày lúc 16:00 giờ VN (09:00 UTC), cũng được stagger phút.

Cấu hình lịch chạy (daily hour, minute, stagger interval) thông qua .env/BaseSettings.
"""

from __future__ import annotations

import logging
from celery.schedules import crontab
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import text

from shared.db.session import SessionLocal

logger = logging.getLogger(__name__)


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Scheduler Configuration Settings                                       ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


class SchedulerSettings(BaseSettings):
    """Cấu hình Celery Beat Scheduler đọc từ biến môi trường hoặc .env."""

    # Daily clean task VN Stock hour (16:00 VN Time = 09:00 UTC)
    CLEAN_STOCK_HOUR_UTC: int = 9

    # Stagger interval in minutes
    CLEAN_STAGGER_INTERVAL_MINS: int = 2

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Helpers                                                                ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


def get_active_symbols() -> list[dict]:
    """Truy vấn danh sách symbol có status='active' từ database."""
    db = SessionLocal()
    try:
        res = db.execute(
            text(
                "SELECT id, ticker, asset_class FROM market.symbol "
                "WHERE status = 'active'"
            )
        ).fetchall()
        return [dict(r._mapping) for r in res]
    except Exception as e:
        logger.warning(
            "Không thể truy vấn danh sách active symbols từ database: %s. "
            "Celery Beat sẽ không cấu hình được dynamic cleaning tasks.",
            e,
        )
        return []
    finally:
        db.close()


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Beat Schedule Generator                                                ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


def generate_beat_schedule() -> dict:
    """Tự động sinh cấu hình Celery Beat schedule cho các tasks làm sạch dữ liệu.

    Đọc các active symbols từ database, tự động gán lịch chạy:
    - Crypto (1h): crontab(minute=stagger_minute)
    - Stock (1d): crontab(day_of_week='1-5', hour=stagger_hour, minute=stagger_minute)

    Returns:
        Dict tương thích với celery_app.conf.beat_schedule.
    """
    settings = SchedulerSettings()
    active_symbols = get_active_symbols()

    schedule = {}
    crypto_count = 0
    stock_count = 0

    for sym in active_symbols:
        symbol_id = sym["id"]
        ticker = sym["ticker"]
        asset_class = sym["asset_class"]

        if asset_class == "crypto":
            # Phân bổ phút chạy crypto: vd 0, 2, 4, 6...
            minute = (crypto_count * settings.CLEAN_STAGGER_INTERVAL_MINS) % 60
            schedule[f"clean-store-crypto-{ticker}-hourly"] = {
                "task": "tasks.clean_and_store_task",
                "schedule": crontab(minute=minute),
                "args": (symbol_id, "1h"),
            }
            crypto_count += 1

        elif asset_class == "stock":
            # Phân bổ phút/giờ chạy stock: vd 09:00, 09:02, 09:04...
            total_minutes = stock_count * settings.CLEAN_STAGGER_INTERVAL_MINS
            hour_offset = total_minutes // 60
            minute = total_minutes % 60
            hour = (settings.CLEAN_STOCK_HOUR_UTC + hour_offset) % 24

            schedule[f"clean-store-stock-{ticker}-daily"] = {
                "task": "tasks.clean_and_store_task",
                "schedule": crontab(day_of_week="1-5", hour=hour, minute=minute),
                "args": (symbol_id, "1d"),
            }
            stock_count += 1

    logger.info(
        "Đã sinh cấu hình Beat Schedule: %d crypto tasks, %d stock tasks "
        "(Stagger interval = %d mins)",
        crypto_count,
        stock_count,
        settings.CLEAN_STAGGER_INTERVAL_MINS,
    )
    return schedule
