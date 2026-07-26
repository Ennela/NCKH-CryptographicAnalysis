"""
Pipeline processing module — Làm sạch và lưu trữ dữ liệu OHLCV.

Cung cấp hàm ``run_clean_and_store`` thực hiện:
1. Đọc dữ liệu mới từ ``market.ohlcv_raw``.
2. Gọi bộ làm sạch ``cleaning.py``.
3. Upsert dữ liệu sạch vào ``market.ohlcv``.
4. Ghi kết quả kiểm tra vào ``ops.data_quality_check``.

Idempotent và an toàn transaction sử dụng SQLAlchemy SAVEPOINTs.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.ingestion.app.cleaning import clean_ohlcv
from shared.db.repositories.market_repo import (
    get_last_ohlcv_ts,
    record_dq_check,
    upsert_ohlcv,
)

logger = logging.getLogger(__name__)


def run_clean_and_store(
    db: Session,
    symbol_id: int,
    timeframe: str,
) -> dict[str, Any]:
    """Chạy quy trình làm sạch dữ liệu và lưu trữ cho symbol + timeframe cụ thể.

    Hàm thực hiện đọc các bản ghi thô mới nhất từ ``market.ohlcv_raw`` chưa được
    đưa vào ``market.ohlcv``, tiến hành chuẩn hóa múi giờ, lọc trùng, điền nến
    thiếu, phát hiện outlier, và lưu trữ dữ liệu sạch. Ghi kết quả thống kê
    vào bảng ``ops.data_quality_check``.

    Sử dụng database SAVEPOINT (nested transaction) để đảm bảo an toàn dữ liệu,
    tự động rollback nếu xảy ra lỗi giữa batch.

    Args:
        db: Sync SQLAlchemy session.
        symbol_id: Khóa ngoại trỏ đến ``market.symbol.id``.
        timeframe: Khung thời gian cần xử lý (e.g. '1d', '1h').

    Returns:
        Dict chứa báo cáo kết quả xử lý (CleaningReport).
    """
    logger.info(
        "Bắt đầu pipeline clean & store cho symbol_id=%d, timeframe=%s",
        symbol_id,
        timeframe,
    )

    try:
        # Sử dụng savepoint (nested transaction) để cô lập lỗi trong batch này
        with db.begin_nested():
            # 1. Truy vấn asset_class của symbol
            symbol_row = db.execute(
                text("SELECT asset_class FROM market.symbol WHERE id = :id"),
                {"id": symbol_id},
            ).fetchone()

            if not symbol_row:
                raise ValueError(f"Không tìm thấy symbol có id={symbol_id}")
            asset_class = symbol_row[0]

            # 2. Tìm mốc thời gian đã xử lý gần nhất trong market.ohlcv
            last_ts = get_last_ohlcv_ts(db, symbol_id, timeframe)

            # 3. Đọc dữ liệu mới từ market.ohlcv_raw
            if last_ts is not None:
                query = text("""
                    SELECT symbol_id, timeframe, ts, open, high, low, close, volume, source, ingested_at
                    FROM market.ohlcv_raw
                    WHERE symbol_id = :symbol_id AND timeframe = :timeframe AND ts > :last_ts
                    ORDER BY ts ASC
                """)
                params = {
                    "symbol_id": symbol_id,
                    "timeframe": timeframe,
                    "last_ts": last_ts,
                }
            else:
                query = text("""
                    SELECT symbol_id, timeframe, ts, open, high, low, close, volume, source, ingested_at
                    FROM market.ohlcv_raw
                    WHERE symbol_id = :symbol_id AND timeframe = :timeframe
                    ORDER BY ts ASC
                """)
                params = {"symbol_id": symbol_id, "timeframe": timeframe}

            raw_rows = db.execute(query, params).fetchall()

            if not raw_rows:
                logger.info(
                    "Không tìm thấy bản ghi mới nào cho symbol_id=%d, timeframe=%s",
                    symbol_id,
                    timeframe,
                )
                return {
                    "input_rows": 0,
                    "output_rows": 0,
                    "duplicates_removed": 0,
                    "missing_filled": 0,
                    "outliers_flagged": 0,
                    "status": "no_new_data",
                }

            # 4. Chuyển đổi list row thành pandas DataFrame để cleaning
            df = pd.DataFrame([dict(row._mapping) for row in raw_rows])

            # 5. Gọi module cleaning làm sạch dữ liệu
            cleaned_df, report = clean_ohlcv(df, asset_class=asset_class)

            if cleaned_df.empty:
                logger.warning(
                    "DataFrame rỗng sau khi làm sạch cho symbol_id=%d, timeframe=%s",
                    symbol_id,
                    timeframe,
                )
                return report.to_dict()

            # 6. Chuẩn hóa lại định dạng dữ liệu cho SQLAlchemy insert
            clean_rows = []
            for _, row in cleaned_df.iterrows():
                ts_val = row["ts"]
                if isinstance(ts_val, pd.Timestamp):
                    ts_val = ts_val.to_pydatetime()

                clean_rows.append(
                    {
                        "symbol_id": int(row["symbol_id"]),
                        "timeframe": str(row["timeframe"]),
                        "ts": ts_val,
                        "open": Decimal(str(row["open"])),
                        "high": Decimal(str(row["high"])),
                        "low": Decimal(str(row["low"])),
                        "close": Decimal(str(row["close"])),
                        "volume": Decimal(str(row["volume"])),
                        "vwap": (
                            Decimal(str(row["vwap"]))
                            if "vwap" in row and pd.notna(row["vwap"])
                            else None
                        ),
                        "trade_count": (
                            int(row["trade_count"])
                            if "trade_count" in row and pd.notna(row["trade_count"])
                            else None
                        ),
                    }
                )

            # 7. Upsert vào market.ohlcv
            upsert_ohlcv(db, clean_rows)

            # 8. Ghi log Data Quality Check
            ts_start = min(r["ts"] for r in clean_rows)
            ts_end = max(r["ts"] for r in clean_rows)

            # Passed nếu không phát hiện outlier
            passed = bool(report.outliers_flagged == 0)

            record_dq_check(
                db=db,
                symbol_id=symbol_id,
                timeframe=timeframe,
                check_name="cleaning_pipeline",
                passed=passed,
                ts_start=ts_start,
                ts_end=ts_end,
                detail=report.to_dict(),
            )

            logger.info(
                "Xử lý thành công %d/%d bản ghi cho symbol_id=%d (%s)",
                report.output_rows,
                report.input_rows,
                symbol_id,
                timeframe,
            )
            return report.to_dict()

    except Exception as e:
        logger.error(
            "Gặp lỗi trong quy trình clean & store cho symbol_id=%d, timeframe=%s: %s",
            symbol_id,
            timeframe,
            str(e),
        )
        raise e
