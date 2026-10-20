# ACB 1d Four-Model Benchmark

- Generated at: `2026-07-23T14:30:15Z`
- Evaluator source commit: `e449f0df93feca9c03726233d0ffe70de6d84202`
- Workflow: `single-contributor`

## Benchmark contract

- Dataset/snapshot: `group_dataset_v1` / `ohlcv_full_current`
- Symbol/timeframe: `ACB` / `1d`
- Target/horizon: `next_close` / `1`
- Split/seed/rows: `test` / `42` / `78`
- Manifest: `62d82e13b48f337623235e20c2412d435395fef46fea5a24776ea895d1c8b828`

## Ranking rule

RMSE ascending, then MAE ascending, then Directional Accuracy descending. Model name ascending is only a deterministic display fallback.

## Official runs and eligibility

| Model | Run ID | Source commit | Source summary | Eligibility |
|---|---|---|---|---|
| xgboost | `55ea7a8c7e3a49ed813ac6294fb26a80` | `e826aea5a06f4a2adb57f7aa3967cf03f3ce5471` | `preliminary` | valid |
| random_forest | `db37627439134d56a250c8b898969d77` | `e826aea5a06f4a2adb57f7aa3967cf03f3ce5471` | `preliminary` | valid |
| gru | `65f56eab440e4fa9a5192bfaddbcc96e` | `8a0d2dd3ec7a749aec2fedd8516e835390a9243d` | `preliminary` | valid |
| arima | `f1ef301caa064c858da753982f1564dc` | `ab1cf9af355211192c923c55aa042ff0413fdf6a` | `preliminary` | valid |

## Final ranking

| Rank | Model | MAE | RMSE | MAPE % | Directional accuracy | Improvement vs Naive RMSE % |
|---:|---|---:|---:|---:|---:|---:|
| 1 | arima | 0.27234869637307557 | 0.3882019113976774 | 1.3135850175231933 | 0.5128205128205128 | 0.5163771224311596 |
| 2 | random_forest | 0.5256917774782239 | 0.6368350104288949 | 2.5733422799615013 | 0.38461538461538464 | -63.20026293698421 |
| 3 | xgboost | 0.48262003678541876 | 0.6483500635961559 | 2.282851875973909 | 0.48717948717948717 | -66.15119948075981 |
| 4 | gru | 0.5393094254762704 | 0.7360494889815756 | 2.534783277033477 | 0.47435897435897434 | -88.62573220578025 |

## Exclusions

None among the four explicitly selected official runs.

## Naive baseline comparison

| MAE | RMSE | MAPE % | Directional accuracy |
|---:|---:|---:|---:|
| 0.2669230769230771 | 0.3902169022085419 | 1.2888783803605892 | 0.10256410256410256 |

## Cross-model validation

- Locked manifest row identity: PASS
- Canonical manifest hash: PASS
- Independent metric recomputation: PASS
- Naive baseline identity: PASS

## Environment

- Python: `3.11.15`
- Platform: `Linux-6.6.87.2-microsoft-standard-WSL2-x86_64-with-glibc2.41`
- MLflow: `2.11.3`
- NumPy: `1.26.4`
- Pandas: `2.3.3`

## Reproduction command

```text
python -m services.training.benchmark \
  --xgboost-run-id 55ea7a8c7e3a49ed813ac6294fb26a80 \
  --random-forest-run-id db37627439134d56a250c8b898969d77 \
  --gru-run-id 65f56eab440e4fa9a5192bfaddbcc96e \
  --arima-run-id f1ef301caa064c858da753982f1564dc \
  --output-dir artifacts/benchmarks/ACB_1d
```

## Limitations

- This is a single locked ACB 1d holdout benchmark, not a claim of statistical superiority across assets, periods, or repeated samples.
- A negative RMSE improvement means the model did not beat the horizon-one Naive baseline on this test manifest.
- Source training summaries remain immutable; benchmark eligibility is recorded separately by this evaluator.

## Conclusion

Issue #20 benchmark gates passed for all four official runs; the result is ready for PR review and post-merge verification.
