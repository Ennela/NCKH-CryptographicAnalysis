import logging
import mlflow
from typing import Any
from shared.config.settings import settings

logger = logging.getLogger(__name__)


class ModelLoader:
    """
    Tải mô hình từ MLflow Model Registry và cache lại trong bộ nhớ RAM
    để phục vụ các request dự báo với độ trễ cực thấp.
    """

    def __init__(self):
        self._cache = {}
        mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)

    def load_registered_model(self, ticker_id: str, model_name: str) -> Any:
        """
        Loads a registered model from MLflow Registry.
        `ticker_id` format: e.g. 'BTC/USDT' or 'FPT'
        `model_name` format: e.g. 'xgboost' or 'lstm'
        """
        # Format name matching MLflow registry naming convention
        clean_ticker = ticker_id.replace("/", "-")
        model_registry_name = f"{clean_ticker}_{model_name}"

        # Check cache
        if model_registry_name in self._cache:
            logger.debug(f"Cache hit for model: {model_registry_name}")
            return self._cache[model_registry_name]

        logger.info(
            f"Cache miss. Loading model '{model_registry_name}' from MLflow Registry..."
        )
        try:
            # URI format: models:/<model_name>/<version_or_stage>
            # We load the 'latest' or 'Production' stage
            model_uri = f"models:/{model_registry_name}/latest"

            # Load as generic pyfunc
            model = mlflow.pyfunc.load_model(model_uri)

            # Save to cache
            self._cache[model_registry_name] = model
            logger.info(f"Successfully loaded and cached model: {model_registry_name}")
            return model

        except Exception as e:
            logger.error(
                f"Failed to load model '{model_registry_name}' from MLflow: {str(e)}"
            )
            # For development safety, if MLflow is not reachable, we'll raise an error
            # TODO: Dev 1 can configure a fallback mock model for frontend demo if MLflow is down
            raise RuntimeError(
                f"MLflow model not found: {model_registry_name}. Error: {str(e)}"
            )


# Singleton instance
model_loader = ModelLoader()
