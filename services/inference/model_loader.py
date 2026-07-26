"""Load registered models from the MLflow Registry as ready-to-use predictors.

Registry naming contract (all four trainers, see services/training/train_*.py):

    {SYMBOL}_{timeframe}_{model_name}   e.g. ACB_1d_xgboost, BTCUSDT_1h_gru

where SYMBOL is the ticker with '/' stripped and uppercased. Each model is
logged with a different MLflow flavor, so loading is flavor-specific:

- xgboost       -> mlflow.xgboost   + preprocessing/standard_scaler.joblib
- random_forest -> mlflow.sklearn   (raw features, no scaler)
- gru           -> mlflow.pytorch   + preprocessing/{feature,target}_scaler.joblib
                   (falls back to rebuilding from model_state/gru_state_dict.pt
                   when the training package is not importable)
- arima         -> mlflow.statsmodels + metadata/pre_test_model.json
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import joblib
import mlflow
import pandas as pd
from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient

from shared.config.settings import settings

from predictors import (
    ArimaPredictor,
    GRUPredictor,
    Predictor,
    RandomForestPredictor,
    XGBoostPredictor,
)

logger = logging.getLogger(__name__)

SCALER_ARTIFACT = "preprocessing/standard_scaler.joblib"
GRU_FEATURE_SCALER_ARTIFACT = "preprocessing/feature_scaler.joblib"
GRU_TARGET_SCALER_ARTIFACT = "preprocessing/target_scaler.joblib"
GRU_STATE_DICT_ARTIFACT = "model_state/gru_state_dict.pt"
ARIMA_METADATA_ARTIFACT = "metadata/pre_test_model.json"


class ModelNotRegisteredError(RuntimeError):
    """The requested model has no version in the MLflow Registry."""


class ModelLoadError(RuntimeError):
    """The model exists but could not be loaded (MLflow down, bad artifacts…)."""


def normalize_ticker(ticker: str) -> str:
    """Normalize a ticker the same way the trainers do ('BTC/USDT' -> 'BTCUSDT')."""
    return ticker.strip().replace("/", "").upper()


def build_registry_name(ticker: str, timeframe: str, model_name: str) -> str:
    """Build the registry name used by every training entrypoint."""
    return f"{normalize_ticker(ticker)}_{timeframe.strip().lower()}_{model_name}"


@dataclass
class LoadedModel:
    """A predictor plus the registry metadata it was resolved from."""

    predictor: Predictor
    registry_name: str
    version: int
    run_id: str


class ModelLoader:
    """Resolve registry versions and cache flavor-loaded predictors in RAM."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, int], LoadedModel] = {}
        mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)

    def load(self, ticker: str, timeframe: str, model_name: str) -> LoadedModel:
        """Load the newest registered version of a model as a predictor."""
        registry_name = build_registry_name(ticker, timeframe, model_name)
        version, run_id = self.latest_version(registry_name)

        cache_key = (registry_name, version)
        if cache_key in self._cache:
            logger.debug("Model cache hit: %s v%d", registry_name, version)
            return self._cache[cache_key]

        logger.info("Loading model %s v%d from MLflow...", registry_name, version)
        try:
            predictor = self._build_predictor(
                model_name, registry_name, version, run_id
            )
        except (ModelNotRegisteredError, ModelLoadError):
            raise
        except Exception as exc:  # noqa: BLE001 — surface any loader failure as 503
            raise ModelLoadError(
                f"Failed to load '{registry_name}' v{version}: {exc}"
            ) from exc

        loaded = LoadedModel(
            predictor=predictor,
            registry_name=registry_name,
            version=version,
            run_id=run_id,
        )
        self._cache[cache_key] = loaded
        return loaded

    # ── Registry resolution ─────────────────────────────────────────

    def latest_version(self, registry_name: str) -> tuple[int, str]:
        """Return (version, run_id) of the newest version of a registered model."""
        client = MlflowClient()
        try:
            versions = client.search_model_versions(f"name='{registry_name}'")
        except MlflowException as exc:
            raise ModelLoadError(
                f"Cannot reach MLflow Registry at {settings.MLFLOW_TRACKING_URI}: {exc}"
            ) from exc
        if not versions:
            raise ModelNotRegisteredError(
                f"Model '{registry_name}' is not registered in MLflow. "
                f"Train it first (python -m services.training.train_<model>)."
            )
        newest = max(versions, key=lambda v: int(v.version))
        return int(newest.version), str(newest.run_id)

    def _download(self, run_id: str, artifact_path: str) -> str:
        """Download one run artifact and return its local path."""
        return mlflow.artifacts.download_artifacts(
            run_id=run_id, artifact_path=artifact_path
        )

    # ── Flavor-specific builders ────────────────────────────────────

    def _build_predictor(
        self, model_name: str, registry_name: str, version: int, run_id: str
    ) -> Predictor:
        model_uri = f"models:/{registry_name}/{version}"
        if model_name == "xgboost":
            model = mlflow.xgboost.load_model(model_uri)
            scaler = joblib.load(self._download(run_id, SCALER_ARTIFACT))
            return XGBoostPredictor(model, scaler)
        if model_name == "random_forest":
            model = mlflow.sklearn.load_model(model_uri)
            return RandomForestPredictor(model)
        if model_name == "gru":
            return self._build_gru(model_uri, run_id)
        if model_name == "arima":
            return self._build_arima(model_uri, run_id)
        raise ModelLoadError(f"Unsupported model name: {model_name}")

    def _build_gru(self, model_uri: str, run_id: str) -> GRUPredictor:
        try:
            import torch
        except ImportError as exc:
            raise ModelLoadError(
                "PyTorch is not installed in the inference runtime; "
                "GRU predictions are unavailable."
            ) from exc

        params = MlflowClient().get_run(run_id).data.params
        try:
            model = mlflow.pytorch.load_model(model_uri, map_location="cpu")
        except Exception:
            # The pickled module references services.training.models.gru_model,
            # which is absent in the standalone image — rebuild from state dict.
            logger.info("Rebuilding GRU from state dict (training package absent).")
            from gru_net import GRUForecaster

            model = GRUForecaster(
                input_size=int(params.get("input_size", 2)),
                hidden_size=int(params.get("hidden_size", 64)),
                num_layers=int(params.get("num_layers", 2)),
                dropout=float(params.get("dropout", 0.2)),
            )
            state_path = self._download(run_id, GRU_STATE_DICT_ARTIFACT)
            model.load_state_dict(torch.load(state_path, map_location="cpu"))

        feature_scaler = joblib.load(
            self._download(run_id, GRU_FEATURE_SCALER_ARTIFACT)
        )
        target_scaler = joblib.load(self._download(run_id, GRU_TARGET_SCALER_ARTIFACT))
        return GRUPredictor(
            model,
            feature_scaler,
            target_scaler,
            sequence_length=int(params.get("sequence_length", 30)),
            moving_average_window=int(params.get("moving_average_window", 7)),
        )

    def _build_arima(self, model_uri: str, run_id: str) -> ArimaPredictor:
        model = mlflow.statsmodels.load_model(model_uri)
        history_end_ts: pd.Timestamp | None = None
        try:
            metadata_path = self._download(run_id, ARIMA_METADATA_ARTIFACT)
            metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
            raw_ts = metadata.get("history_end_ts")
            if raw_ts:
                history_end_ts = pd.Timestamp(raw_ts)
        except Exception as exc:  # noqa: BLE001 — metadata is best-effort
            logger.warning(
                "ARIMA metadata artifact unavailable (%s); "
                "state will not be advanced with new bars.",
                exc,
            )
        return ArimaPredictor(model, history_end_ts)


# Singleton instance
model_loader = ModelLoader()
