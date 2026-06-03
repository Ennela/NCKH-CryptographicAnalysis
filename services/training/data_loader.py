import logging
import pandas as pd
from typing import Tuple, Generator
from sqlalchemy import text
from sklearn.model_selection import TimeSeriesSplit
from shared.db.session import SessionLocal
from shared.utils.metrics import (
    calculate_returns,
    calculate_volatility,
    calculate_rsi,
    calculate_macd
)

logger = logging.getLogger(__name__)

class DataLoader:
    """
    Loads historical market data from TimescaleDB and engineers features for models.
    """
    def __init__(self, ticker_id: str, resolution: str = "1d"):
        self.ticker_id = ticker_id
        self.resolution = resolution

    def load_raw_data(self, limit: int = 1000) -> pd.DataFrame:
        """
        Loads the most recent raw candles from raw.ohlcv_prices.
        """
        db = SessionLocal()
        query = text("""
            SELECT timestamp, open, high, low, close, volume 
            FROM raw.ohlcv_prices
            WHERE ticker_id = :ticker_id AND resolution = :resolution
            ORDER BY timestamp ASC
            LIMIT :limit
        """)
        
        try:
            df = pd.read_sql_query(
                query, 
                con=db.bind, 
                params={"ticker_id": self.ticker_id, "resolution": self.resolution}
            )
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
        finally:
            db.close()

    def engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Computes financial features: returns, volatility, RSI, and MACD.
        """
        if len(df) < 30:
            logger.warning("Not enough data to calculate all technical indicators properly.")
            
        df = df.copy()
        
        # Calculate features
        df['returns'] = calculate_returns(df['close'])
        df['volatility'] = calculate_volatility(df['returns'], window=14)
        df['rsi'] = calculate_rsi(df['close'], period=14)
        
        macd_line, macd_sig = calculate_macd(df['close'])
        df['macd'] = macd_line
        df['macd_signal'] = macd_sig
        
        # Drop initial rows with NaNs resulting from indicator windows
        df = df.dropna().reset_index(drop=True)
        return df

    def save_features_to_db(self, df: pd.DataFrame):
        """
        Saves computed features back into the processed.features table.
        """
        # TODO: Implement database write for processed.features.
        # Ensure to use `on_conflict_do_update` to avoid duplicating features.
        logger.info(f"Saving {len(df)} feature records to processed.features table")
        pass

    def prepare_train_test_split(
        self, 
        df: pd.DataFrame, 
        test_ratio: float = 0.2
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Splits data sequentially to prevent lookahead bias (standard sequential split).
        """
        split_idx = int(len(df) * (1 - test_ratio))
        train_df = df.iloc[:split_idx].reset_index(drop=True)
        test_df = df.iloc[split_idx:].reset_index(drop=True)
        return train_df, test_df

    def get_time_series_cross_val_splits(
        self, 
        df: pd.DataFrame, 
        n_splits: int = 5
    ) -> Generator[Tuple[pd.DataFrame, pd.DataFrame], None, None]:
        """
        Yields (train, val) splits using TimeSeriesSplit (Agile/ML validation standard).
        """
        tscv = TimeSeriesSplit(n_splits=n_splits)
        for train_idx, val_idx in tscv.split(df):
            yield df.iloc[train_idx], df.iloc[val_idx]
        
        # TODO: Implement sequence shaping for LSTM/GRU neural nets (e.g. converting 2D df to 3D tensor of shape [batch, seq_len, features])
