from typing import List, Union
import numpy as np
import pandas as pd

# ==============================================================================
# Financial Indicators & Feature Engineering
# ==============================================================================


def calculate_returns(prices: pd.Series) -> pd.Series:
    """Calculates simple returns: (p_t - p_{t-1}) / p_{t-1}"""
    return prices.pct_change()


def calculate_volatility(returns: pd.Series, window: int = 14) -> pd.Series:
    """Calculates rolling volatility: standard deviation of returns over a window."""
    return returns.rolling(window=window).std()


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculates Relative Strength Index (RSI).
    """
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Use exponential moving average
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()

    rs = avg_gain / (avg_loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_macd(
    prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series]:
    """
    Calculates Moving Average Convergence Divergence (MACD) and signal line.
    Returns: (macd_line, signal_line)
    """
    exp1 = prices.ewm(span=fast, adjust=False).mean()
    exp2 = prices.ewm(span=slow, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line


# ==============================================================================
# Machine Learning Model Evaluation Metrics
# ==============================================================================


def mean_absolute_error(
    y_true: Union[np.ndarray, List[float]], y_pred: Union[np.ndarray, List[float]]
) -> float:
    """Computes Mean Absolute Error (MAE)."""
    return float(np.mean(np.abs(np.array(y_true) - np.array(y_pred))))


def root_mean_squared_error(
    y_true: Union[np.ndarray, List[float]], y_pred: Union[np.ndarray, List[float]]
) -> float:
    """Computes Root Mean Squared Error (RMSE)."""
    return float(np.sqrt(np.mean(np.square(np.array(y_true) - np.array(y_pred)))))


def mean_absolute_percentage_error(
    y_true: Union[np.ndarray, List[float]], y_pred: Union[np.ndarray, List[float]]
) -> float:
    """
    Computes Mean Absolute Percentage Error (MAPE).
    Handles potential divide-by-zero occurrences using a small epsilon.
    """
    y_t = np.array(y_true)
    y_p = np.array(y_pred)
    # Mask actual zero values to avoid division by zero
    mask = y_t != 0
    if not np.any(mask):
        return 0.0
    return float(np.mean(np.abs((y_t[mask] - y_p[mask]) / y_t[mask])))
