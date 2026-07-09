import logging
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sklearn.model_selection import TimeSeriesSplit
from shared.db.session import SessionLocal
from shared.utils.metrics import (
    calculate_returns,
    calculate_volatility,
    calculate_rsi,
    calculate_macd,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# Feature column registry — single source of truth for ML features
# ==============================================================================

FEATURE_COLUMNS: list[str] = [
    # Technical indicators (original)
    "returns",
    "volatility",
    "rsi",
    "macd",
    "macd_signal",
    # Lag features
    "close_lag_1",
    "close_lag_2",
    "close_lag_3",
    "close_lag_7",
    "return_lag_1",
    "return_lag_3",
    "return_lag_7",
    # Rolling statistics
    "rolling_mean_7",
    "rolling_mean_14",
    "rolling_std_7",
    "rolling_std_14",
    # Volume
    "volume_change",
]


class DataLoader:
    """
    Loads historical market data from TimescaleDB and engineers features for models.

    Reads from ``market.ohlcv`` (joined with ``market.symbol`` for ticker lookup).
    NOTE: Official report results are valid only when run through ``train.py``
    or ``make train-official`` with the dataset contract enabled. If using
    DataLoader directly in a notebook, call ``validate_against_contract()`` to
    catch ticker/resolution mistakes early.
    """

    def __init__(self, ticker_id: str, resolution: str = "1d") -> None:
        self.ticker_id = self._normalize_ticker(ticker_id)
        self.resolution = resolution

    # ------------------------------------------------------------------
    # Ticker normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_ticker(ticker: str) -> str:
        """
        Normalize a ticker string for DB lookup.

        Handles crypto tickers with slashes (``BTC/USDT`` → ``BTCUSDT``)
        and uppercases the result.  Stock tickers (``FPT``) pass through.
        """
        return ticker.strip().replace("/", "").upper()

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def load_raw_data(
        self,
        limit: Optional[int] = None,
        start_ts: Optional[str] = None,
        end_ts: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Loads candles from ``market.ohlcv`` joined with ``market.symbol``.

        Input:
            limit: maximum number of rows to return.  ``None`` means all rows.
            start_ts: optional inclusive lower timestamp bound.
            end_ts: optional inclusive upper timestamp bound.

        Output:
            DataFrame with columns: timestamp, open, high, low, close, volume.
            Sorted ascending by timestamp.
        """
        db = SessionLocal()

        # Step 1: resolve ticker → symbol_id
        sym_query = text(
            "SELECT id FROM market.symbol "
            "WHERE ticker = :ticker AND status = 'active'"
        )

        try:
            sym_row = db.execute(sym_query, {"ticker": self.ticker_id}).first()
            if sym_row is None:
                logger.error(
                    "Ticker '%s' not found in market.symbol. "
                    "Check that ingestion has seeded this symbol.",
                    self.ticker_id,
                )
                return pd.DataFrame()

            symbol_id: int = sym_row[0]

            # Step 2: query OHLCV data
            conditions = ["symbol_id = :symbol_id", "timeframe = :timeframe"]
            params = {
                "symbol_id": symbol_id,
                "timeframe": self.resolution,
            }

            if start_ts is not None:
                conditions.append("ts >= CAST(:start_ts AS TIMESTAMPTZ)")
                params["start_ts"] = start_ts
            if end_ts is not None:
                conditions.append("ts <= CAST(:end_ts AS TIMESTAMPTZ)")
                params["end_ts"] = end_ts

            query_text = (
                "SELECT ts, open, high, low, close, volume "
                "FROM market.ohlcv "
                f"WHERE {' AND '.join(conditions)} "
                "ORDER BY ts ASC"
            )

            if limit is not None:
                query_text += " LIMIT :limit"
                params["limit"] = limit

            ohlcv_sql = text(query_text)

            df = pd.read_sql_query(ohlcv_sql, con=db.bind, params=params)

            if df.empty:
                logger.warning(
                    "No OHLCV data found for symbol_id=%d, timeframe=%s",
                    symbol_id,
                    self.resolution,
                )
                return df

            # Rename DB column → pipeline convention
            df = df.rename(columns={"ts": "timestamp"})
            df["timestamp"] = pd.to_datetime(df["timestamp"])

            # Cast Decimal → float for numeric columns
            for col in ("open", "high", "low", "close", "volume"):
                df[col] = df[col].astype(float)

            logger.info(
                "Loaded %d candles for %s (%s) from %s to %s",
                len(df),
                self.ticker_id,
                self.resolution,
                df["timestamp"].iloc[0],
                df["timestamp"].iloc[-1],
            )
            return df

        finally:
            db.close()

    def validate_against_contract(
        self,
        contract_path: str = "configs/group_dataset.json",
    ) -> None:
        """
        Check that this loader's ticker and resolution exist in the contract.

        This is a soft check for notebooks and standalone scripts. It does not
        replace contract enforcement in ``train.py`` for official reports.

        Raises:
            ValueError: if the ticker or resolution is not in the contract.
        """
        try:
            from services.training.dataset_contract import (
                find_asset_for_symbol,
                get_timeframe_contract,
                load_dataset_contract,
            )
        except ModuleNotFoundError:
            from dataset_contract import (
                find_asset_for_symbol,
                get_timeframe_contract,
                load_dataset_contract,
            )

        contract = load_dataset_contract(contract_path)
        if contract is None:
            raise ValueError("Cannot load dataset contract.")

        find_asset_for_symbol(contract, self.ticker_id)
        get_timeframe_contract(contract, self.ticker_id, self.resolution)

    # ------------------------------------------------------------------
    # Feature engineering
    # ------------------------------------------------------------------

    def engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Computes financial features: returns, volatility, RSI, MACD,
        lag features, rolling stats, and volume change.

        All features use only past/current data — no look-ahead.
        """
        if len(df) < 30:
            logger.warning(
                "Not enough data (%d rows) to calculate all technical "
                "indicators properly.",
                len(df),
            )

        df = df.copy()

        # --- Original technical indicators ---
        df["returns"] = calculate_returns(df["close"])
        df["volatility"] = calculate_volatility(df["returns"], window=14)
        df["rsi"] = calculate_rsi(df["close"], period=14)

        macd_line, macd_sig = calculate_macd(df["close"])
        df["macd"] = macd_line
        df["macd_signal"] = macd_sig

        # --- Lag features (close) ---
        for lag in (1, 2, 3, 7):
            df[f"close_lag_{lag}"] = df["close"].shift(lag)

        # --- Lag features (returns) ---
        for lag in (1, 3, 7):
            df[f"return_lag_{lag}"] = df["returns"].shift(lag)

        # --- Rolling statistics ---
        for window in (7, 14):
            df[f"rolling_mean_{window}"] = (
                df["close"].rolling(window=window).mean()
            )
            df[f"rolling_std_{window}"] = (
                df["close"].rolling(window=window).std()
            )

        # --- Volume change ---
        df["volume_change"] = df["volume"].pct_change()

        # Drop initial rows with NaNs resulting from indicator windows
        df = df.dropna().reset_index(drop=True)
        return df

    # ------------------------------------------------------------------
    # Target creation
    # ------------------------------------------------------------------

    @staticmethod
    def add_target(
        df: pd.DataFrame,
        horizon: int = 1,
        target_mode: str = "next_close",
    ) -> pd.DataFrame:
        """
        Adds a ``target`` column to the DataFrame.

        MUST be called BEFORE splitting to avoid losing boundary rows.

        Input:
            df:          DataFrame with at least a ``close`` column.
            horizon:     number of steps ahead to predict.
            target_mode: ``"next_close"`` → target = close.shift(-horizon).
                         ``"next_return"`` → target = returns.shift(-horizon).

        Output:
            DataFrame with an extra ``target`` column.  Rows where target is
            NaN (last ``horizon`` rows) are dropped.
        """
        df = df.copy()

        if target_mode == "next_close":
            df["target"] = df["close"].shift(-horizon)
        elif target_mode == "next_return":
            if "returns" not in df.columns:
                df["_tmp_ret"] = df["close"].pct_change()
                df["target"] = df["_tmp_ret"].shift(-horizon)
                df = df.drop(columns=["_tmp_ret"])
            else:
                df["target"] = df["returns"].shift(-horizon)
        else:
            raise ValueError(
                f"Unknown target_mode '{target_mode}'. "
                "Use 'next_close' or 'next_return'."
            )

        df = df.dropna(subset=["target"]).reset_index(drop=True)
        return df

    # ------------------------------------------------------------------
    # Splitting
    # ------------------------------------------------------------------

    def prepare_train_validation_test_split(
        self,
        df: pd.DataFrame,
        train_ratio: float = 0.70,
        validation_ratio: float = 0.15,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Splits data sequentially by time into train / validation / test.

        No shuffling — preserves temporal order to prevent data leakage.

        Input:
            df:               DataFrame sorted by time.
            train_ratio:      fraction for training (default 70 %).
            validation_ratio: fraction for validation (default 15 %).
                              test_ratio = 1 - train_ratio - validation_ratio.

        Output:
            (train_df, val_df, test_df) — each reset-indexed.
        """
        n = len(df)
        train_end = int(n * train_ratio)
        val_end = int(n * (train_ratio + validation_ratio))

        train_df = df.iloc[:train_end].reset_index(drop=True)
        val_df = df.iloc[train_end:val_end].reset_index(drop=True)
        test_df = df.iloc[val_end:].reset_index(drop=True)

        logger.info(
            "Split: train=%d, val=%d, test=%d (total=%d)",
            len(train_df),
            len(val_df),
            len(test_df),
            n,
        )
        return train_df, val_df, test_df

    def prepare_train_test_split(
        self, df: pd.DataFrame, test_ratio: float = 0.2
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Splits data sequentially to prevent lookahead bias (standard sequential split).

        Kept for backward compatibility.
        """
        split_idx = int(len(df) * (1 - test_ratio))
        train_df = df.iloc[:split_idx].reset_index(drop=True)
        test_df = df.iloc[split_idx:].reset_index(drop=True)
        return train_df, test_df

    # ------------------------------------------------------------------
    # Cross-validation
    # ------------------------------------------------------------------

    def get_time_series_cross_val_splits(
        self, df: pd.DataFrame, n_splits: int = 5
    ):
        """
        Yields (train, val) splits using TimeSeriesSplit (Agile/ML validation standard).
        """
        tscv = TimeSeriesSplit(n_splits=n_splits)
        for train_idx, val_idx in tscv.split(df):
            yield df.iloc[train_idx], df.iloc[val_idx]

    # ------------------------------------------------------------------
    # Persistence (TODO)
    # ------------------------------------------------------------------

    def save_features_to_db(self, df: pd.DataFrame) -> None:
        """
        Saves computed features back into the processed.features table.
        """
        # TODO: Implement database write for processed.features.
        # Ensure to use `on_conflict_do_update` to avoid duplicating features.
        logger.info(f"Saving {len(df)} feature records to processed.features table")
        pass
