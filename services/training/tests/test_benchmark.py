"""Contract tests for the explicit four-model ACB 1d benchmark evaluator."""

from __future__ import annotations

import argparse
import json
from contextlib import AbstractContextManager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest

from services.training import benchmark
from services.training.benchmark_contract import (
    EXPECTED_TEST_MANIFEST_SHA256,
    METRIC_NAMES,
    MODEL_NAMES,
    MODEL_REQUIRED_PARAMS,
    OVERVIEW_COLUMNS,
    PREDICTION_COLUMNS,
    REQUIRED_RUN_PARAMS,
    SUMMARY_COLUMNS,
    LockedBenchmarkContract,
    build_locked_test_manifest,
    calculate_manifest_sha256,
)


def _expect(condition: bool, message: str) -> None:
    """Fail explicitly so the assertion remains active under ``python -O``."""
    if not condition:
        pytest.fail(message)


@pytest.fixture
def contract() -> LockedBenchmarkContract:
    """Return the locked values without reading repository data."""
    return LockedBenchmarkContract(
        dataset_version="group_dataset_v1",
        snapshot_name="ohlcv_full_current",
        target="next_close",
        horizon=1,
    )


@pytest.fixture
def manifest(contract: LockedBenchmarkContract) -> pd.DataFrame:
    """Build a deterministic 78-row synthetic horizon-one manifest."""
    timestamps = pd.date_range("2026-01-01", periods=79, freq="D", tz="UTC")
    current = np.linspace(20.0, 27.7, 78)
    actual = current + np.where(np.arange(78) % 2 == 0, 0.2, -0.1)
    return pd.DataFrame(
        {
            "dataset_version": contract.dataset_version,
            "snapshot_name": contract.snapshot_name,
            "symbol": contract.symbol,
            "timeframe": contract.timeframe,
            "split": contract.split,
            "input_ts": timestamps[:-1].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "target_ts": timestamps[1:].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "current_close": current,
            "actual_close": actual,
        }
    )


def _prediction_frame(
    manifest: pd.DataFrame,
    model: str = "xgboost",
    run_id: str = "a" * 32,
) -> pd.DataFrame:
    manifest_hash = calculate_manifest_sha256(manifest)
    frame = manifest.copy()
    frame.insert(2, "test_manifest_sha256", manifest_hash)
    frame.insert(5, "model", model)
    frame["predicted_close"] = frame["actual_close"] + 0.15
    frame["run_id"] = run_id
    frame["seed"] = 42
    return frame.loc[:, PREDICTION_COLUMNS]


def _evaluation(
    predictions: pd.DataFrame,
    model: str = "xgboost",
    run_id: str = "a" * 32,
) -> benchmark.ModelEvaluation:
    metrics = benchmark.recompute_metrics(predictions)
    return benchmark.ModelEvaluation(
        model=model,
        run_id=run_id,
        mlflow_metrics=metrics.copy(),
        recomputed_metrics=metrics.copy(),
        predictions=predictions,
    )


def _summary_frame(
    predictions: pd.DataFrame,
    contract: LockedBenchmarkContract,
    model: str = "xgboost",
    run_id: str = "a" * 32,
    status: str = "preliminary",
) -> pd.DataFrame:
    metrics = benchmark.recompute_metrics(predictions)
    row: dict[str, Any] = {
        "dataset_version": contract.dataset_version,
        "snapshot_name": contract.snapshot_name,
        "test_manifest_sha256": predictions["test_manifest_sha256"].iloc[0],
        "symbol": contract.symbol,
        "timeframe": contract.timeframe,
        "model": model,
        "split": contract.split,
        "n_samples": len(predictions),
        **metrics,
        "run_id": run_id,
        "seed": contract.seed,
        "status": status,
    }
    return pd.DataFrame([row], columns=SUMMARY_COLUMNS)


def _run_ids() -> dict[str, str]:
    return {model: str(index + 1) * 32 for index, model in enumerate(MODEL_NAMES)}


def _args(run_ids: dict[str, str], output_dir: Path) -> argparse.Namespace:
    values = {f"{model}_run_id": run_id for model, run_id in run_ids.items()}
    return argparse.Namespace(**values, output_dir=output_dir)


def _params(
    model: str,
    contract: LockedBenchmarkContract,
    manifest_hash: str,
) -> dict[str, str]:
    params = {
        "dataset_version": contract.dataset_version,
        "snapshot_name": contract.snapshot_name,
        "test_manifest_sha256": manifest_hash,
        "symbol": contract.symbol,
        "timeframe": contract.timeframe,
        "model": model,
        "target": contract.target,
        "horizon": str(contract.horizon),
        "seed": str(contract.seed),
    }
    params.update({name: "1" for name in MODEL_REQUIRED_PARAMS[model]})
    if model == "arima":
        params.update(
            {
                "order_p": "1",
                "order_d": "1",
                "order_q": "1",
                "state_role": "pre_test_deployable",
                "observation_count": "444",
                "contains_test_history": "False",
            }
        )
    return params


def _fake_run(
    model: str,
    contract: LockedBenchmarkContract,
    manifest_hash: str,
    metrics: dict[str, float],
    *,
    status: str = "FINISHED",
    source_commit: str = "a" * 40,
) -> SimpleNamespace:
    return SimpleNamespace(
        info=SimpleNamespace(status=status),
        data=SimpleNamespace(
            params=_params(model, contract, manifest_hash),
            metrics=metrics,
            tags={"mlflow.source.git.commit": source_commit},
        ),
    )


def test_cli_requires_all_four_explicit_run_ids(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        benchmark.parse_args(
            [
                "--xgboost-run-id",
                "x",
                "--random-forest-run-id",
                "r",
                "--gru-run-id",
                "g",
                "--output-dir",
                str(tmp_path),
            ]
        )


def test_explicit_run_mapping_rejects_duplicate_ids(tmp_path: Path) -> None:
    run_ids = _run_ids()
    run_ids["arima"] = run_ids["gru"]
    with pytest.raises(benchmark.BenchmarkValidationError, match="distinct"):
        benchmark.explicit_run_ids(_args(run_ids, tmp_path))


def test_explicit_run_mapping_never_discovers_latest(tmp_path: Path) -> None:
    run_ids = _run_ids()
    actual = benchmark.explicit_run_ids(_args(run_ids, tmp_path))
    _expect(actual == run_ids, "Evaluator changed the explicit model-to-run mapping")


@pytest.mark.parametrize(
    ("mutation", "expected_check"),
    [
        ("missing_column", "prediction_schema"),
        ("extra_index", "prediction_schema"),
        ("wrong_order", "prediction_schema"),
        ("short_rows", "prediction_rows"),
        ("wrong_model", "prediction_model"),
        ("wrong_seed", "prediction_seed"),
        ("wrong_run_id", "prediction_run_id"),
        ("duplicate_target", "prediction_chronology"),
        ("unordered_target", "prediction_chronology"),
        ("input_not_before_target", "prediction_chronology"),
        ("nan", "prediction_finite"),
        ("positive_inf", "prediction_finite"),
        ("negative_inf", "prediction_finite"),
    ],
)
def test_prediction_contract_rejects_invalid_content(
    mutation: str,
    expected_check: str,
    contract: LockedBenchmarkContract,
    manifest: pd.DataFrame,
) -> None:
    run_id = "a" * 32
    frame = _prediction_frame(manifest, run_id=run_id)
    if mutation == "missing_column":
        frame = frame.drop(columns=["predicted_close"])
    elif mutation == "extra_index":
        frame.insert(0, "Unnamed: 0", np.arange(len(frame)))
    elif mutation == "wrong_order":
        columns = list(frame.columns)
        columns[-1], columns[-2] = columns[-2], columns[-1]
        frame = frame.loc[:, columns]
    elif mutation == "short_rows":
        frame = frame.iloc[:-1].copy()
    elif mutation == "wrong_model":
        frame["model"] = "gru"
    elif mutation == "wrong_seed":
        frame["seed"] = 7
    elif mutation == "wrong_run_id":
        frame["run_id"] = "wrong"
    elif mutation == "duplicate_target":
        frame.loc[1, "target_ts"] = frame.loc[0, "target_ts"]
    elif mutation == "unordered_target":
        frame.loc[[0, 1], "target_ts"] = frame.loc[[1, 0], "target_ts"].to_numpy()
    elif mutation == "input_not_before_target":
        frame.loc[0, "input_ts"] = frame.loc[0, "target_ts"]
    elif mutation == "nan":
        frame.loc[0, "predicted_close"] = np.nan
    elif mutation == "positive_inf":
        frame.loc[0, "predicted_close"] = np.inf
    elif mutation == "negative_inf":
        frame.loc[0, "predicted_close"] = -np.inf
    evaluation = benchmark.ModelEvaluation(model="xgboost", run_id=run_id)
    benchmark.validate_prediction_frame(
        evaluation,
        frame,
        contract,
        manifest,
        calculate_manifest_sha256(manifest),
    )
    failures = {check.name for check in evaluation.checks if check.status == "fail"}
    _expect(
        expected_check in failures,
        f"{mutation} did not fail expected check {expected_check}: {failures}",
    )


def test_same_hash_string_cannot_hide_row_mismatch(
    contract: LockedBenchmarkContract,
    manifest: pd.DataFrame,
) -> None:
    run_id = "a" * 32
    frame = _prediction_frame(manifest, run_id=run_id)
    frame.loc[0, "actual_close"] += 1.0
    evaluation = benchmark.ModelEvaluation(model="xgboost", run_id=run_id)
    benchmark.validate_prediction_frame(
        evaluation,
        frame,
        contract,
        manifest,
        calculate_manifest_sha256(manifest),
    )
    locked_check = next(
        check for check in evaluation.checks if check.name == "locked_manifest_rows"
    )
    _expect(locked_check.status == "fail", "Row mismatch passed on a copied hash")


@pytest.mark.parametrize(
    "column", ["input_ts", "target_ts", "current_close", "actual_close"]
)
def test_each_manifest_identity_field_is_checked(
    column: str,
    contract: LockedBenchmarkContract,
    manifest: pd.DataFrame,
) -> None:
    frame = _prediction_frame(manifest)
    if column.endswith("_ts"):
        frame.loc[0, column] = "2030-01-01T00:00:00Z"
    else:
        frame.loc[0, column] += 1.0
    evaluation = benchmark.ModelEvaluation(model="xgboost", run_id="a" * 32)
    benchmark.validate_prediction_frame(
        evaluation,
        frame,
        contract,
        manifest,
        calculate_manifest_sha256(manifest),
    )
    locked_check = next(
        check for check in evaluation.checks if check.name == "locked_manifest_rows"
    )
    _expect(locked_check.status == "fail", f"{column} mismatch was not detected")


def test_metric_recomputation_uses_percent_mape_and_naive_current_close(
    manifest: pd.DataFrame,
) -> None:
    frame = _prediction_frame(manifest)
    metrics = benchmark.recompute_metrics(frame)
    actual = frame["actual_close"].to_numpy()
    predicted = frame["predicted_close"].to_numpy()
    current = frame["current_close"].to_numpy()
    expected_mape = float(np.mean(np.abs((actual - predicted) / actual)) * 100)
    expected_naive = float(np.sqrt(np.mean((actual - current) ** 2)))
    _expect(
        np.isclose(metrics["mape_pct"], expected_mape, rtol=0.0, atol=1e-15),
        "MAPE is not stored as percent",
    )
    _expect(
        np.isclose(metrics["naive_rmse"], expected_naive, rtol=0.0, atol=1e-15),
        "Naive prediction is not current_close",
    )


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_metric_recomputation_rejects_non_finite(
    value: float,
    manifest: pd.DataFrame,
) -> None:
    frame = _prediction_frame(manifest)
    frame.loc[0, "predicted_close"] = value
    with pytest.raises(benchmark.BenchmarkValidationError, match="NaN or infinity"):
        benchmark.recompute_metrics(frame)


def test_summary_accepts_preliminary_but_rejects_metric_tampering(
    contract: LockedBenchmarkContract,
    manifest: pd.DataFrame,
) -> None:
    frame = _prediction_frame(manifest)
    evaluation = _evaluation(frame)
    summary = _summary_frame(frame, contract)
    summary.loc[0, "rmse"] += 0.5
    benchmark.validate_summary_frame(
        evaluation,
        summary,
        contract,
        calculate_manifest_sha256(manifest),
    )
    checks = {check.name: check.status for check in evaluation.checks}
    _expect(checks["summary_status"] == "pass", "preliminary status was rejected")
    _expect(checks["summary_metrics"] == "fail", "tampered summary metric passed")


@pytest.mark.parametrize(
    "mutation", ["missing", "extra", "order", "status", "explicit_invalid"]
)
def test_summary_contract_rejects_schema_or_status(
    mutation: str,
    contract: LockedBenchmarkContract,
    manifest: pd.DataFrame,
) -> None:
    frame = _prediction_frame(manifest)
    summary = _summary_frame(frame, contract)
    if mutation == "missing":
        summary = summary.drop(columns=["mae"])
    elif mutation == "extra":
        summary["unexpected"] = 1
    elif mutation == "order":
        summary = summary.loc[:, list(reversed(summary.columns))]
    elif mutation == "status":
        summary.loc[0, "status"] = "excluded"
    elif mutation == "explicit_invalid":
        summary.loc[0, "status"] = "invalid"
    evaluation = _evaluation(frame)
    benchmark.validate_summary_frame(
        evaluation,
        summary,
        contract,
        calculate_manifest_sha256(manifest),
    )
    _expect(
        bool(evaluation.failure_reasons),
        f"Invalid summary mutation {mutation} was accepted",
    )


def test_mlflow_metric_mismatch_is_rejected(
    contract: LockedBenchmarkContract,
    manifest: pd.DataFrame,
) -> None:
    frame = _prediction_frame(manifest)
    evaluation = _evaluation(frame)
    evaluation.mlflow_metrics["mae"] += 0.01
    summary = _summary_frame(frame, contract)
    benchmark.validate_summary_frame(
        evaluation,
        summary,
        contract,
        calculate_manifest_sha256(manifest),
    )
    status = next(
        check.status for check in evaluation.checks if check.name == "mlflow_metrics"
    )
    _expect(status == "fail", "MLflow metric mismatch was accepted")


def test_metadata_rejects_unfinished_missing_params_and_metrics(
    monkeypatch: pytest.MonkeyPatch,
    contract: LockedBenchmarkContract,
    manifest: pd.DataFrame,
) -> None:
    manifest_hash = calculate_manifest_sha256(manifest)
    predictions = _prediction_frame(manifest)
    metrics = benchmark.recompute_metrics(predictions)
    run = _fake_run("xgboost", contract, manifest_hash, metrics, status="RUNNING")
    run.data.params.pop("horizon")
    run.data.metrics.pop("rmse")
    monkeypatch.setattr(benchmark, "git_is_ancestor", lambda *args, **kwargs: True)
    evaluation = benchmark.ModelEvaluation(model="xgboost", run_id="a" * 32)
    benchmark.validate_run_metadata(evaluation, run, contract, manifest_hash, "a" * 40)
    failed = {check.name for check in evaluation.checks if check.status == "fail"}
    _expect(
        {"run_status", "required_params", "required_metrics"}.issubset(failed),
        f"Metadata failures were incomplete: {failed}",
    )


def test_metadata_rejects_explicitly_superseded_run(
    monkeypatch: pytest.MonkeyPatch,
    contract: LockedBenchmarkContract,
    manifest: pd.DataFrame,
) -> None:
    manifest_hash = calculate_manifest_sha256(manifest)
    metrics = benchmark.recompute_metrics(_prediction_frame(manifest))
    run = _fake_run("xgboost", contract, manifest_hash, metrics)
    run.data.tags["candidate_status"] = "superseded"
    monkeypatch.setattr(benchmark, "git_is_ancestor", lambda *args, **kwargs: True)
    evaluation = benchmark.ModelEvaluation(model="xgboost", run_id="a" * 32)
    benchmark.validate_run_metadata(evaluation, run, contract, manifest_hash, "a" * 40)
    lifecycle = next(
        check for check in evaluation.checks if check.name == "run_lifecycle"
    )
    _expect(lifecycle.status == "fail", "Superseded run was accepted")


@pytest.mark.parametrize(
    ("field", "wrong"),
    [
        ("model", "gru"),
        ("seed", "7"),
        ("target", "timestamp"),
        ("horizon", "2"),
        ("snapshot_name", "wrong"),
        ("test_manifest_sha256", "0" * 64),
    ],
)
def test_metadata_rejects_wrong_contract_param(
    field: str,
    wrong: str,
    monkeypatch: pytest.MonkeyPatch,
    contract: LockedBenchmarkContract,
    manifest: pd.DataFrame,
) -> None:
    manifest_hash = calculate_manifest_sha256(manifest)
    metrics = benchmark.recompute_metrics(_prediction_frame(manifest))
    run = _fake_run("xgboost", contract, manifest_hash, metrics)
    run.data.params[field] = wrong
    monkeypatch.setattr(benchmark, "git_is_ancestor", lambda *args, **kwargs: True)
    evaluation = benchmark.ModelEvaluation(model="xgboost", run_id="a" * 32)
    benchmark.validate_run_metadata(evaluation, run, contract, manifest_hash, "a" * 40)
    status = next(
        check.status for check in evaluation.checks if check.name == "contract_params"
    )
    _expect(status == "fail", f"Wrong contract field {field} was accepted")


def test_source_commit_outside_develop_and_current_head_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluation = benchmark.ModelEvaluation(model="xgboost", run_id="a" * 32)
    evaluation.source_commit = "b" * 40
    monkeypatch.setattr(benchmark, "git_is_ancestor", lambda *args, **kwargs: False)
    benchmark._validate_source_provenance(evaluation, "a" * 40, Path("."))
    status = next(
        check.status for check in evaluation.checks if check.name == "source_commit"
    )
    _expect(status == "fail", "Untrusted source commit was accepted")


def test_current_committed_evaluator_head_is_allowed_pre_merge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluation = benchmark.ModelEvaluation(model="xgboost", run_id="a" * 32)
    evaluation.source_commit = "a" * 40

    def ancestry(ancestor: str, descendant: str, repo_root: Path) -> bool:
        return descendant == evaluation.source_commit

    monkeypatch.setattr(benchmark, "git_is_ancestor", ancestry)
    benchmark._validate_source_provenance(evaluation, "a" * 40, Path("."))
    statuses = {check.name: check.status for check in evaluation.checks}
    _expect(statuses["source_commit"] == "pass", "Committed feature HEAD was rejected")
    _expect(
        statuses["minimum_implementation_commit"] == "pass",
        "Minimum implementation ancestry was rejected",
    )


@pytest.mark.parametrize("missing_kind", ["prediction", "summary", "model"])
def test_required_artifact_gate_rejects_missing_files(missing_kind: str) -> None:
    evaluation = benchmark.ModelEvaluation(model="xgboost", run_id="a" * 32)
    paths = [
        "predictions/run.csv",
        "metrics/run.csv",
        "model/MLmodel",
        "preprocessing/standard_scaler.joblib",
    ]
    if missing_kind == "prediction":
        paths.remove("predictions/run.csv")
    elif missing_kind == "summary":
        paths.remove("metrics/run.csv")
    elif missing_kind == "model":
        paths.remove("model/MLmodel")
    evaluation.artifact_paths = paths
    prediction, summary = benchmark.validate_required_artifacts(evaluation)
    _expect(
        bool(evaluation.failure_reasons),
        f"Missing {missing_kind} artifact was accepted",
    )
    if missing_kind in {"prediction", "summary"}:
        _expect(
            prediction is None and summary is None,
            "Missing CSV did not stop CSV resolution",
        )


def test_model_reload_exception_marks_run_invalid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    evaluation = benchmark.ModelEvaluation(model="xgboost", run_id="a" * 32)

    def fail(*args: Any, **kwargs: Any) -> None:
        raise ValueError("broken artifact")

    monkeypatch.setattr(benchmark, "_validate_xgboost_artifact", fail)
    benchmark.validate_model_artifact(evaluation, object(), tmp_path)
    _expect(
        "Model artifact validation failed: broken artifact"
        in evaluation.failure_reasons,
        "Reload failure was not recorded",
    )


def test_naive_identity_mismatch_invalidates_offending_model(
    manifest: pd.DataFrame,
) -> None:
    evaluations = {
        model: _evaluation(
            _prediction_frame(manifest, model, str(index) * 32), model, str(index) * 32
        )
        for index, model in enumerate(MODEL_NAMES, start=1)
    }
    for evaluation in evaluations.values():
        evaluation.failure_reasons.clear()
    evaluations["gru"].recomputed_metrics["naive_rmse"] += 0.1
    result = benchmark.finalize_eligibility(evaluations)
    _expect(not result, "Naive mismatch did not fail the benchmark")
    _expect(
        evaluations["gru"].status == "invalid",
        "Offending GRU run was not marked invalid",
    )
    _expect(
        evaluations["arima"].status == "excluded",
        "Otherwise valid run was not excluded from incomplete ranking",
    )


def _rank_evaluations() -> dict[str, benchmark.ModelEvaluation]:
    values = {
        "xgboost": (0.4, 0.5, 0.60),
        "random_forest": (0.4, 0.5, 0.55),
        "gru": (0.3, 0.5, 0.40),
        "arima": (0.2, 0.4, 0.50),
    }
    evaluations: dict[str, benchmark.ModelEvaluation] = {}
    for model, (mae, rmse, direction) in values.items():
        metrics = {
            "mae": mae,
            "rmse": rmse,
            "mape_pct": 1.0,
            "directional_accuracy": direction,
            "naive_mae": 0.2,
            "naive_rmse": 0.3,
            "naive_mape_pct": 1.0,
            "naive_directional_accuracy": 0.1,
            "improvement_vs_naive_rmse_pct": -1.0,
        }
        evaluations[model] = benchmark.ModelEvaluation(
            model=model,
            run_id=model,
            status="valid",
            recomputed_metrics=metrics,
        )
    return evaluations


def test_ranking_uses_rmse_mae_and_directional_accuracy() -> None:
    ranking = benchmark.rank_valid_models(_rank_evaluations())
    _expect(
        [evaluation.model for evaluation in ranking]
        == ["arima", "gru", "xgboost", "random_forest"],
        "Protocol ranking order is incorrect",
    )


def test_ranking_uses_model_name_only_as_full_tie_fallback() -> None:
    evaluations = _rank_evaluations()
    shared = evaluations["xgboost"].recomputed_metrics.copy()
    for evaluation in evaluations.values():
        evaluation.recomputed_metrics = shared.copy()
    ranking = benchmark.rank_valid_models(evaluations)
    _expect(
        [evaluation.model for evaluation in ranking] == sorted(MODEL_NAMES),
        "Full metric tie is not deterministic by model name",
    )


def test_invalid_or_missing_model_cannot_be_ranked() -> None:
    evaluations = _rank_evaluations()
    evaluations["gru"].status = "invalid"
    with pytest.raises(benchmark.BenchmarkValidationError, match="four valid"):
        benchmark.rank_valid_models(evaluations)
    evaluations.pop("gru")
    with pytest.raises(benchmark.BenchmarkValidationError, match="four valid"):
        benchmark.rank_valid_models(evaluations)


def test_overview_uses_exact_protocol_schema_without_index(
    contract: LockedBenchmarkContract,
) -> None:
    evaluations = _rank_evaluations()
    ranking = benchmark.rank_valid_models(evaluations)
    rows = benchmark.build_overview_rows(evaluations, contract, "a" * 64, ranking)
    _expect(
        tuple(rows[0]) == OVERVIEW_COLUMNS,
        "Overview row schema differs from the protocol",
    )
    _expect([row["rank"] for row in rows] == [1, 2, 3, 4], "Ranks are invalid")


def test_report_contains_all_required_sections(
    contract: LockedBenchmarkContract,
) -> None:
    evaluations = _rank_evaluations()
    for evaluation in evaluations.values():
        evaluation.source_commit = "a" * 40
        evaluation.source_summary_status = "preliminary"
    ranking = benchmark.rank_valid_models(evaluations)
    report = benchmark.render_report(
        contract,
        "a" * 64,
        evaluations,
        ranking,
        "b" * 40,
        "2026-07-23T00:00:00Z",
        "python -m services.training.benchmark",
    )
    for section in (
        "Benchmark contract",
        "Ranking rule",
        "Official runs and eligibility",
        "Final ranking",
        "Exclusions",
        "Naive baseline comparison",
        "Cross-model validation",
        "Environment",
        "Reproduction command",
        "Limitations",
        "Conclusion",
    ):
        _expect(f"## {section}" in report, f"Report is missing {section}")


def test_locked_manifest_has_issue_20_hash(
    contract: LockedBenchmarkContract,
) -> None:
    manifest, manifest_hash = build_locked_test_manifest(contract)
    _expect(
        manifest_hash == EXPECTED_TEST_MANIFEST_SHA256,
        "Locked production manifest differs from the Issue #20 hash",
    )
    _expect(
        calculate_manifest_sha256(manifest) == EXPECTED_TEST_MANIFEST_SHA256,
        "Returned production manifest does not reproduce its locked hash",
    )


def test_atomic_publish_replaces_complete_directory(tmp_path: Path) -> None:
    output = tmp_path / "ACB_1d"
    output.mkdir()
    (output / "old.txt").write_text("old", encoding="utf-8")
    staged = tmp_path / "staged"
    staged.mkdir()
    for filename in benchmark.OUTPUT_FILENAMES:
        (staged / filename).write_text(filename, encoding="utf-8")
    benchmark.publish_staged_outputs(staged, output)
    _expect(
        sorted(path.name for path in output.iterdir())
        == sorted(benchmark.OUTPUT_FILENAMES),
        "Atomic publish left old or partial output",
    )


def test_stage_outputs_are_deterministic_and_leave_sources_untouched(
    tmp_path: Path,
    contract: LockedBenchmarkContract,
) -> None:
    evaluations = _rank_evaluations()
    ranking = benchmark.rank_valid_models(evaluations)
    rows = benchmark.build_overview_rows(evaluations, contract, "a" * 64, ranking)
    audit = {"status": "valid", "generated_at": "fixed"}
    source = tmp_path / "source.csv"
    source.write_text("immutable", encoding="utf-8")
    first = benchmark.stage_outputs(tmp_path / "one", rows, "report\n", audit)
    second = benchmark.stage_outputs(tmp_path / "two", rows, "report\n", audit)
    for filename in benchmark.OUTPUT_FILENAMES:
        _expect(
            (first / filename).read_bytes() == (second / filename).read_bytes(),
            f"{filename} output is nondeterministic",
        )
    _expect(source.read_text(encoding="utf-8") == "immutable", "Source was overwritten")


def test_failure_audit_does_not_create_partial_official_directory(
    tmp_path: Path,
) -> None:
    output = tmp_path / "ACB_1d"
    failure = benchmark.write_failure_audit(output, {"status": "invalid"})
    _expect(not output.exists(), "Failure created a partial official output directory")
    _expect(failure.is_file(), "Failure audit was not created")


def test_audit_json_contains_required_machine_readable_fields(
    contract: LockedBenchmarkContract,
) -> None:
    evaluations = _rank_evaluations()
    for evaluation in evaluations.values():
        evaluation.source_commit = "a" * 40
    ranking = benchmark.rank_valid_models(evaluations)
    payload = benchmark.build_audit_payload(
        contract,
        "a" * 64,
        evaluations,
        ranking,
        "b" * 40,
        "2026-07-23T00:00:00Z",
    )
    required = {
        "benchmark_contract",
        "models",
        "run_ids",
        "source_commits",
        "checks",
        "expected",
        "actual",
        "status",
        "failure_reason",
        "ranking_rule",
        "generated_at",
        "evaluator_source_commit",
    }
    _expect(required.issubset(payload), "Audit JSON is missing required fields")
    _expect("D:\\" not in json.dumps(payload), "Audit JSON leaked a Windows path")


def test_mlflow_evidence_logs_required_params_and_only_three_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    contract: LockedBenchmarkContract,
) -> None:
    for filename in benchmark.OUTPUT_FILENAMES:
        (tmp_path / filename).write_text(filename, encoding="utf-8")
    captured: dict[str, Any] = {"artifacts": []}

    class RunContext(AbstractContextManager[SimpleNamespace]):
        def __enter__(self) -> SimpleNamespace:
            return SimpleNamespace(info=SimpleNamespace(run_id="evaluator-run"))

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(benchmark, "init_mlflow", lambda: None)
    monkeypatch.setattr(
        benchmark.mlflow,
        "set_experiment",
        lambda value: captured.setdefault("experiment", value),
    )
    monkeypatch.setattr(benchmark.mlflow, "start_run", lambda **kwargs: RunContext())
    monkeypatch.setattr(
        benchmark.mlflow,
        "log_params",
        lambda value: captured.setdefault("params", value),
    )
    monkeypatch.setattr(
        benchmark.mlflow,
        "set_tags",
        lambda value: captured.setdefault("tags", value),
    )
    monkeypatch.setattr(
        benchmark.mlflow,
        "log_metrics",
        lambda value: captured.setdefault("metrics", value),
    )
    monkeypatch.setattr(
        benchmark.mlflow,
        "log_artifact",
        lambda value: captured["artifacts"].append(Path(value).name),
    )
    evaluations = _rank_evaluations()
    ranking = benchmark.rank_valid_models(evaluations)
    run_id = benchmark.log_benchmark_evidence(
        tmp_path,
        contract,
        "a" * 64,
        evaluations,
        "b" * 40,
        ranking,
    )
    _expect(run_id == "evaluator-run", "Unexpected evaluator run ID")
    _expect(
        set(captured["artifacts"]) == set(benchmark.OUTPUT_FILENAMES),
        "MLflow evidence did not contain exactly three benchmark artifacts",
    )
    _expect(
        all(f"{model}_run_id" in captured["params"] for model in MODEL_NAMES),
        "MLflow evidence is missing source run IDs",
    )
    _expect(
        captured["tags"]["register_as_model"] == "false",
        "Evaluator was marked for model registration",
    )


def test_artifact_listing_is_sorted_and_recursive() -> None:
    tree = {
        "": [
            SimpleNamespace(path="z.txt", is_dir=False),
            SimpleNamespace(path="model", is_dir=True),
        ],
        "model": [
            SimpleNamespace(path="model/MLmodel", is_dir=False),
            SimpleNamespace(path="model/data", is_dir=True),
        ],
        "model/data": [SimpleNamespace(path="model/data/model.bin", is_dir=False)],
    }

    class Client:
        def list_artifacts(self, run_id: str, path: str) -> list[SimpleNamespace]:
            return tree[path]

    actual = benchmark._list_artifacts_recursive(Client(), "run")
    _expect(
        actual == ["model/MLmodel", "model/data/model.bin", "z.txt"],
        "Artifact recursion is incomplete or nondeterministic",
    )


def test_missing_run_is_recorded_without_fallback(
    contract: LockedBenchmarkContract,
    manifest: pd.DataFrame,
    tmp_path: Path,
) -> None:
    class Client:
        def get_run(self, run_id: str) -> None:
            raise LookupError(run_id)

    evaluation = benchmark.evaluate_model_run(
        Client(),
        "xgboost",
        "missing",
        contract,
        manifest,
        calculate_manifest_sha256(manifest),
        "a" * 40,
        tmp_path,
        reload_model=False,
    )
    _expect(evaluation.status == "invalid", "Missing run changed status")
    _expect(
        any(
            check.name == "run_exists" and check.status == "fail"
            for check in evaluation.checks
        ),
        "Missing run was not recorded",
    )


def test_reproduction_command_contains_all_explicit_ids(tmp_path: Path) -> None:
    command = benchmark.benchmark_command(_run_ids(), tmp_path)
    for model in MODEL_NAMES:
        option = model.replace("_", "-")
        _expect(f"--{option}-run-id" in command, f"Command missing {model}")
    _expect("latest" not in command.lower(), "Command contains latest-run discovery")


def test_source_summary_is_not_mutated(
    contract: LockedBenchmarkContract,
    manifest: pd.DataFrame,
) -> None:
    frame = _prediction_frame(manifest)
    summary = _summary_frame(frame, contract, status="preliminary")
    original = summary.copy(deep=True)
    evaluation = _evaluation(frame)
    benchmark.validate_summary_frame(
        evaluation,
        summary,
        contract,
        calculate_manifest_sha256(manifest),
    )
    _expect(summary.equals(original), "Evaluator mutated the source summary")


def test_required_param_contract_covers_every_model() -> None:
    _expect(
        set(MODEL_REQUIRED_PARAMS) == set(MODEL_NAMES),
        "Model-specific param contract is incomplete",
    )
    _expect(
        {"model", "target", "horizon", "seed"}.issubset(REQUIRED_RUN_PARAMS),
        "Shared required params are incomplete",
    )


def test_metric_contract_has_no_mse_alias() -> None:
    _expect("rmse" in METRIC_NAMES, "RMSE is missing")
    _expect("mse" not in METRIC_NAMES, "MSE was accepted into benchmark metrics")


def test_main_returns_nonzero_for_contract_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        benchmark,
        "run_benchmark",
        lambda args: (_ for _ in ()).throw(
            benchmark.BenchmarkValidationError("contract fail")
        ),
    )
    exit_code = benchmark.main(
        [
            "--xgboost-run-id",
            "x",
            "--random-forest-run-id",
            "r",
            "--gru-run-id",
            "g",
            "--arima-run-id",
            "a",
            "--output-dir",
            str(tmp_path),
        ]
    )
    _expect(exit_code == 1, "Contract failure did not produce a nonzero exit code")
