import logging
from typing import Dict, List, Optional, Union

import numpy as np
from shared.utils.metrics import (
    mean_absolute_error,
    root_mean_squared_error,
    mean_absolute_percentage_error,
    r2_score,
    directional_accuracy,
)

logger = logging.getLogger(__name__)


def compare_with_naive(
    y_true: Union[np.ndarray, List[float]],
    y_pred: Union[np.ndarray, List[float]],
    y_naive: Union[np.ndarray, List[float]],
) -> Dict[str, Dict[str, Optional[float]]]:
    """Compare model errors with a naive ``next close = current close`` forecast.

    ``model`` and ``naive`` contain MAE, RMSE, and MAPE. MAPE remains a
    fraction, matching the existing metric contract. ``improvement_pct`` is
    ``(naive - model) / naive * 100`` and is ``None`` when the naive error is
    smaller than ``1e-9``. ``improvement_abs`` is signed in the same direction,
    so a positive value always means the model has lower error than the naive
    forecast.

    Absolute MAE/RMSE improvements use the target price unit and are only
    directly comparable for models evaluated on the same symbol.
    ``improvement_abs['mape']`` is expressed in percentage points.
    """
    model_metrics = {
        "mae": mean_absolute_error(y_true, y_pred),
        "rmse": root_mean_squared_error(y_true, y_pred),
        "mape": mean_absolute_percentage_error(y_true, y_pred),
    }
    naive_metrics = {
        "mae": mean_absolute_error(y_true, y_naive),
        "rmse": root_mean_squared_error(y_true, y_naive),
        "mape": mean_absolute_percentage_error(y_true, y_naive),
    }
    improvement_pct: Dict[str, Optional[float]] = {}
    improvement_abs: Dict[str, Optional[float]] = {}

    for metric_name, model_value in model_metrics.items():
        naive_value = naive_metrics[metric_name]
        difference = naive_value - model_value
        improvement_pct[metric_name] = (
            None if abs(naive_value) < 1e-9 else difference / naive_value * 100.0
        )
        improvement_abs[metric_name] = (
            difference * 100.0 if metric_name == "mape" else difference
        )

    return {
        "model": model_metrics,
        "naive": naive_metrics,
        "improvement_pct": improvement_pct,
        "improvement_abs": improvement_abs,
    }


def evaluate_predictions(
    y_true: Union[np.ndarray, List[float]],
    y_pred: Union[np.ndarray, List[float]],
    previous_close: Optional[Union[np.ndarray, List[float]]] = None,
) -> Dict[str, float]:
    """
    Computes performance metrics to assess predictions.

    Input:
        y_true:         actual target values.
        y_pred:         predicted target values.
        previous_close: close prices at time *t* (for directional accuracy
                        and naive baseline).  Same length as y_true.

    Output:
        Dict with keys: mae, rmse, mape, r2, directional_accuracy,
        and (if previous_close provided) naive_* and improvement_vs_naive_rmse_pct.
    """
    mae = mean_absolute_error(y_true, y_pred)
    rmse = root_mean_squared_error(y_true, y_pred)
    mape = mean_absolute_percentage_error(y_true, y_pred)
    r2 = r2_score(y_true, y_pred)
    da = directional_accuracy(y_true, y_pred, previous_close)

    metrics: Dict[str, float] = {
        "mae": mae,
        "rmse": rmse,
        "mape": mape,
        "r2": r2,
        "directional_accuracy": da,
    }

    logger.info(
        "Model — MAE=%.4f  RMSE=%.4f  MAPE=%.4f%%  R²=%.4f  DA=%.4f",
        mae,
        rmse,
        mape * 100,
        r2,
        da,
    )

    # Naive baseline: predict next close = current close
    if previous_close is not None:
        naive_metrics = compute_naive_baseline_metrics(y_true, previous_close)
        metrics.update(naive_metrics)

    return metrics


def compute_naive_baseline_metrics(
    y_true: Union[np.ndarray, List[float]],
    previous_close: Union[np.ndarray, List[float]],
) -> Dict[str, float]:
    """
    Computes metrics for the Naive baseline (predict = previous close).

    The naive forecast assumes the next close equals the current close,
    which is the simplest possible prediction.  Any useful model must
    beat this baseline.

    Input:
        y_true:         actual target values (close at t+horizon).
        previous_close: close prices at time *t*.

    Output:
        Dict with naive_mae, naive_rmse, naive_mape,
        naive_directional_accuracy, and improvement_vs_naive_rmse_pct.
    """
    y_t = np.array(y_true, dtype=float)
    prev = np.array(previous_close, dtype=float)

    # Naive prediction: next close = current close
    naive_pred = prev

    n_mae = mean_absolute_error(y_t, naive_pred)
    n_rmse = root_mean_squared_error(y_t, naive_pred)
    n_mape = mean_absolute_percentage_error(y_t, naive_pred)
    n_da = directional_accuracy(y_t, naive_pred, prev)

    # Note: improvement_vs_naive_rmse_pct is NOT computed here — this function
    # only returns the naive_* metrics. The caller merges them with the model
    # metrics and then calls add_improvement_vs_naive() to derive it.

    result: Dict[str, float] = {
        "naive_mae": n_mae,
        "naive_rmse": n_rmse,
        "naive_mape": n_mape,
        "naive_directional_accuracy": n_da,
    }

    logger.info(
        "Naive — MAE=%.4f  RMSE=%.4f  MAPE=%.4f%%  DA=%.4f",
        n_mae,
        n_rmse,
        n_mape * 100,
        n_da,
    )

    return result


def add_improvement_vs_naive(
    metrics: Dict[str, float],
) -> Dict[str, float]:
    """
    Adds ``improvement_vs_naive_rmse_pct`` to the metrics dict.

    Must be called after both model and naive metrics are present.

    Formula: improvement = (naive_rmse - model_rmse) / naive_rmse * 100.
    Positive means the model is better than naive.
    """
    if "naive_rmse" in metrics and "rmse" in metrics:
        naive_rmse = metrics["naive_rmse"]
        if naive_rmse > 0:
            improvement = (naive_rmse - metrics["rmse"]) / naive_rmse * 100.0
        else:
            improvement = 0.0
        metrics["improvement_vs_naive_rmse_pct"] = round(improvement, 4)
        logger.info("Improvement vs Naive RMSE: %.2f%%", improvement)

    return metrics
