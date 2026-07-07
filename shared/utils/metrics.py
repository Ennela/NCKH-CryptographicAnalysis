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


def r2_score(
    y_true: Union[np.ndarray, List[float]], y_pred: Union[np.ndarray, List[float]]
) -> float:
    """
    Computes R² (coefficient of determination).

    R² = 1 - SS_res / SS_tot.
    Returns 0.0 if total variance is zero (constant target).
    """
    y_t = np.array(y_true, dtype=float)
    y_p = np.array(y_pred, dtype=float)
    ss_res = np.sum((y_t - y_p) ** 2)
    ss_tot = np.sum((y_t - np.mean(y_t)) ** 2)
    if ss_tot == 0:
        return 0.0
    return float(1.0 - ss_res / ss_tot)


def directional_accuracy(
    y_true: Union[np.ndarray, List[float]],
    y_pred: Union[np.ndarray, List[float]],
    previous_close: Union[np.ndarray, List[float], None] = None,
) -> float:
    """
    Computes Directional Accuracy — fraction of correct direction predictions.

    Direction is computed relative to ``previous_close`` (close at time *t*
    when the target is close at *t+horizon*).  If ``previous_close`` is not
    provided the function falls back to using consecutive differences of
    ``y_true`` (i.e. ``y_true[i-1]`` as previous close), which discards the
    first observation.

    Input:
        y_true:         actual target values (close at t+horizon).
        y_pred:         predicted target values.
        previous_close: close prices at time *t* (same length as y_true).

    Output:
        float in [0, 1] — ratio of correctly predicted directions.
    """
    y_t = np.array(y_true, dtype=float)
    y_p = np.array(y_pred, dtype=float)

    if previous_close is not None:
        prev = np.array(previous_close, dtype=float)
        actual_dir = np.sign(y_t - prev)
        pred_dir = np.sign(y_p - prev)
    else:
        # Fallback: use y_true[i-1] as proxy for previous close
        actual_dir = np.sign(np.diff(y_t))
        pred_dir = np.sign(y_p[1:] - y_t[:-1])

    if len(actual_dir) == 0:
        return 0.0
    return float(np.mean(actual_dir == pred_dir))
