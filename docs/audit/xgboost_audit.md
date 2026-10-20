# XGBoost Pipeline Audit — ACB 1d Benchmark

> **Loại:** Audit pipeline, không sửa code.
> **Ngày:** 2026-08-19 (rev 2 — phản hồi reviewer)
> **Phạm vi:** `train_xgboost.py`, `xgboost_features.py`, `xgboost_model.py`,
> `shared/dataset/loader.py`, `benchmark.py`, `benchmark_contract.py`, `evaluate.py`,
> `shared/utils/metrics.py`.

---

## 1. Đang dự đoán target gì?

| Thuộc tính | Giá trị | Evidence |
|---|---|---|
| Target column | `next_close` | [`train_xgboost.py:41`](file:///D:/sources/repos/NCKH/services/training/train_xgboost.py#L41) `TARGET_COLUMN = "next_close"` |
| Horizon | 1 (bước kế tiếp) | [`train_xgboost.py:42`](file:///D:/sources/repos/NCKH/services/training/train_xgboost.py#L42) `HORIZON = 1` |
| Định nghĩa | $y_{t+1} = \text{Close}_{t+1}$ — giá đóng cửa phiên kế tiếp | [`shared/dataset/loader.py:274`](file:///D:/sources/repos/NCKH/shared/dataset/loader.py#L274) `result["next_close"] = result.groupby("split", sort=False)["close"].shift(-horizon)` |
| Đơn vị | Giá thô (VND), **không scale target** | [`_target_series`](file:///D:/sources/repos/NCKH/services/training/train_xgboost.py#L233-L238) trả `float64` raw price |
| Contract check | Script assert contract phải có `{"mode": "next_close", "horizon": 1}` | [`load_dataset_metadata`](file:///D:/sources/repos/NCKH/services/training/train_xgboost.py#L169-L180) |

> **Kết luận:** Target rõ ràng, tường minh, không ambiguous.

---

## 2. Train / Validation / Test chia như thế nào?

### 2.1 Phương pháp

- **Chia theo thời gian, tuần tự, không shuffle.**
- Split được gán trực tiếp trên full series trước khi feature engineering.

### 2.2 Tỷ lệ

| Split | Ratio | Evidence |
|---|---|---|
| Train | 70% | [`configs/group_dataset.json`](file:///D:/sources/repos/NCKH/configs/group_dataset.json): `"train_ratio": 0.7` |
| Validation | 15% | `"validation_ratio": 0.15` |
| Test | 15% | `"test_ratio": 0.15` |

### 2.3 Cách thực hiện

1. `shared/dataset/loader.py` → [`_add_split_and_target`](file:///D:/sources/repos/NCKH/shared/dataset/loader.py#L242-L275):
   - Dòng 256–257: `train_end = int(len(df) * 0.70)`, `validation_end = int(len(df) * 0.85)`
   - Gán label `"train"` / `"val"` / `"test"` theo index.
2. Feature engineering chạy trên **toàn bộ series liên tục** (tránh cold-start NaN đầu val/test).
3. Sau khi tính feature, dropna → tách ra dict `{"train": ..., "val": ..., "test": ...}`.

### 2.4 Số lượng sample (ACB 1d)

| Total rows | Train | Val | Test (có target) |
|---|---|---|---|
| 523 | ~366 | ~78 | **78** |

Evidence: [`benchmark_contract.py:32`](file:///D:/sources/repos/NCKH/services/training/benchmark_contract.py#L32) `EXPECTED_PREDICTION_ROWS = 78`.

> **Kết luận:** Chia đúng theo thời gian, không shuffle, không data leakage từ split.

---

## 3. Có data leakage không?

### 3.1 Feature → Target leakage

| Kiểm tra | Kết quả | Evidence |
|---|---|---|
| `next_close` có trong `FEATURE_LIST`? | **KHÔNG** | [`FEATURE_LIST`](file:///D:/sources/repos/NCKH/services/training/models/xgboost_features.py#L68-L75) chỉ chứa 19 feature, không có `next_close` |
| Feature có dùng dữ liệu tương lai? | **KHÔNG** | Tất cả feature dùng `shift(period)` với `period ≥ 1`, hoặc backward rolling window |

### 3.2 Chi tiết từng nhóm feature

| Feature | Công thức | Look-ahead? |
|---|---|---|
| `returns` | `close.pct_change()` = $(C_t - C_{t-1}) / C_{t-1}$ | Không |
| `volatility` | `returns.rolling(14).std()` | Không |
| `rsi` | EWM trên `prices.diff()` gain/loss | Không |
| `macd`, `macd_signal` | EWM(12) − EWM(26), signal EWM(9) | Không |
| `close_lag_{1,3,5,10,20}` | `close.shift(period)`, period ≥ 1 | Không |
| `rolling_mean_{5,10,20}` | `close.rolling(w).mean()` | Không |
| `rolling_std_{5,20}` | `close.rolling(w).std()` | Không |
| `rolling_min_10`, `rolling_max_10` | `close.rolling(10).min/max()` | Không |
| `bollinger_band_width_20` | `(upper - lower) / middle` từ rolling | Không |
| `atr_14` | `TrueRange.rolling(14).mean()` dùng `close.shift(1)` | Không |

Evidence: [`xgboost_features.py:138-196`](file:///D:/sources/repos/NCKH/services/training/models/xgboost_features.py#L138-L196)

### 3.3 Cross-split boundary leakage

| Kiểm tra | Kết quả | Evidence |
|---|---|---|
| Target `next_close` có cross boundary? | **KHÔNG** | [`loader.py:274`](file:///D:/sources/repos/NCKH/shared/dataset/loader.py#L274): `shift(-horizon)` TRONG `groupby("split")` → dòng cuối mỗi split là NaN, bị drop |
| Rolling features cross boundary? | Có (nhưng **không phải leakage**) | Feature được tính trên full series liên tục trước split. Đây là practice chuẩn cho time series: train history chảy vào val/test feature, nhưng **không có dữ liệu tương lai chảy ngược**. |

### 3.4 Test data leakage vào Optuna

| Kiểm tra | Kết quả | Evidence |
|---|---|---|
| Optuna có dùng test data? | **KHÔNG** | [`optimize_params`](file:///D:/sources/repos/NCKH/services/training/train_xgboost.py#L303-L324): chỉ truyền `X_train, y_train, X_val, y_val` |
| Final model fit có dùng test? | **KHÔNG** | [`train_final_model`](file:///D:/sources/repos/NCKH/services/training/train_xgboost.py#L327-L340): fit trên train, early stop trên val |

> **Kết luận: KHÔNG phát hiện data leakage.**

---

## 4. Scaling có đúng không?

| Kiểm tra | Kết quả | Evidence |
|---|---|---|
| Scaler fit trên train only? | **CÓ** | [`prepare_scaled_dataset`](file:///D:/sources/repos/NCKH/services/training/train_xgboost.py#L241-L259): dòng 249–250 `scaler = StandardScaler(); scaler.fit(train_features)` |
| Val/Test dùng transform only? | **CÓ** | Dòng 255: `scaler.transform(val_features)`, dòng 257: `scaler.transform(test_features)` |
| Target bị scale? | **KHÔNG** (giá thô) | [`_target_series`](file:///D:/sources/repos/NCKH/services/training/train_xgboost.py#L233-L238) trả raw float64, không qua scaler |
| Scaler được log? | **CÓ** | [`_log_run_artifacts`](file:///D:/sources/repos/NCKH/services/training/train_xgboost.py#L640-L653): `joblib.dump(scaler)` → MLflow artifact |

> **Kết luận: Scaling đúng chuẩn. Fit trên train, transform trên val/test.**

---

## 5. Test set của model có giống test set của Naive không?

### 5.1 XGBoost test set

- Nguồn: `load_full("ACB", "1d")` → `build_xgboost_features(full_frame)` → `splits["test"]`
- Kết quả: 78 samples, cùng `input_ts`, `target_ts`, `current_close`, `actual_close`
- Evidence: [`run_training`](file:///D:/sources/repos/NCKH/services/training/train_xgboost.py#L699-L749)

### 5.2 Naive test set

- Naive prediction tính từ `manifest["current_close"]` (tức `close` tại thời điểm $t$)
- Evidence: [`build_naive_predictions`](file:///D:/sources/repos/NCKH/services/training/train_xgboost.py#L353-L355)
- Evaluation trên `manifest["actual_close"]` (tức `next_close` = $Close_{t+1}$)
- Evidence: [`evaluate_metric_vectors`](file:///D:/sources/repos/NCKH/services/training/train_xgboost.py#L396-L425): dòng 408–410

### 5.3 So sánh trực tiếp

| Thuộc tính | XGBoost | Naive | Giống? |
|---|---|---|---|
| Test rows | 78 | 78 (cùng manifest) | ✅ |
| `actual_close` (y_true) | `manifest["actual_close"]` | `manifest["actual_close"]` | ✅ |
| `current_close` (y_t) | `manifest["current_close"]` | `manifest["current_close"]` | ✅ |
| Test period | Cùng `input_ts` → `target_ts` | Cùng `input_ts` → `target_ts` | ✅ |
| Target | `next_close` (horizon 1) | `current_close` as prediction of `next_close` | ✅ |

### 5.4 Cross-model Naive identity enforcement

- [`_validate_test_alignment`](file:///D:/sources/repos/NCKH/services/training/train_xgboost.py#L656-L664): assert model test targets = manifest targets
- Benchmark [`_validate_naive_identity`](file:///D:/sources/repos/NCKH/services/training/benchmark.py#L1076-L1100): yêu cầu cả 4 model có cùng Naive metrics (tolerance $10^{-12}$)
- Manifest locked bằng SHA-256: `62d82e13...`

> **Kết luận: CÓ — Test set HOÀN TOÀN GIỐNG nhau cho Model và Naive. Enforced bằng cryptographic hash.**

---

## 6. Metric được tính như thế nào?

### 6.1 Công thức

| Metric | Công thức | Code location |
|---|---|---|
| MAE | $\frac{1}{N} \sum \|y_i - \hat{y}_i\|$ | [`_error_metrics`](file:///D:/sources/repos/NCKH/services/training/train_xgboost.py#L358-L369) dòng 366 |
| RMSE | $\sqrt{\frac{1}{N} \sum (y_i - \hat{y}_i)^2}$ | Dòng 367 |
| MAPE % | $\frac{1}{N} \sum \left\|\frac{y_i - \hat{y}_i}{y_i}\right\| \times 100\%$ | Dòng 368 |
| Directional Accuracy | $\frac{1}{N} \sum \mathbb{I}(\text{sign}(\hat{y}_i - C_t) = \text{sign}(y_i - C_t))$ | [`_directional_accuracy`](file:///D:/sources/repos/NCKH/services/training/train_xgboost.py#L372-L380) |
| Naive MAE / RMSE / MAPE | Cùng công thức, $\hat{y}^{\text{naive}} = C_t$ | [`evaluate_metric_vectors`](file:///D:/sources/repos/NCKH/services/training/train_xgboost.py#L396-L425) dòng 408–410 |
| Improvement vs Naive RMSE | $\frac{\text{RMSE}_{\text{naive}} - \text{RMSE}_{\text{model}}}{\text{RMSE}_{\text{naive}}} \times 100\%$ | Dòng 422 |

### 6.2 Sanity checks

- `validate_metric_relationships` ([dòng 383–393](file:///D:/sources/repos/NCKH/services/training/train_xgboost.py#L383-L393)):
  - RMSE ≥ MAE (tolerance $10^{-12}$)
  - $0 \le \text{Directional Accuracy} \le 1$
  - Tất cả metrics phải finite
- Benchmark recompute ([dòng 285–322](file:///D:/sources/repos/NCKH/services/training/benchmark.py#L285-L322)): metric được tính lại độc lập từ CSV predictions, so sánh với self-reported (tolerance $10^{-12}$)

### 6.3 Kết quả benchmark chính thức

| Metric | XGBoost | Naive | Improvement |
|---|---|---|---|
| MAE | 0.48262 | 0.26692 | −80.97% |
| RMSE | 0.64835 | 0.39022 | **−66.15%** |
| MAPE % | 2.2829 | 1.2889 | — |
| DA | 0.4872 | 0.1026 | — (xem caveat §6.4) |

### 6.4 Caveat quan trọng: Directional Accuracy (DA) và sai baseline

> [!WARNING]
> **So sánh "DA XGBoost = 48.72% vs Naive DA = 10.26%" đúng về số nhưng SAI về baseline.**
> Không được dùng con số "gấp 4.7 lần" làm luận điểm trong báo cáo.

**Tại sao Naive DA ≈ 10% không phải baseline hợp lệ cho bài toán hướng đi:**

DA được tính bằng:
$$\text{DA} = \frac{1}{N} \sum \mathbb{I}\big(\text{sign}(\hat{y}_i - C_t) = \text{sign}(y_i - C_t)\big)$$

Với Naive: $\hat{y}^{\text{naive}} = C_t$, nên $\hat{y}^{\text{naive}} - C_t = 0$ luôn → $\text{sign}(0) = 0$.
Naive chỉ "đúng hướng" khi giá đứng yên ($y_{t+1} = C_t$, tức $\text{sign}(y_{t+1} - C_t) = 0$).
Naive DA = 10.26% đơn giản phản ánh **tỷ lệ ngày flat** trong test set, **KHÔNG phải năng lực dự đoán hướng** — vì Naive không đưa ra dự đoán hướng nào cả.

**Baseline đúng cho DA là coin-flip 50%:**

Với $n = 78$, standard error của tỷ lệ quanh 50%:

$$SE = \sqrt{\frac{0.5 \times 0.5}{78}} \approx 0.0566 \approx 5.66\text{ pp}$$

CI 95% cho XGBoost DA = 48.72%:

$$48.72\% \pm 1.96 \times 5.66\% = [37.6\%, 59.8\%]$$

Khoảng tin cậy **bao trùm 50%** → chưa đủ bằng chứng thống kê (two-sided binomial test) rằng model có edge thật về hướng đi.

**Hàm ý cho báo cáo:**

- ✅ Có thể ghi: "XGBoost DA = 48.72% trên 78 samples, chưa khác biệt thống kê so với 50% coin-flip ($p > 0.05$, binomial test)."
- ❌ Không nên ghi: "XGBoost DA cao hơn Naive 4.7 lần."
- Muốn claim model có giá trị dự đoán hướng → cần binomial test, hoặc backtest P&L, hoặc tăng $n$ đáng kể.

> **Kết luận: Metric được tính đúng chuẩn, trên cùng vector, cùng số sample, có sanity check và independent recomputation. Tuy nhiên DA so với Naive là misleading — cần so với 50% và kèm caveat thống kê.**

---

## 7. Có vấn đề gì phát hiện được?

### 7.1 Pipeline integrity → KHÔNG phát hiện lỗi kỹ thuật

Pipeline **đúng về mặt kỹ thuật**:
- ✅ Không data leakage
- ✅ Scaling đúng (fit train only)
- ✅ Không look-ahead trong feature
- ✅ Optuna không dùng test data
- ✅ Naive và model dùng cùng test set
- ✅ Metric tính đúng công thức

### 7.2 Nguyên nhân TIỀM NĂNG khiến model thua Naive (ghi nhận, KHÔNG sửa)

> [!IMPORTANT]
> Những điểm dưới đây là **quan sát nghiên cứu**, không phải bug. Task này chỉ audit,
> không đề xuất hay thực hiện sửa đổi.

#### 7.2.1 XGBoost đang dự đoán giá thô (raw price level)

- **Quan sát:** Target là `next_close` — giá thô ~20–25k VND cho ACB. Naive prediction (= `current_close`) rất gần `next_close` vì giá cổ phiếu thay đổi rất ít giữa hai ngày liên tiếp (daily change ~1%).
- **Hệ quả:** Model phải dự đoán chính xác mức giá tuyệt đối hơn cả việc "giữ nguyên giá hôm nay". Đây là nhiệm vụ cực kỳ khó — Naive Baseline mặc nhiên "đoán gần đúng" giá trị.
- **Evidence:** Naive MAPE = 1.2889% (tức sai lệch trung bình ~1.3% so với giá thật). Naive RMSE = 0.39 VND trên giá ~20k VND.
- **Ghi chú:** Đây KHÔNG phải bug — đây là tính chất của bài toán khi dùng raw price làm target. Persistence baseline có lợi thế cấu trúc cố hữu trên price level vì chuỗi giá tài chính gần random walk.

#### 7.2.2 Bản chất khó ngoại suy (extrapolation) của tree-based models

- **Quan sát:** XGBoost (và Random Forest) là tree-based model — chúng **không có khả năng ngoại suy** ngoài phạm vi giá trị đã thấy trong training data. Nếu test set có giá nằm ngoài khoảng min–max của train, model sẽ trả về giá trị gần nhất nó biết, không phải giá đúng.
- **Evidence:** XGBoost objective = `reg:squarederror` ([dòng 276](file:///D:/sources/repos/NCKH/services/training/train_xgboost.py#L276)), predict bằng `model.predict(X)` ([`xgboost_model.py:70-72`](file:///D:/sources/repos/NCKH/services/training/models/xgboost_model.py#L70-L72)).
- **Cần xác nhận:** So `min/max(close)` giữa train và test để biết extrapolation có xảy ra thật không (xem mục 7.3 #2).
- **Ghi chú:** Đây là hạn chế cố hữu của tree-based method khi dự đoán raw price — không phải bug trong pipeline.

#### 7.2.3 Optuna chỉ chạy 1 trial (mặc định)

- **Quan sát:** `DEFAULT_N_TRIALS = 1` ([dòng 43](file:///D:/sources/repos/NCKH/services/training/train_xgboost.py#L43)). Với 1 trial, Optuna thực chất random pick một bộ hyperparameter, không thực sự tối ưu.
- **Evidence:** Dòng 43 và CLI default `--n-trials 1`.
- **Ghi chú:** Có thể chạy CLI với `--n-trials N` (N > 1) để tối ưu thực sự. Tuy nhiên, **đây không phải lỗi pipeline** — chỉ là default setting chưa tối ưu.

#### 7.2.4 Dataset nhỏ (ACB 1d)

- **Quan sát:** 523 rows → ~366 train, ~78 val, 78 test. Với 19 features, train set khá nhỏ cho tree-based model.
- **Evidence:** [`benchmark_contract.py:32`](file:///D:/sources/repos/NCKH/services/training/benchmark_contract.py#L32): `EXPECTED_PREDICTION_ROWS = 78`
- **Ghi chú:** Kết quả benchmark chỉ valid cho ACB 1d holdout này, không generalize.

#### 7.2.5 Feature engineering khác biệt giữa hai pipeline

- **Quan sát:** `data_loader.py` (cũ) dùng 17 features khác (lag 1,2,3,7 thay vì 1,3,5,10,20; rolling window 7,14 thay vì 5,10,20; có `volume_change` và `return_lag_*`). `xgboost_features.py` (official benchmark) dùng 19 features riêng.
- **Evidence:**
  - [`data_loader.py:22-44`](file:///D:/sources/repos/NCKH/services/training/data_loader.py#L22-L44): `FEATURE_COLUMNS` (17 features)
  - [`xgboost_features.py:27-75`](file:///D:/sources/repos/NCKH/services/training/models/xgboost_features.py#L27-L75): `FEATURE_LIST` (19 features)
- **Ghi chú:** Benchmark CHÍNH THỨC dùng `xgboost_features.py` qua `train_xgboost.py`, không dùng `data_loader.py`. Hai bộ feature khác nhau KHÔNG tạo leakage, nhưng cần lưu ý khi so sánh kết quả giữa hai entrypoint (`train.py` vs `train_xgboost.py`).

### 7.3 Ưu tiên hành động (chờ duyệt nhóm, KHÔNG tự ý thực hiện)

> [!CAUTION]
> Mục #3 (đổi target) là thay đổi cấp `group_dataset` — ảnh hưởng toàn bộ 4 model,
> PHẢI bàn với leader và cả nhóm trước khi thực hiện. Xem mục 7.4.

| # | Việc | Effort | Lý do |
|---|---|---|---|
| 1 | Tăng `--n-trials` Optuna từ 1 lên ≥ 50 | Thấp | Hiện tại chưa tuning thật (1 trial = random pick), nên làm bất kể hướng tiếp theo |
| 2 | So `min/max(close)` train vs test | Rất thấp | Nếu giá test nằm ngoài range train → xác nhận extrapolation (7.2.2) là root cause chính, không chỉ "khả năng" |
| 3 | Cân nhắc đổi target → log-return / % change | Trung bình–cao | Fix chuẩn cho bài toán "khó thắng persistence baseline" trong forecast tài chính — Naive-on-return (dự đoán 0%) là baseline công bằng hơn hẳn raw price |
| 4 | Đưa DA (kèm caveat thống kê §6.4) vào báo cáo song song RMSE/MAPE | Thấp | Tránh để RMSE-vs-Naive là toàn bộ câu chuyện |

**Lưu ý cho #3:** Đổi target sang return KHÔNG đảm bảo model sẽ thắng dễ hơn. Return chứng khoán gần random walk quanh 0, nên kỳ vọng hợp lý là bức tranh RMSE-vs-Naive **công bằng hơn** (Naive mất lợi thế cấu trúc trên raw price), chứ chưa chắc $R^2$ sẽ cao.

### 7.4 Ảnh hưởng ngoài XGBoost

> [!IMPORTANT]
> Các finding dưới đây KHÔNG chỉ riêng XGBoost — cần bàn với nhóm trước khi hành động.

- **Random Forest:** Cũng tree-based, cũng target `next_close` → dính đúng root cause 7.2.1 (raw price) + 7.2.2 (extrapolation). Khả năng cao cùng cơ chế khiến RF thua Naive (improvement = −63.20%).
- **GRU:** Neural network có khả năng ngoại suy hơn tree, nhưng vẫn dự đoán raw price → 7.2.1 vẫn áp dụng. Improvement = −88.63%, kém nhất → có thể do overfitting trên dataset nhỏ.
- **ARIMA:** Duy nhất thắng Naive (+0.52%) vì ARIMA(1,1,1) với differencing ($d = 1$) thực chất đã model hóa return ngầm. Lợi thế nhỏ này nhất quán với giả thuyết rằng target raw price bất lợi cho model không có built-in differencing.
- **Quyết định đổi target** (mục 7.3 #3) nằm ở cấp `configs/group_dataset.json` → thay đổi `target.mode` ảnh hưởng hàm `_add_split_and_target` trong `shared/dataset/loader.py`, tức **tất cả 4 model đều bị ảnh hưởng**. Đây là quyết định nhóm, không phải cá nhân.

---

## 8. Evidence map — File/Function/Line

| Audit item | File | Function / Constant | Lines |
|---|---|---|---|
| Target definition | `train_xgboost.py` | `TARGET_COLUMN`, `HORIZON` | 41–42 |
| Target creation | `shared/dataset/loader.py` | `_add_split_and_target` | 242–275 |
| Contract validation | `train_xgboost.py` | `load_dataset_metadata` | 169–180 |
| Feature engineering | `models/xgboost_features.py` | `build_xgboost_features` | 223–297 |
| Feature list (19 features) | `models/xgboost_features.py` | `FEATURE_LIST` | 68–75 |
| Indicator functions | `shared/utils/metrics.py` | `calculate_returns/rsi/macd/volatility` | 10–48 |
| Audit columns | `models/xgboost_features.py` | `_add_target_audit_columns` | 186–196 |
| Split creation | `shared/dataset/loader.py` | `_add_split_and_target` | 256–265 |
| Scaling | `train_xgboost.py` | `prepare_scaled_dataset` | 241–259 |
| Optuna tuning | `train_xgboost.py` | `optimize_params`, `objective_optuna` | 282–324 |
| Final model training | `train_xgboost.py` | `train_final_model` | 327–340 |
| Naive baseline | `train_xgboost.py` | `build_naive_predictions` | 353–355 |
| Metric computation | `train_xgboost.py` | `_error_metrics`, `_directional_accuracy`, `evaluate_metric_vectors` | 358–425 |
| Metric sanity check | `train_xgboost.py` | `validate_metric_relationships` | 383–393 |
| Test manifest | `train_xgboost.py` | `build_test_manifest` | 445–478 |
| Manifest SHA-256 | `train_xgboost.py` | `calculate_test_manifest_sha256` | 481–508 |
| Test alignment check | `train_xgboost.py` | `_validate_test_alignment` | 656–664 |
| Benchmark recompute | `benchmark.py` | `recompute_metrics` | 285–322 |
| Cross-model Naive check | `benchmark.py` | `_validate_naive_identity` | 1076–1100 |
| Locked test manifest | `benchmark_contract.py` | `build_locked_test_manifest` | 268–304 |
| Expected rows | `benchmark_contract.py` | `EXPECTED_PREDICTION_ROWS` | 32 |
| Model wrapper | `models/xgboost_model.py` | `XGBoostModelWrapper` | 11–89 |
| DA formula | `train_xgboost.py` | `_directional_accuracy` | 372–380 |
| DA (Naive = sign(0)) | `benchmark.py` | `recompute_metrics` | 315–317 |

---

## 9. Tóm tắt (TL;DR)

| Câu hỏi | Trả lời |
|---|---|
| Target là gì? | `next_close` — giá đóng cửa phiên kế tiếp (horizon 1) |
| Split đúng không? | ✅ Time-based 70/15/15, không shuffle |
| Có data leakage? | ✅ Không phát hiện |
| Scaling đúng? | ✅ Fit trên train only |
| Test set model = test set Naive? | ✅ Giống 100%, enforced bằng SHA-256 manifest hash |
| Metric tính đúng? | ✅ MAE/RMSE/MAPE%/DA, cùng công thức, independent recomputation |
| DA so Naive có ý nghĩa? | ⚠️ Không — Naive DA ≈ 10% chỉ đo tỷ lệ ngày flat. Baseline đúng là coin-flip 50%; XGBoost DA 48.72% chưa khác biệt thống kê ($n=78$, CI 95% bao trùm 50%) |
| Vấn đề phát hiện? | Pipeline đúng kỹ thuật. Model thua Naive do bản chất bài toán (raw price → persistence advantage), tree-based extrapolation limit, dataset nhỏ (366 train), tuning chưa thật (1 trial). Đổi target là quyết định nhóm. |
