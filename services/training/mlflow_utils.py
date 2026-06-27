import logging
import mlflow
from typing import Dict, Any
from shared.config.settings import settings

logger = logging.getLogger(__name__)


def init_mlflow():
    """Initializes MLflow tracking URI client configuration."""
    mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
    logger.info(f"MLflow Tracking URI set to: {settings.MLFLOW_TRACKING_URI}")


def log_experiment_run(
    experiment_name: str,
    run_name: str,
    params: Dict[str, Any],
    metrics: Dict[str, float],
    model: Any,
    model_name_in_registry: str = None,
):
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

        # Log and Register Model
        if model_name_in_registry:
            # Logs standard model based on type (PyTorch, XGBoost, sklearn, etc)
            if hasattr(model, "predict") and "xgboost" in run_name.lower():
                mlflow.xgboost.log_model(
                    model,
                    artifact_path="model",
                    registered_model_name=model_name_in_registry,
                )
            elif hasattr(model, "state_dict"):  # PyTorch Model
                mlflow.pytorch.log_model(
                    model,
                    artifact_path="model",
                    registered_model_name=model_name_in_registry,
                )
            else:  # Fallback to standard python/statsmodels or pickle
                mlflow.sklearn.log_model(
                    model,
                    artifact_path="model",
                    registered_model_name=model_name_in_registry,
                )
            logger.info(f"Model registered as: {model_name_in_registry}")
        else:
            mlflow.sklearn.log_model(model, artifact_path="model")
            logger.info("Model logged to MLflow without registration")

        return run.info.run_id
