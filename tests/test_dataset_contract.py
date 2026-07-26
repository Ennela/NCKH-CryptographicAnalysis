import hashlib
import importlib
import sys
import types
from argparse import Namespace
from pathlib import Path

import pytest

from scripts.snapshot_checksum import compute_manifest_fingerprint, sha256_file

REPO_ROOT = Path(__file__).resolve().parents[1]
TRAINING_DIR = REPO_ROOT / "services" / "training"

pytestmark = pytest.mark.no_db


class _DummyTimeSeriesSplit:
    def __init__(self, n_splits: int = 5) -> None:
        self.n_splits = n_splits

    def split(self, df: object) -> list[tuple[list[int], list[int]]]:
        return []


class _DummyModel:
    def __init__(self, *args: object, **kwargs: object) -> None:
        self.feature_importances_: list[float] = []

    def fit(self, *args: object, **kwargs: object) -> "_DummyModel":
        return self

    def predict(self, *args: object, **kwargs: object) -> list[float]:
        return []

    def forecast(self, steps: int = 1) -> list[float]:
        return [0.0] * steps


def _module(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    sys.modules.setdefault(name, module)
    return module


def _install_training_import_stubs() -> None:
    sklearn_module = types.ModuleType("sklearn")
    model_selection_module = types.ModuleType("sklearn.model_selection")
    model_selection_module.TimeSeriesSplit = _DummyTimeSeriesSplit
    ensemble_module = types.ModuleType("sklearn.ensemble")
    ensemble_module.RandomForestRegressor = _DummyModel
    sys.modules.setdefault("sklearn", sklearn_module)
    sys.modules.setdefault("sklearn.model_selection", model_selection_module)
    sys.modules.setdefault("sklearn.ensemble", ensemble_module)

    optuna_module = _module("optuna")
    optuna_module.Trial = object
    optuna_module.create_study = lambda *args, **kwargs: None

    torch_module = _module("torch")
    torch_module.manual_seed = lambda seed: None

    xgboost_module = _module("xgboost")
    xgboost_module.XGBRegressor = _DummyModel

    shap_module = _module("shap")
    shap_module.TreeExplainer = _DummyModel

    statsmodels_module = _module("statsmodels")
    tsa_module = _module("statsmodels.tsa")
    arima_pkg = _module("statsmodels.tsa.arima")
    arima_model_module = _module("statsmodels.tsa.arima.model")
    arima_model_module.ARIMA = _DummyModel
    statsmodels_module.tsa = tsa_module
    tsa_module.arima = arima_pkg
    arima_pkg.model = arima_model_module

    mlflow_module = _module("mlflow")
    mlflow_module.set_tracking_uri = lambda *args, **kwargs: None
    mlflow_module.set_experiment = lambda *args, **kwargs: None


def _prepare_training_path() -> None:
    for path in (REPO_ROOT, TRAINING_DIR):
        path_text = str(path)
        if path_text not in sys.path:
            sys.path.insert(0, path_text)


def _train_module() -> types.ModuleType:
    _prepare_training_path()
    _install_training_import_stubs()
    return importlib.import_module("services.training.train")


def _data_loader_class() -> type:
    _prepare_training_path()
    _install_training_import_stubs()
    data_loader_module = importlib.import_module("services.training.data_loader")
    return data_loader_module.DataLoader


def test_sha256_file(tmp_path: Path) -> None:
    path = tmp_path / "sample.txt"
    path.write_text("known content", encoding="utf-8")

    assert sha256_file(path) == hashlib.sha256(b"known content").hexdigest()


def test_compute_manifest_fingerprint_deterministic() -> None:
    manifest_a = {
        "snapshot_name": "ohlcv_full_current",
        "files": {"b": {"rows": 2}, "a": {"rows": 1}},
    }
    manifest_b = {
        "files": {"a": {"rows": 1}, "b": {"rows": 2}},
        "snapshot_name": "ohlcv_full_current",
    }

    assert compute_manifest_fingerprint(manifest_a) == compute_manifest_fingerprint(
        manifest_b
    )


def test_compute_manifest_fingerprint_excludes_self() -> None:
    manifest = {"snapshot_name": "ohlcv_full_current", "files": {}}
    with_fingerprint = {**manifest, "snapshot_fingerprint": "old-value"}

    assert compute_manifest_fingerprint(manifest) == compute_manifest_fingerprint(
        with_fingerprint
    )


def test_train_rejects_none_without_flag() -> None:
    train = _train_module()
    args = Namespace(dataset_config="none", allow_custom_data=False)

    with pytest.raises(SystemExit) as exc:
        train._load_dataset_contract_or_exit(args)

    assert exc.value.code == 1


def test_train_allows_none_with_custom_flag() -> None:
    train = _train_module()
    args = Namespace(dataset_config="none", allow_custom_data=True)

    assert train._load_dataset_contract_or_exit(args) is None


def test_custom_dataset_tracking_params() -> None:
    train = _train_module()

    assert train._dataset_tracking_params(None) == {
        "dataset_version": "CUSTOM",
        "source_snapshot_name": "CUSTOM",
        "dataset_contract": "NONE - CUSTOM DATA",
    }


def test_valid_ticker_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    DataLoader = _data_loader_class()
    contract = {
        "dataset_version": "group_dataset_v1",
        "assets": {
            "crypto": {
                "symbols": ["BTCUSDT"],
                "timeframes": {"1d": {}},
            }
        },
    }

    monkeypatch.setattr(
        "services.training.dataset_contract.load_dataset_contract",
        lambda path: contract,
    )

    DataLoader("BTCUSDT", "1d").validate_against_contract()


def test_invalid_ticker_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    DataLoader = _data_loader_class()
    contract = {
        "dataset_version": "group_dataset_v1",
        "assets": {
            "crypto": {
                "symbols": ["BTCUSDT"],
                "timeframes": {"1d": {}},
            }
        },
    }

    monkeypatch.setattr(
        "services.training.dataset_contract.load_dataset_contract",
        lambda path: contract,
    )

    with pytest.raises(ValueError):
        DataLoader("INVALID", "1d").validate_against_contract()
