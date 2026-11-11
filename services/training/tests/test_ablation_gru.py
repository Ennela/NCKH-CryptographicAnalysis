"""Tests for the GRU feature-group ablation."""

from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from services.training import ablation_gru, train_gru


@pytest.fixture
def sequences() -> train_gru.PreparedSequences:
    row_count = 140
    row_number = np.arange(row_count, dtype=np.float64)
    close = 10.0 + row_number * 0.1 + np.sin(row_number / 5.0) * 0.2
    split = np.where(
        row_number < 80, "train", np.where(row_number < 110, "val", "test")
    )
    frame = pd.DataFrame(
        {
            "ts": pd.date_range("2025-01-01", periods=row_count, freq="D", tz="UTC"),
            "open": close - 0.1,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1_000.0 + row_number,
            "split": split,
        }
    )
    frame["next_close"] = frame.groupby("split", sort=False)["close"].shift(-1)
    return train_gru.build_sequence_dataset(frame, train_gru.GRUTrainingConfig())


def test_every_variant_keeps_close_first_and_uses_known_features() -> None:
    for variant, features in ablation_gru.FEATURE_SETS.items():
        indices = ablation_gru.feature_indices(features)
        assert indices[0] == train_gru.FEATURE_LIST.index("close"), variant
    assert ablation_gru.FEATURE_SETS["full"] == train_gru.FEATURE_LIST


def test_feature_indices_rejects_variants_without_leading_close() -> None:
    with pytest.raises(ValueError, match="close"):
        ablation_gru.feature_indices(("return_1d", "close"))
    with pytest.raises(ValueError, match="Unknown"):
        ablation_gru.feature_indices(("close", "volume"))


def test_select_features_keeps_order_and_only_the_requested_channels(
    sequences: train_gru.PreparedSequences,
) -> None:
    indices = ablation_gru.feature_indices(("close", "moving_average_14"))
    sliced = ablation_gru.select_features(sequences.test, indices)
    assert sliced.X.shape == (*sequences.test.X.shape[:2], 2)
    np.testing.assert_array_equal(sliced.X, sequences.test.X[:, :, indices])
    np.testing.assert_array_equal(sliced.actual_close, sequences.test.actual_close)


def test_full_variant_matches_train_gru_and_runs_are_reproducible(
    monkeypatch: pytest.MonkeyPatch,
    sequences: train_gru.PreparedSequences,
) -> None:
    short = replace(train_gru.GRUTrainingConfig(), max_epochs=3, hidden_size=8)
    monkeypatch.setattr(ablation_gru, "GRUTrainingConfig", lambda: short)
    first, epoch = ablation_gru.train_variant(sequences, train_gru.FEATURE_LIST, 42)
    second, _ = ablation_gru.train_variant(sequences, train_gru.FEATURE_LIST, 42)
    assert first == second
    assert 1 <= epoch <= 3
    close_only, _ = ablation_gru.train_variant(sequences, ("close",), 42)
    assert np.isfinite(close_only["rmse"])
    assert close_only["naive_rmse"] == pytest.approx(first["naive_rmse"])


def test_append_result_writes_header_once(tmp_path: Path) -> None:
    path = tmp_path / "out.csv"
    row = {name: "x" for name in ablation_gru.RESULT_FIELDNAMES}
    ablation_gru.append_result(path, row)
    ablation_gru.append_result(path, row)
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == list(ablation_gru.RESULT_FIELDNAMES)
    assert len(rows) == 3
