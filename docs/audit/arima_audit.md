# ARIMA Model Audit — NCKH-CryptographicAnalysis

This audit inspects the ARIMA rolling benchmark implementation in this repository and answers the requested questions based on the code in `services/training/train_arima.py` and `services/training/data_loader.py`.

Files reviewed:
- [services/training/train_arima.py](services/training/train_arima.py)
- [services/training/data_loader.py](services/training/data_loader.py)

---

1) Đang dự đoán target gì?

- Target được xác định là `next_close` (giá close tiếp theo, horizon = 1). Điều này được định nghĩa trong `train_arima.py` tại hằng số `TARGET_COLUMN = "next_close"` và kiểm tra hợp đồng dữ liệu trong `load_dataset_metadata()` (yêu cầu `payload.get("target") == {"mode": TARGET_COLUMN, "horizon": 1}`).
- See: [services/training/train_arima.py](services/training/train_arima.py) (load_dataset_metadata and TARGET_COLUMN).

2) Train/validation/test chia như thế nào?

- Dữ liệu dùng trong benchmark là một "locked" frame có cột `split` với các giá trị `train`, `val`, `test` (không xáo trộn). `train_arima.py` thực thi `_normalise_full_frame()` để đảm bảo các split tồn tại và là tuần tự/contiguous; `_build_split_pairs()` tạo các cặp (input_ts → target_ts) trong cùng một split mà không cross boundary.
- `prepare_rolling_data()` lấy `train` (toàn bộ lịch sử train), xây `validation_pairs` từ split `val` và `test_pairs` từ split `test`.
- Tóm lại: split là time-series sequential split (chronological, không shuffle) và benchmark tiến theo thứ tự thời gian.
- See: [services/training/train_arima.py](services/training/train_arima.py) (functions `_normalise_full_frame`, `_build_split_pairs`, `prepare_rolling_data`).

3) Có data leakage không?

- Không phát hiện leakage. Lý do:
  - Dữ liệu bắt buộc phải có cột `split` và `_normalise_full_frame()` từ chối nếu các split không tuần tự hoặc nếu `target` vượt qua boundary.
  - Khi rolling qua validation/test, `_roll_one_split()` chỉ `update()` lịch sử bằng actual values sau khi tạo dự báo; mô hình không thấy tương lai trước khi dự báo.
  - `services/training/data_loader.py` cũng tạo target bằng `shift(-horizon)` qua `add_target()` và khuyến cáo gọi trước khi split; các hàm split của `DataLoader` chia theo thứ tự thời gian (no shuffle).
- Kết luận: tuân thủ nguyên tắc nhân quả của chuỗi thời gian — không có data leakage trong pipeline đánh giá ARIMA hiện tại.
- See: [services/training/train_arima.py](services/training/train_arima.py) (`_roll_one_split`, `prepare_rolling_data`) and [services/training/data_loader.py](services/training/data_loader.py) (`add_target`, `prepare_train_validation_test_split`).

4) Scaling có đúng không?

- ARIMA baseline (`ARIMABaseline`) được khởi tạo và `model.fit(prepared.train_close)` được gọi với mảng `close` gốc (không thấy code scaling trong `train_arima.py`). `prepare_rolling_data()` cung cấp `train_close` trực tiếp từ cột `close` của locked frame.
- `services/training/data_loader.py` engineer features cho các mô hình khác (returns, lags, rolling stats), nhưng ARIMA benchmark dùng trực tiếp `close` (và nội tại ARIMA sử dụng differencing theo order d nếu cần). Vì vậy không cần scaling phức tạp cho ARIMA ở đây; pipeline không áp dụng StandardScaler/MinMax trước cho ARIMA.
- Kết luận: scaling không được sử dụng cho ARIMA (đúng với cách triển khai baseline trên giá gốc/differencing), và đó là hành vi hợp lý cho mô hình ARIMA một-step.
- See: [services/training/train_arima.py](services/training/train_arima.py) (use of `train_close`), and `ARIMABaseline` usage in `run_rolling_evaluation`.

5) Test set của model có giống test set của Naive không?

- Có. `evaluate_predictions()` tính metrics trên cùng một manifest (actual) và so sánh `predicted` (kết quả ARIMA) với `current_close` (được dùng làm Naive baseline). Hàm này trả cả `naive_mae`, `naive_rmse`, `naive_mape_pct` và `naive_directional_accuracy` từ cùng bộ target.
- Ngoài ra, manifest được tạo từ `prepared.test_pairs` (cùng ticker ACB, timeframe 1d khi chạy command) nên cả ARIMA và Naive dùng cùng tập test, cùng số mẫu target.
- Kết luận: test set của ARIMA và Naive là đồng nhất trong pipeline đánh giá.
- See: [services/training/train_arima.py](services/training/train_arima.py) (`evaluate_predictions` uses `current_close` as naive baseline).

6) Metric được tính như thế nào?

- Metrics được tính trong `train_arima.py`:
  - `_error_metrics(actual, predicted)` → returns MAE, RMSE, MAPE% (MAPE = mean(|error / actual|) * 100). MAPE explicitly raises if any actual == 0.
  - `_directional_accuracy(actual, predicted, current)` → fraction where sign(predicted - current) == sign(actual - current).
  - `evaluate_predictions()` computes `mae`, `rmse`, `mape_pct`, `directional_accuracy` for ARIMA and the same metrics for Naive baseline (using `current_close` as naive predicted value). It also computes `improvement_vs_naive_rmse_pct`.
- See: [services/training/train_arima.py](services/training/train_arima.py) (`_error_metrics`, `_directional_accuracy`, `evaluate_predictions`).

7) Có vấn đề gì phát hiện được?

- Functional correctness: pipeline chứa nhiều validation asserts (chronological timestamps, contiguous splits, no NaN/Inf) và kiểm tra metadata consistency; điều này tăng độ tin cậy audit.
- Observed behavior (from runs): ARIMA performance in the example run is only slightly better than the Naive baseline (small improvement in RMSE). Điều này có thể phản ánh đặc thù dữ liệu tài chính (sóng nhỏ, high noise), và là thông tin chứ không phải bug.
- Potential concerns (not fixes, chỉ lưu ý):
  - Môi trường dependency: cài đặt toàn bộ `services/training/requirements.txt` trên Windows có thể gặp build issues cho một số wheel (NumPy/PyTorch/xgboost) — đã ghi trong `docs/dev_setup.md` (khuyến nghị conda). Đây là operational, không phải lỗi mô hình.
  - Nếu muốn tăng khả năng reproducibility: consider adding an explicit smoke-test that asserts Naive RMSE > 0 and that improvement metric is present (the code already asserts these relationships in `validate_metric_relationships`).
- See: code-wide validations in [services/training/train_arima.py](services/training/train_arima.py) (many `raise ValueError` and `validate_metric_relationships`).

8) Evidence nằm ở file/function nào?

- Target, split, and validation logic: [services/training/train_arima.py](services/training/train_arima.py) — functions/constants: `TARGET_COLUMN`, `load_dataset_metadata()`, `_normalise_full_frame()`, `_build_split_pairs()`, `prepare_rolling_data()`, `_roll_one_split()`, `run_rolling_evaluation()`, `evaluate_predictions()`.

- Data ingestion / target creation / sequential splits: [services/training/data_loader.py](services/training/data_loader.py) — functions: `add_target()`, `prepare_train_validation_test_split()`, `load_raw_data()`, and `engineer_features()` (documents that features use only past data).

---

Final notes / constraints
- I did not change dataset boundaries, test set, features, or model hyperparameters — this audit only inspects existing code and reports findings.
- If you want, I can (a) produce a concise checklist to include in `docs/audit/` to automate future audits, or (b) add a tiny unit test that asserts the locked dataset contract (`TARGET_COLUMN` and split continuity) to prevent regressions. Which would you prefer?
