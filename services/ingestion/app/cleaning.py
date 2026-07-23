"""
Cleaning pipeline cho dữ liệu OHLCV.

Xử lý dữ liệu thô từ ``market.ohlcv_raw`` trước khi ghi vào ``market.ohlcv``:

1. Chuẩn hóa timezone → UTC.
2. Loại bản ghi trùng theo ``(symbol_id, timeframe, ts)``.
3. Forward-fill missing sessions cho cổ phiếu VN (giới hạn N phiên, chỉ dùng
   dữ liệu quá khứ — không look-ahead).
4. Phát hiện outlier bằng IQR trên ``close`` / ``volume`` theo từng
   ``(symbol_id, timeframe)``, gắn cờ ``is_outlier`` (không tự xóa).

Tuân thủ AGENTS.md:
- Config qua pydantic-settings (không hardcode).
- Type hint + docstring đầy đủ.
- Không dùng dữ liệu tương lai khi fill.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Offset giờ VN so với UTC: UTC+7
_VN_UTC_OFFSET_HOURS: int = 7


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Config & Report                                                        ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


class CleaningConfig(BaseSettings):
    """Cấu hình cleaning pipeline, đọc từ biến môi trường / ``.env``.

    Biến môi trường:
        CLEANING_FFILL_LIMIT — Số phiên liên tiếp tối đa được forward-fill.
        CLEANING_IQR_MULTIPLIER — Hệ số nhân IQR xác định ngưỡng outlier.
    """

    CLEANING_FFILL_LIMIT: int = 3
    CLEANING_IQR_MULTIPLIER: float = 1.5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@dataclass
class CleaningReport:
    """Báo cáo kết quả cleaning, dùng để ghi vào ``ops.data_quality_check``."""

    input_rows: int = 0
    output_rows: int = 0
    duplicates_removed: int = 0
    missing_filled: int = 0
    outliers_flagged: int = 0

    def to_dict(self) -> dict[str, int]:
        """Chuyển thành dict JSONB cho ``ops.data_quality_check.detail``."""
        return {
            "input_rows": self.input_rows,
            "output_rows": self.output_rows,
            "duplicates_removed": self.duplicates_removed,
            "missing_filled": self.missing_filled,
            "outliers_flagged": self.outliers_flagged,
        }


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Step 1: Chuẩn hóa timezone                                            ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


def normalize_timezone(
    df: pd.DataFrame,
    source: str,
    timeframe: str,
) -> pd.DataFrame:
    """Chuẩn hóa cột ``ts`` về UTC.

    - **binance**: đã UTC — chỉ gắn tzinfo nếu thiếu.
    - **vnstock daily** (``1d``/``1w``): adapter hiện tại gán ngày giao dịch VN
      dạng ``YYYY-MM-DD 00:00+00``. Với dữ liệu daily, *ngày* là đúng
      (chỉ khác múi giờ nội nhật) nên giữ nguyên.
    - **vnstock sub-daily** (``1h``, ``15m``, …): giờ VN bị gán nhầm UTC
      → trừ 7h để về UTC thật.

    Args:
        df: DataFrame chứa cột ``ts``.
        source: ``'binance'`` hoặc ``'vnstock'``.
        timeframe: ``'1d'``, ``'1h'``, v.v.

    Returns:
        DataFrame mới với ``ts`` đã chuẩn hóa.
    """
    df = df.copy()
    df["ts"] = pd.to_datetime(df["ts"], utc=True)

    # VNStock sub-daily: timestamp VN bị gán nhầm UTC → trừ 7h
    daily_or_weekly = timeframe in ("1d", "1w")
    if source == "vnstock" and not daily_or_weekly:
        df["ts"] = df["ts"] - pd.Timedelta(hours=_VN_UTC_OFFSET_HOURS)

    return df


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Step 2: Loại bản ghi trùng                                            ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


def deduplicate(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Loại bản ghi trùng theo ``(symbol_id, timeframe, ts)``.

    Nếu trùng, giữ bản ghi **mới nhất** (theo ``ingested_at`` nếu có,
    hoặc bản ghi xuất hiện sau cùng trong DataFrame).

    Args:
        df: DataFrame OHLCV.

    Returns:
        ``(df_deduped, duplicates_removed)``
    """
    before = len(df)
    dedup_keys = ["symbol_id", "timeframe", "ts"]

    # Ưu tiên bản ghi có ingested_at mới nhất
    if "ingested_at" in df.columns:
        df = df.sort_values(
            dedup_keys + ["ingested_at"],
            ascending=[True, True, True, False],
        )

    df = df.drop_duplicates(subset=dedup_keys, keep="first")
    removed = before - len(df)

    if removed > 0:
        logger.info("Deduplicate: loại %d bản ghi trùng", removed)

    return df, removed


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Step 3: Forward-fill missing sessions (stock only)                     ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


def fill_missing_sessions(
    df: pd.DataFrame,
    asset_class: str,
    timeframe: str,
    ffill_limit: int = 3,
) -> tuple[pd.DataFrame, int]:
    """Forward-fill các phiên bị thiếu cho cổ phiếu VN.

    - **stock + 1d**: tạo business-day index (thứ 2–6), forward-fill tối đa
      ``ffill_limit`` phiên liên tiếp. Bản ghi được fill có ``volume = 0``
      (không có giao dịch thật).
    - **crypto**: KHÔNG fill — crypto giao dịch 24/7, missing nghĩa là lỗi
      thật từ nguồn.

    Chỉ dùng dữ liệu quá khứ (forward-fill), không look-ahead.

    Args:
        df: DataFrame OHLCV đã sort theo ``ts``.
        asset_class: ``'stock'`` hoặc ``'crypto'``.
        timeframe: ``'1d'``, ``'1h'``, v.v.
        ffill_limit: Số phiên liên tiếp tối đa được fill.

    Returns:
        ``(df_filled, missing_filled_count)``
    """
    if asset_class != "stock" or timeframe != "1d":
        return df, 0

    filled_groups: list[pd.DataFrame] = []
    total_filled = 0

    price_cols = ["open", "high", "low", "close"]

    for (sym_id, tf), group in df.groupby(["symbol_id", "timeframe"]):
        group = group.sort_values("ts").copy()
        group = group.set_index("ts")
        original_len = len(group)

        # Tạo business-day index (thứ 2–6) trong range dữ liệu
        full_idx = pd.bdate_range(
            start=group.index.min(),
            end=group.index.max(),
            freq="B",
        )
        # Match timezone nếu cần
        if group.index.tz is not None and full_idx.tz is None:
            full_idx = full_idx.tz_localize(group.index.tz)

        # Reindex: tạo NaN cho ngày thiếu
        group = group.reindex(full_idx)

        # Forward-fill giá (chỉ dùng quá khứ, không look-ahead)
        for col in price_cols:
            if col in group.columns:
                group[col] = group[col].ffill(limit=ffill_limit)

        # Đánh dấu rows đã fill: volume gốc là NaN → set volume = 0
        is_filled_mask = group["volume"].isna()
        group.loc[is_filled_mask, "volume"] = 0

        # Điền lại symbol_id và timeframe cho rows mới
        group["symbol_id"] = sym_id
        group["timeframe"] = tf

        # Forward-fill các cột phụ (source, v.v.) nếu có
        for col in group.columns:
            if col not in price_cols + ["volume", "symbol_id", "timeframe"]:
                group[col] = group[col].ffill(limit=ffill_limit)

        # Loại rows không fill được (gap > limit → close vẫn NaN)
        group = group.dropna(subset=["close"])

        filled = len(group) - original_len
        total_filled += max(filled, 0)

        group = group.reset_index().rename(columns={"index": "ts"})
        filled_groups.append(group)

    if not filled_groups:
        return df, 0

    result = pd.concat(filled_groups, ignore_index=True)

    if total_filled > 0:
        logger.info(
            "Forward-fill: điền %d phiên thiếu (limit=%d)", total_filled, ffill_limit
        )

    return result, total_filled


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Step 4: Phát hiện outlier bằng IQR                                    ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


def detect_outliers(
    df: pd.DataFrame,
    iqr_multiplier: float = 1.5,
    min_group_size: int = 10,
) -> tuple[pd.DataFrame, int]:
    """Phát hiện outlier bằng IQR trên ``close`` và ``volume``.

    Outlier: giá trị nằm ngoài ``[Q1 - k*IQR, Q3 + k*IQR]`` trong cùng
    nhóm ``(symbol_id, timeframe)``.

    Chỉ **gắn cờ** ``is_outlier = True``, KHÔNG xóa bản ghi (để truy vết).

    Args:
        df: DataFrame OHLCV.
        iqr_multiplier: Hệ số ``k`` cho ngưỡng IQR. Mặc định 1.5.
        min_group_size: Nhóm nhỏ hơn giá trị này sẽ bỏ qua (IQR không
            có ý nghĩa thống kê với mẫu quá nhỏ).

    Returns:
        ``(df_with_flag, outlier_count)``
    """
    df = df.copy()
    df["is_outlier"] = False

    for col in ["close", "volume"]:
        if col not in df.columns:
            continue

        values = df[col].astype(float)

        # Tính Q1, Q3 per group bằng transform
        grp = df.groupby(["symbol_id", "timeframe"])[col]
        group_sizes = grp.transform("count")

        q1 = grp.transform(lambda x: x.astype(float).quantile(0.25))
        q3 = grp.transform(lambda x: x.astype(float).quantile(0.75))
        iqr = q3 - q1

        lower = q1 - iqr_multiplier * iqr
        upper = q3 + iqr_multiplier * iqr

        # Chỉ flag nếu nhóm đủ lớn để IQR có ý nghĩa
        outlier_mask = (group_sizes >= min_group_size) & (
            (values < lower) | (values > upper)
        )
        df.loc[outlier_mask, "is_outlier"] = True

    outlier_count = int(df["is_outlier"].sum())
    if outlier_count > 0:
        logger.info(
            "Outlier detection: %d bản ghi bị gắn cờ (IQR × %.1f)",
            outlier_count,
            iqr_multiplier,
        )

    return df, outlier_count


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Pipeline chính                                                         ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


def clean_ohlcv(
    df: pd.DataFrame,
    asset_class: str,
    config: Optional[CleaningConfig] = None,
) -> tuple[pd.DataFrame, CleaningReport]:
    """Pipeline chính: cleaning dữ liệu OHLCV.

    Thứ tự xử lý:
        1. Chuẩn hóa timezone → UTC.
        2. Loại bản ghi trùng ``(symbol_id, timeframe, ts)``.
        3. Forward-fill missing sessions (stock daily only).
        4. Phát hiện outlier bằng IQR → gắn cờ ``is_outlier``.

    Args:
        df: DataFrame thô từ ``market.ohlcv_raw``. Cần có cột:
            ``symbol_id``, ``timeframe``, ``ts``, ``open``, ``high``,
            ``low``, ``close``, ``volume``.
            Tùy chọn: ``source``, ``ingested_at``, ``raw_payload``.
        asset_class: ``'stock'`` hoặc ``'crypto'``.
        config: Cấu hình cleaning. Nếu ``None``, đọc mặc định từ ``.env``.

    Returns:
        ``(cleaned_df, report)`` — DataFrame đã sạch (có cột ``is_outlier``)
        và ``CleaningReport`` để ghi vào ``ops.data_quality_check``.
    """
    if config is None:
        config = CleaningConfig()

    report = CleaningReport(input_rows=len(df))

    if df.empty:
        report.output_rows = 0
        return df, report

    # Suy luận source và timeframe từ dữ liệu
    source = str(df["source"].iloc[0]) if "source" in df.columns else "unknown"
    timeframe = str(df["timeframe"].iloc[0]) if "timeframe" in df.columns else "1d"

    # Step 1: Timezone
    df = normalize_timezone(df, source=source, timeframe=timeframe)

    # Step 2: Deduplicate
    df, dups = deduplicate(df)
    report.duplicates_removed = dups

    # Step 3: Fill missing (stock only, no look-ahead)
    df, filled = fill_missing_sessions(
        df,
        asset_class=asset_class,
        timeframe=timeframe,
        ffill_limit=config.CLEANING_FFILL_LIMIT,
    )
    report.missing_filled = filled

    # Step 4: Outlier detection (flag only, don't remove)
    df, outliers = detect_outliers(
        df,
        iqr_multiplier=config.CLEANING_IQR_MULTIPLIER,
    )
    report.outliers_flagged = outliers

    # Sort output
    df = df.sort_values(["symbol_id", "timeframe", "ts"]).reset_index(drop=True)

    report.output_rows = len(df)

    logger.info(
        "Cleaning done: in=%d out=%d dups=%d filled=%d outliers=%d",
        report.input_rows,
        report.output_rows,
        report.duplicates_removed,
        report.missing_filled,
        report.outliers_flagged,
    )

    return df, report
