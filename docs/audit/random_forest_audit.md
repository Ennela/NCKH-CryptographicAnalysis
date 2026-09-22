# Random Forest Audit

**Người thực hiện:** Lê Hải Nam
**Ngày:** 2026-08-21
**Model:** Random Forest
**Symbol / Timeframe benchmark:** ACB / 1d

---

## 1. Target

**Target:** `next_close`

**Horizon:** 1 day

**Định nghĩa:** `y[t] = close[t+1]` — model nhận input tại ngày `t`, dự đoán giá đóng cửa ngày `t+1`

**Status: ✅ PASS**

Evidence:
- file: `services/training/train_random_forest.py`
- function: module-level constant
- line: 37–38 (`TARGET_COLUMN = "next_close"`, `HORIZON = 1`)

Evidence (target được tạo):
- file: `shared/dataset/loader.py`
- function: `_add_split_and_target()`
- line: 274 (`result["next_close"] = result.groupby("split", sort=False)["close"].shift(-horizon)`)

Evidence (contract enforce):
- file: `services/training/train_random_forest.py`
- function: `load_dataset_metadata()`
- line: 150–151 (`payload.get("target") != {"mode": TARGET_COLUMN, "horizon": HORIZON}` → raise)

Evidence (assert runtime):
- file: `services/training/train_random_forest.py`
- function: `_validate_target_frame()`
- line: 193–198 (assert `actual_close == next_close` và `input_ts < target_ts`)

---

## 2. Train / Validation / Test

**Tỉ lệ:** 70% train / 15% val / 15% test

**Chia theo thứ tự thời gian:** YES

**Có random shuffle:** KHÔNG

**Validation dùng để tuning:** KHÔNG — model chỉ `fit()` trên train, val không được dùng trong `train_random_forest.py`

**Test dùng để chọn hyperparameter:** KHÔNG — test chỉ được evaluate 1 lần ở cuối

**Status: ✅ PASS**

Evidence:
- file: `shared/dataset/loader.py`
- function: `_add_split_and_target()`
- line: 256–265

```python
train_end      = int(len(df) * 0.70)
validation_end = int(len(df) * 0.85)
result["split"] = "test"
result.loc[result.index < train_end, "split"] = "train"
result.loc[(index >= train_end) & (index < validation_end), "split"] = "val"
```

Evidence (train only):
- file: `services/training/train_random_forest.py`
- function: `train_model()`
- line: 243 (`model.fit(data.X_train, data.y_train)`)

---

## 3. Data Leakage

**Có look-ahead trong feature không:** KHÔNG

Tất cả feature đều chỉ dùng dữ liệu tại hoặc trước ngày `t`:

| Feature | Look-ahead? | Lý do |
|---------|-------------|-------|
| `open, high, low, close, volume` | KHÔNG | Giá trị ngày `t` |
| `return_1` | KHÔNG | `close[t]/close[t-1] - 1` |
| `volume_return_1` | KHÔNG | Tương tự |
| `close_lag_{1,3,5,10,20}` | KHÔNG | `shift(+period)` — quá khứ |
| `rolling_mean_{5,10,20}` | KHÔNG | `rolling(w).mean()` — chỉ đến `t` |
| `rolling_std_{5,10,20}` | KHÔNG | Tương tự |

**Status: ✅ PASS**

Evidence:
- file: `services/training/models/random_forest_features.py`
- function: `_add_causal_features()`
- line: 53–62

---

ℹ️ **Ghi nhận thêm: Cross-split boundary rolling (không phải lỗi nghiêm trọng)**

Rolling/lag được tính trên toàn bộ DataFrame liên tục **trước** khi tách thành split — các hàng đầu của `val` và `test` có thể dùng rolling/lag từ data của split trước.

Evidence:
- file: `services/training/models/random_forest_features.py`
- function: `build_random_forest_features()`
- line: 83–94

```python
featured = df.sort_values("ts", ...).copy()   # 522 hàng gộp chung
_add_causal_features(featured)                # tính rolling TRƯỚC khi tách
featured = featured.dropna(...)
return {split: featured[featured["split"] == split] ...}   # SAU ĐÓ mới tách
```

**Ví dụ cụ thể (ACB 1d, window=20):**

```
Hàng 347–366 : train  (20 hàng cuối train)
Hàng 367     : val    (hàng đầu tiên của val)

rolling_mean_20 tại hàng 367 (val)
= mean(close[348], ..., close[366], close[367])
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        19 giá trị này thuộc TRAIN
```

→ Feature của hàng đầu val dùng 19 giá trị từ train để tính rolling.

**Có phải data leakage không?**

| Câu hỏi | Trả lời |
|---------|---------|
| Rolling có nhìn vào dữ liệu **tương lai** không? | **KHÔNG** — chỉ nhìn về quá khứ |
| Train data có xảy ra **trước** val về thời gian không? | **CÓ** — hoàn toàn hợp lệ về nhân quả |
| Có bị gọi là cross-split contamination không? | **CÓ nhẹ** — chỉ ở ~20 hàng biên |
| RF có nhạy cảm với điều này không? | **Không** — tree-based model ít bị ảnh hưởng |
| Phổ biến trong ML thực tế không? | **Rất phổ biến** — hầu hết pipeline time series đều làm vậy |

**Kết luận:** Đây là **intentional design** — giữ data liên tục để tính lag/rolling đầy đủ, tránh mất hàng đầu mỗi split do NaN. Không phải lỗi. Cần ghi vào báo cáo như một design decision có ý thức.

---



## 4. Scaling

**Scaler được fit trên phần nào:** N/A — Random Forest không dùng scaler

**Lý do:** Tree-based model (RF) không nhạy với scale của feature. Không cần StandardScaler hay MinMaxScaler.

**Status: ✅ N/A**

Evidence:
- file: `services/training/train_random_forest.py`
- function: `prepare_dataset()`
- line: 219–230 (docstring: *"without fitting a target scaler"*)

---

## 5. Naive Baseline

**Định nghĩa Naive:**

```
Naive prediction(t+1) = close(t)
```

Tức là dự đoán ngày mai bằng giá đóng cửa hôm nay.

**Naive test samples:** 78

**Random Forest test samples:** 78

**Cùng actual array:** YES — `y_true = actual_close = next_close` dùng chung cho cả RF và Naive

**Status: ✅ PASS**

Evidence:
- file: `services/training/train_random_forest.py`
- function: `_calculate_metric_summary()`
- line: 383 (`naive_mae, naive_rmse, naive_mape_pct = _error_metrics(y_true, current_close)`)

---

## 6. Extrapolation

Random Forest là tree-based model — **không thể ngoại suy** ra ngoài vùng giá trị đã thấy trong training. Nếu `close_test > max(close_train)`, model RF sẽ predict tối đa bằng `max(y_train)`.

**Kết quả đo thực tế (ACB / 1d):**

| Split | Thời gian | next_close min | next_close max |
|-------|-----------|---------------|---------------|
| Train | 2024-05-24 → 2025-11-06 | 15.69 | **25.37** |
| Val   | 2025-11-07 → 2026-03-05 | 19.77 | 21.97 |
| Test  | 2026-03-06 → 2026-06-29 | 18.70 | **22.90** |

**Kiểm tra:**
- `test_max (22.90) ≤ train_max (25.37)` → **Không bị extrapolation phía trên**
- `test_min (18.70) ≥ train_min (15.69)` → **Không bị extrapolation phía dưới**

**Status: ✅ PASS**

Evidence:
- file: `shared/dataset/loader.py`
- function: `load_full()`
- Chạy trực tiếp với `load_full("ACB", "1d")` — xác nhận ngày 2026-08-21

---

## 7. Metric (RMSE)

**Công thức:**

```
RMSE = sqrt(mean((actual_close - predicted_close)²))
```

**actual có đúng không:** YES — `y_true = data.y_test = next_close`

**prediction có đúng không:** YES — `model.predict(X_test)` → float64 array

**Có NaN không:** KHÔNG — bị reject bởi `_metric_vector()` trước khi tính

**Có lệch index không:** KHÔNG — cùng `splits["test"]` DataFrame, cùng thứ tự

**Có prediction bị bỏ không:** KHÔNG — `len(predicted) == len(manifest)` được validate

**Status: ✅ PASS**

Evidence:
- file: `services/training/train_random_forest.py`
- function: `_error_metrics()`
- line: 342–352

---

## 8. Kết luận

**Pipeline hiện tại:**

- [x] Valid — không phát hiện lỗi methodology nghiêm trọng

**Issues phát hiện:**

| Mức | CHECK | Nội dung |
|-----|-------|----------|
| ℹ️ GHI NHẬN | CHECK 3 (Cross-split rolling) | Rolling/lag tính cross-split tại boundary — không phải future leakage, nhưng cần nhóm xác nhận là intentional design. |

**Không phát hiện lỗi methodology nghiêm trọng** (target sai, split sai, leakage, scaler sai, baseline sai, metric sai, extrapolation).

**Bảng tóm tắt PASS/FAIL:**

| CHECK | Nội dung | Status |
|-------|----------|--------|
| 1. Target | `next_close`, horizon=1 | ✅ PASS |
| 2. Train/Val/Test | Chia theo thời gian, không shuffle | ✅ PASS |
| 3. Data Leakage | Không look-ahead; cross-split rolling là intentional | ✅ PASS |
| 4. Scaling | Không áp dụng (RF tree-based) | ✅ N/A |
| 5. Naive Baseline | `close[t]`, 78 samples, cùng array với RF | ✅ PASS |
| 6. Extrapolation | test range [18.70–22.90] nằm trong train range [15.69–25.37] | ✅ PASS |
| 7. RMSE | Công thức đúng, không NaN, không lệch index | ✅ PASS |

**Khả năng model thua Naive do:**
1. Hyperparameter cố định chưa qua tuning có kiểm soát (`n_estimators=200`, `max_depth=10`)
2. Feature là giá tuyệt đối, không scale — model có thể học kém với regime giá thay đổi
3. Hoặc model thực sự không tốt hơn Naive trên tập test này — chỉ kết luận sau TASK 02
