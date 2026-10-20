# Benchmark Evidence — ACB 1d Four-Model Benchmark (Issue #20)

Ba file trong thư mục này là bản sao nguyên trạng (byte-identical) của output do
evaluator chính thức sinh ra, được commit vào Git để chuỗi bằng chứng không phụ
thuộc vào MLflow volume của một máy cá nhân.

## Nguồn gốc (provenance)

| Thuộc tính | Giá trị |
|---|---|
| Sinh bởi | `python -m services.training.benchmark` (xem lệnh đầy đủ trong `benchmark_report.md`) |
| Evaluator MLflow run | `f082a0252d7042f2a599b9554b2e68e0` (experiment `ACB_1d_four_model_benchmark`) |
| Evaluator source commit | `e449f0df93feca9c03726233d0ffe70de6d84202` |
| Generated at | `2026-07-23T14:30:15Z` |
| Test manifest SHA-256 | `62d82e13b48f337623235e20c2412d435395fef46fea5a24776ea895d1c8b828` |
| Trạng thái | `valid` — cả 4 run đạt toàn bộ quality gate |

Official run IDs: XGBoost `55ea7a8c7e3a49ed813ac6294fb26a80`, Random Forest
`db37627439134d56a250c8b898969d77`, GRU `65f56eab440e4fa9a5192bfaddbcc96e`,
ARIMA `f1ef301caa064c858da753982f1564dc`.

## Checksum (SHA-256) tại thời điểm commit

```text
2aa3ed74f78d3d6966ed68084212c6388b038fa47521cd633b9d3d9dd0fe7f39  benchmark_overview.csv
12003ee485df6cf929d1dcba38cae4b6cf44f4ab3a359f170c90ae9c07083ba2  benchmark_report.md
27bd62376aa89d64f00463c18bc84d1b23dfdb0af673cee78e29c8f557efa325  benchmark_audit.json
```

## Quy tắc

- KHÔNG sửa tay các file này. Nếu benchmark được chạy lại, tạo thư mục evidence
  mới (ví dụ `docs/evidence/ACB_1d_v2/`) thay vì ghi đè.
- File gốc nằm tại `artifacts/benchmarks/ACB_1d/` (bị `.gitignore`) và trong
  MLflow evaluator run nêu trên; bản backup offline kèm `mlflow.db` được nhóm
  trưởng giữ riêng.
