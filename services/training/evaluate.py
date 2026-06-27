import logging
from typing import Dict, Union, List
import numpy as np
from shared.utils.metrics import (
    mean_absolute_error,
    root_mean_squared_error,
    mean_absolute_percentage_error,
)

logger = logging.getLogger(__name__)


def evaluate_predictions(
    y_true: Union[np.ndarray, List[float]], y_pred: Union[np.ndarray, List[float]]
) -> Dict[str, float]:
    """
    Computes performance metrics to assess predictions.
    """
    mae = mean_absolute_error(y_true, y_pred)
    rmse = root_mean_squared_error(y_true, y_pred)
    mape = mean_absolute_percentage_error(y_true, y_pred)

    logger.info(f"Evaluation Results: MAE={mae:.4f}, RMSE={rmse:.4f}, MAPE={mape:.4%}")

    return {"mae": mae, "rmse": rmse, "mape": mape}
