import logging

import mlflow
from typing import Any

from shared.config.settings import settings

logger = logging.getLogger(__name__)


def init_mlflow() -> None:
    """Initializes MLflow tracking URI client configuration."""
    mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
    logger.info(f"MLflow Tracking URI set to: {settings.MLFLOW_TRACKING_URI}")


def _log_model(
    model: Any,
    run_name: str,
    model_name_in_registry: str | None,
) -> None:
    """Log a model with its native MLflow flavor and optional registry name."""
    log_options = {"artifact_path": "model"}
    if model_name_in_registry is not None:
        log_options["registered_model_name"] = model_name_in_registry

    if hasattr(model, "predict") and "xgboost" in run_name.lower():
        mlflow.xgboost.log_model(model, **log_options)
    elif hasattr(model, "state_dict"):
        mlflow.pytorch.log_model(model, **log_options)
    else:
        mlflow.sklearn.log_model(model, **log_options)


def log_experiment_run(
    experiment_name: str,
    run_name: str,
    params: dict[str, Any],
    metrics: dict[str, float],
    model: Any,
    model_name_in_registry: str | None = None,
) -> str:
    """
    Helper function to log a model training run to MLflow.
    Optionally registers the model in MLflow registry.
    """
    init_mlflow()
    mlflow.set_experiment(experiment_name)

    with mlflow.start_run(run_name=run_name) as run:
        # Log Parameters
        mlflow.log_params(params)
        logger.info(f"Logged params to MLflow: {params}")

        # Log Metrics
        mlflow.log_metrics(metrics)
        logger.info(f"Logged metrics to MLflow: {metrics}")

        try:
            _log_model(model, run_name, model_name_in_registry)
        except Exception:
            logger.exception(
                "Failed to log model for run '%s'; aborting the training pipeline.",
                run_name,
            )
            raise

        if model_name_in_registry is not None:
            logger.info("Model logged and registered as: %s", model_name_in_registry)
        else:
            logger.info("Model logged to MLflow without registration")

        return str(run.info.run_id)
