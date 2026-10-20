"""Tests for the Diebold-Mariano / stationarity analysis."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from services.training import significance


def test_dm_horizon_one_equals_one_sample_t_test() -> None:
    # For h=1 the HLN-corrected DM statistic reduces exactly to a t-test on d_t.
    rng = np.random.default_rng(0)
    baseline = rng.normal(0.0, 1.2, 200)
    model = rng.normal(0.0, 1.0, 200)
    result = significance.diebold_mariano(baseline, model, loss="squared")
    expected = stats.ttest_1samp(baseline**2 - model**2, 0.0)
    assert result.statistic == pytest.approx(expected.statistic, rel=1e-12)
    assert result.p_two_sided == pytest.approx(expected.pvalue, rel=1e-9)


def test_dm_sign_and_one_sided_p() -> None:
    rng = np.random.default_rng(1)
    baseline = rng.normal(0.0, 2.0, 300)
    better = baseline * 0.5
    result = significance.diebold_mariano(baseline, better, loss="absolute")
    assert result.statistic > 0
    assert result.p_model_better < 0.001
    reverse = significance.diebold_mariano(better, baseline, loss="absolute")
    assert reverse.statistic == pytest.approx(-result.statistic)
    assert reverse.p_model_better > 0.999


def test_dm_rejects_identical_forecasts_and_bad_input() -> None:
    errors = np.array([1.0, -1.0, 0.5, 0.2])
    with pytest.raises(ValueError, match="zero variance"):
        significance.diebold_mariano(errors, errors)
    with pytest.raises(ValueError, match="equal length"):
        significance.diebold_mariano(errors, errors[:3])
    with pytest.raises(ValueError, match="Unknown loss"):
        significance.diebold_mariano(errors, errors * 2, loss="huber")


def test_holm_adjust_matches_hand_computation() -> None:
    # Sorted p: 0.01*3=0.03, 0.02*2=0.04, 0.04*1=0.04 -> back in input order.
    assert significance.holm_adjust([0.04, 0.01, 0.02]) == pytest.approx(
        [0.04, 0.03, 0.04]
    )
    assert significance.holm_adjust([0.5, 0.9]) == pytest.approx([1.0, 1.0])


def test_stationarity_separates_random_walk_from_returns() -> None:
    rng = np.random.default_rng(42)
    price = pd.Series(100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, 800))))
    level = significance.stationarity(price)
    returns = significance.stationarity(np.log(price).diff())
    assert level["adf_p"] > 0.05 and level["kpss_p"] < 0.05
    assert returns["adf_p"] < 0.01 and returns["kpss_p"] > 0.05
    assert returns["n"] == 799
