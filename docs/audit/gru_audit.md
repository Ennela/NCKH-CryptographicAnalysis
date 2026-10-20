# GRU Audit Report

## 1. Target Audit
- **Target hiện tại:** `next_close`
- **Horizon:** 1 day
- **X[t] dự đoán y[t+1]:** YES
- **Evidence:** 
  - File: `services/training/train_gru.py`
  - Function: `_build_continuous_features` (dòng 244-246) và `_collect_sequence_records` (dòng 297, 302, 308).
  - File: `shared/dataset/loader.py`
  - Function: `_add_split_and_target` (dòng 274: `result["next_close"] = result.groupby("split", sort=False)["close"].shift(-horizon)`)
  - Target được lấy từ `next_close` ở thời điểm `t`. Do `next_close` ở `t` chính là `close` ở `t+1`, việc dùng chuỗi kết thúc tại `t` để dự đoán target tại `t` tương đương với `X[t] -> y[t+1]`.
- **Status:** ✅ PASS

## 2. Train / Validation / Test
- **Câu 1: Dữ liệu có được chia theo thứ tự thời gian không?** CÓ. (Evidence: `load_full` trong `shared/dataset/loader.py` dòng 225 sắp xếp theo `ts` trước khi chia split).
- **Câu 2: Test có nằm sau train không?** CÓ. (Evidence: `_add_split_and_target` gán train, val, test theo index tăng dần).
- **Câu 3: Có random shuffle không?** KHÔNG. (Evidence: `train_gru.py` dòng 377 `shuffle=False` trong `create_data_loader`).
- **Câu 4: Validation có được dùng để tuning không?** CÓ. (Evidence: `train_with_early_stopping` trong `train_gru.py` dùng validation loss để early stopping).
- **Câu 5: Test có được dùng để chọn model/hyperparameter không?** KHÔNG. (Evidence: Tập test chỉ được gọi một lần duy nhất trong `_evaluate_and_export`).
- **Status:** ✅ PASS

## 3. Data Leakage
- **Feature engineering:** Tính toán `moving_average_7` bằng hàm `.rolling(window=7).mean()` (dòng 240, `train_gru.py`). Hàm `rolling` mặc định dùng dữ liệu từ quá khứ đến hiện tại (`[t-6, t]`), không nhìn vào tương lai.
- Target `next_close` được `shift(-1)` theo từng `split` (dòng 274, `loader.py`). Điều này đảm bảo dòng cuối cùng của tập train sẽ có `next_close = NaN`. Khi tạo chuỗi (dòng 294, `train_gru.py`), các dòng có target NaN bị bỏ qua, nên không bao giờ xảy ra việc dùng `close` của tập `val` làm target cho một chuỗi thuộc tập `train`.
- **Status:** ✅ PASS

## 4. Scaling
- **Scaler được fit trên phần nào?** Train only
- **Evidence:** File `services/training/train_gru.py`, function `_fit_train_scalers` (dòng 254-262). Mã nguồn lọc ra `train_rows = featured["split"].eq("train")` và chỉ gọi `.fit()` trên phần dữ liệu này. Tập `val` và `test` chỉ được `.transform()`.
- **Status:** ✅ PASS

## 5. Naive Baseline & Metric Comparison
- **Naive baseline calculation:** Naive prediction là `current_close` của ngày `t`.
- **Comparison:** Trong hàm `evaluate_predictions` (`train_gru.py`, dòng 553), model prediction và naive prediction đều được tính toán và so sánh trên cùng một mảng `actual` và `current_close` tương ứng với mỗi record trong tập test. Hai phương pháp được đánh giá công bằng trên cùng số samples.
- **Metric:** RMSE tính đúng công thức `sqrt(mean((actual - prediction)^2))` (`_error_metrics` dòng 515).
- **Status:** ✅ PASS

## 6. GRU Sequence / Lookback
- **Sequence Length:** `config.sequence_length = 30` (dòng 118).
- **Lookback window:** Trong `_collect_sequence_records` (dòng 304), `window_start = input_index - sequence_length + 1`. Chuỗi input có độ dài 30, bắt đầu từ `t-29` và kết thúc ở `t` (bao gồm cả `t`).
- **Target index:** Target được gán là giá trị tại `input_index` (tức là `t`). Vì cột target là `next_close`, nên target tại thời điểm `t` chính là giá của ngày `t+1`.
- **Kết luận:** Model nhận sequence Ngày 1 → 30 để dự đoán Ngày 31. Hoàn toàn chính xác, không dùng tương lai để dự đoán tương lai.
- **Status:** ✅ PASS

## 7. Conclusion
- Current pipeline: 
  - [x] Valid
  - [ ] Has issues
  - [ ] Need further investigation
- **Issues:** Pipeline của mô hình GRU được triển khai rất cẩn thận, đặc biệt là cách xử lý việc cross-split boundary để tránh leak data, và việc dùng scaler chỉ fit trên train set. Không phát hiện ra issue P0 nào trong logic của GRU. Nguyên nhân kết quả GRU tệ hơn Naive có thể do bản thân mô hình chưa được tune tốt hoặc bản chất dữ liệu chuỗi thời gian nhiễu làm GRU khó vượt qua được Naive baseline, chứ không phải do lỗi pipeline (data leakage hay chia split sai).
