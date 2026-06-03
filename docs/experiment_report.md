# Báo Cáo Thí Nghiệm: So Sánh Hiệu Năng Các Mô Hình Machine Learning Cho Bài Toán Dự Báo Giá Tài Sản Tài Chính

> **Nguồn dữ liệu:** VNStock (Cổ phiếu Việt Nam) + Binance (Tiền mã hóa)

---

## 1. Mục Tiêu Thí Nghiệm

Đánh giá và so sánh hiệu năng của các mô hình thuộc các nhóm khác nhau trong Machine Learning nhằm xác định mô hình phù hợp nhất cho bài toán **dự báo giá tài sản tài chính**.

### 1.1 Câu hỏi nghiên cứu

| # | Câu hỏi | Phương pháp trả lời |
|---|---------|---------------------|
| Q1 | Mô hình nào cho độ chính xác dự báo cao nhất? | So sánh 5 metrics (MAE, RMSE, MAPE, R², DA) trên tập test |
| Q2 | Mô hình Deep Learning (LSTM) có outperform mô hình truyền thống (LR, RF, LightGBM)? | So sánh trực tiếp metrics giữa LSTM vs. nhóm Traditional ML |
| Q3 | Feature engineering ảnh hưởng thế nào so với lựa chọn mô hình? | Ablation study: Raw features vs. Engineered features trên cả 4 models |

---

## 2. Thiết Kế Thí Nghiệm

### 2.1 Tổng quan pipeline

```
┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐    ┌────────────────┐    ┌────────────┐
│  Data Source  │───▶│  Preprocessing   │───▶│  Feature Engine  │───▶│    Training     │───▶│ Evaluation │
│  VNStock      │    │  - Missing vals  │    │  - Technical     │    │ - Linear Reg   │    │ - MAE      │
│  Binance      │    │  - Normalization │    │  - Lag features  │    │ - Random Forest│    │ - RMSE     │
└──────────────┘    │  - Train/Test    │    │  - Indicators    │    │ - LightGBM     │    │ - DA       │
                    └──────────────────┘    └──────────────────┘    │ - LSTM         │    └────────────┘
                                                                   └────────────────┘
```

### 2.2 Nguồn dữ liệu

#### VNStock — Cổ phiếu Việt Nam

| Thuộc tính | Chi tiết |
|------------|----------|
| **Thư viện** | `vnstock` (Python) |
| **Mã cổ phiếu** | VN30 blue-chip: VNM, FPT, VIC, HPG, MBB, ... |
| **Khoảng thời gian** | 01/01/2020 – 31/12/2025 (~5 năm) |
| **Tần suất** | Daily (OHLCV) |
| **Trường dữ liệu** | `Open`, `High`, `Low`, `Close`, `Volume`, `Date` |

#### Binance — Tiền mã hóa

| Thuộc tính | Chi tiết |
|------------|----------|
| **Thư viện** | `python-binance` hoặc `ccxt` |
| **Cặp giao dịch** | BTC/USDT, ETH/USDT, BNB/USDT, ... |
| **Khoảng thời gian** | 01/01/2020 – 31/12/2025 |
| **Tần suất** | Daily |
| **Trường dữ liệu** | `Open`, `High`, `Low`, `Close`, `Volume`, `Timestamp` |

### 2.3 Tiền xử lý dữ liệu

| Bước | Phương pháp |
|------|-------------|
| Xử lý missing values | Forward-fill / Interpolation |
| Loại bỏ outliers | IQR hoặc Z-score |
| Chuẩn hóa | MinMaxScaler (cho LSTM), StandardScaler (cho LR, RF, LightGBM) |
| Chia tập dữ liệu | **Time-based split** — Train 70% / Val 15% / Test 15% |
| Sliding window (LSTM) | Window size = 30 hoặc 60 ngày |

> ⚠️ **Quan trọng:** Dữ liệu tài chính là chuỗi thời gian → bắt buộc dùng **time-based split** (không shuffle) để tránh data leakage.

---

## 3. Các Mô Hình Thí Nghiệm

### 3.1 Tổng quan 4 mô hình

```
Mô hình thí nghiệm
├── 1. Linear Regression          ← Baseline
├── 2. Random Forest Regressor    ← Ensemble (Traditional ML)
├── 3. LightGBM Regressor        ← Gradient Boosting (Traditional ML)
└── 4. LSTM                       ← Deep Learning
```

### 3.2 Chi tiết cấu hình

#### Model 1 — Linear Regression (Baseline)

| Thuộc tính | Chi tiết |
|------------|----------|
| **Vai trò** | Đường cơ sở (baseline) để so sánh |
| **Thư viện** | `sklearn.linear_model.LinearRegression` |
| **Hyperparameters** | Mặc định (không tune) |
| **Ưu điểm** | Nhanh, dễ interpret, baseline rõ ràng |
| **Nhược điểm** | Giả định tuyến tính, không capture non-linear patterns |

#### Model 2 — Random Forest Regressor

| Thuộc tính | Chi tiết |
|------------|----------|
| **Vai trò** | Ensemble — đại diện cho tree-based methods |
| **Thư viện** | `sklearn.ensemble.RandomForestRegressor` |
| **Hyperparameters** | `n_estimators` ∈ {100, 300, 500}, `max_depth` ∈ {10, 20, None}, `min_samples_split` ∈ {2, 5} |
| **Tuning** | GridSearchCV hoặc RandomizedSearchCV |
| **Ưu điểm** | Robust với noise, feature importance, ít overfit |
| **Nhược điểm** | Chậm hơn LightGBM, không capture sequence |

#### Model 3 — LightGBM Regressor

| Thuộc tính | Chi tiết |
|------------|----------|
| **Vai trò** | Gradient Boosting — state-of-the-art cho tabular data |
| **Thư viện** | `lightgbm.LGBMRegressor` |
| **Hyperparameters** | `num_leaves` ∈ {31, 63, 127}, `learning_rate` ∈ {0.01, 0.05, 0.1}, `n_estimators` ∈ {100, 500, 1000} |
| **Tuning** | Optuna hoặc GridSearchCV |
| **Ưu điểm** | Nhanh, hiệu quả bộ nhớ, tốt trên tabular data |
| **Nhược điểm** | Dễ overfit nếu tune sai, không native cho time-series |

#### Model 4 — LSTM (Long Short-Term Memory)

| Thuộc tính | Chi tiết |
|------------|----------|
| **Vai trò** | Deep Learning — đại diện cho sequence modeling |
| **Thư viện** | `tensorflow.keras` hoặc `pytorch` |
| **Kiến trúc** | Input → LSTM(64) → Dropout(0.2) → LSTM(32) → Dropout(0.2) → Dense(1) |
| **Hyperparameters** | `units` ∈ {32, 64, 128}, `dropout` ∈ {0.1, 0.2, 0.3}, `sequence_length` ∈ {30, 60} |
| **Training** | Optimizer: Adam (lr=0.001), Loss: MSE, Epochs: 100, Early Stopping (patience=10), Batch: 32 |
| **Ưu điểm** | Capture long-term dependencies, tốt cho sequence data |
| **Nhược điểm** | Cần nhiều data, train chậm, khó interpret |

### 3.3 Tại sao chọn 4 mô hình này?

| Tiêu chí | LR | RF | LightGBM | LSTM |
|----------|----|----|----------|------|
| Đại diện cho | Baseline tuyến tính | Ensemble bagging | Gradient boosting | Deep Learning |
| Độ phức tạp | Thấp | Trung bình | Trung bình–Cao | Cao |
| Non-linear | ✗ | ✓ | ✓ | ✓ |
| Sequence-aware | ✗ | ✗ | ✗ | ✓ |
| Interpretable | ✓✓✓ | ✓✓ | ✓✓ | ✗ |

→ Bốn mô hình tạo thành một **spectrum từ đơn giản → phức tạp**, giúp trả lời câu hỏi: *"Liệu mô hình phức tạp hơn có thực sự tốt hơn?"*

---

## 4. Feature Engineering

### 4.1 Hai bộ features (cho Ablation Study — trả lời Q3)

#### Bộ A — Raw Features

```
[Open, High, Low, Close, Volume]
```

#### Bộ B — Engineered Features

| Nhóm | Features | Mô tả |
|------|----------|-------|
| **Price** | Returns, Log Returns | Tỷ suất sinh lời |
| **Moving Averages** | SMA_7, SMA_14, SMA_30, EMA_12, EMA_26 | Xu hướng giá |
| **Momentum** | RSI_14, MACD, MACD_signal | Động lượng |
| **Volatility** | Bollinger Upper/Lower, ATR_14 | Biến động |
| **Volume** | OBV, Volume_SMA_20 | Khối lượng giao dịch |
| **Lag** | Close_lag_1 → Close_lag_7 | Giá đóng cửa 1–7 ngày trước |

### 4.2 Ablation Matrix

| Model | Feature Set A (Raw) | Feature Set B (Engineered) | Δ Performance |
|-------|--------------------|-----------------------------|---------------|
| Linear Regression | LR_raw | LR_eng | Δ₁ |
| Random Forest | RF_raw | RF_eng | Δ₂ |
| LightGBM | LGBM_raw | LGBM_eng | Δ₃ |
| LSTM | LSTM_raw | LSTM_eng | Δ₄ |

**Phân tích:**
- Nếu Δ trung bình lớn → **Feature engineering quan trọng hơn model selection**
- Nếu Δ nhỏ nhưng variance giữa models lớn → **Model selection quan trọng hơn**

---

## 5. Metrics Đánh Giá

### 5.1 Năm metrics đánh giá

| # | Metric | Công thức | Ý nghĩa | Vai trò |
|---|--------|-----------|----------|--------|
| 1 | **MAE** (Mean Absolute Error) | $\frac{1}{n}\sum\|y_i - \hat{y}_i\|$ | Sai số trung bình tuyệt đối — dễ interpret, đơn vị giống giá gốc | Primary |
| 2 | **RMSE** (Root Mean Squared Error) | $\sqrt{\frac{1}{n}\sum(y_i - \hat{y}_i)^2}$ | Phạt nặng các sai số lớn — nhạy với outliers | Primary |
| 3 | **MAPE** (Mean Absolute Percentage Error) | $\frac{100}{n}\sum\|\frac{y_i - \hat{y}_i}{y_i}\|$ | Sai số phần trăm trung bình — dùng so sánh cross-asset (VNStock vs Binance) | Secondary |
| 4 | **R²** (Coefficient of Determination) | $1 - \frac{SS_{res}}{SS_{tot}}$ | Hệ số xác định — đo mức độ giải thích biến thiên của mô hình | Secondary |
| 5 | **DA** (Directional Accuracy) | $\frac{1}{n}\sum \mathbb{1}(\text{sign}(\Delta y) = \text{sign}(\Delta \hat{y})) \times 100\%$ | Tỷ lệ dự đoán đúng xu hướng tăng/giảm — quan trọng cho trading | Primary |

### 5.2 Tiêu chí chọn model tốt nhất

```
Bước 1: Loại model có DA < 50% (tệ hơn random guess)
Bước 2: Xếp hạng theo RMSE (primary) → MAE (secondary) → DA (tertiary)
Bước 3: Tham khảo thêm MAPE (để so sánh cross-asset) và R² (goodness of fit)
Bước 4: Xét trade-off giữa accuracy và training time
```

### 5.3 Bổ sung

| Metric phụ | Mục đích |
|------------|----------|
| **Training Time** | Đánh giá tính khả thi triển khai |
| **Inference Time** | Tốc độ dự đoán real-time |

---

## 6. Kế Hoạch Thực Hiện

### 6.1 Timeline

| Phase | Công việc | Thời gian |
|-------|-----------|-----------|
| **1** | Thu thập dữ liệu VNStock + Binance | Tuần 1 |
| **2** | EDA & Preprocessing | Tuần 1–2 |
| **3** | Feature Engineering (Bộ A + Bộ B) | Tuần 2 |
| **4** | Train Linear Regression + Random Forest | Tuần 3 |
| **5** | Train LightGBM + Hyperparameter tuning | Tuần 3 |
| **6** | Train LSTM + Hyperparameter tuning | Tuần 3–4 |
| **7** | Evaluation, Ablation Study, So sánh | Tuần 4 |
| **8** | Viết báo cáo & Trực quan hóa kết quả | Tuần 4–5 |

### 6.2 Cấu trúc thư mục

```
NCKH/
├── data/
│   ├── raw/                  # Dữ liệu gốc
│   └── processed/            # Dữ liệu đã xử lý
├── notebooks/
│   ├── 01_data_collection.ipynb
│   ├── 02_eda.ipynb
│   ├── 03_feature_engineering.ipynb
│   ├── 04_model_training.ipynb
│   └── 05_evaluation.ipynb
├── src/
│   ├── data/
│   │   ├── crawlers.py       # VNStock & Binance crawlers
│   │   └── preprocessing.py
│   ├── features/
│   │   └── engineering.py    # Feature engineering pipeline
│   ├── models/
│   │   ├── linear_reg.py
│   │   ├── random_forest.py
│   │   ├── lightgbm_model.py
│   │   └── lstm_model.py
│   └── evaluation/
│       ├── metrics.py        # MAE, RMSE, MAPE, R², DA
│       └── visualization.py
├── models/                   # Saved trained models
├── reports/
│   ├── figures/
│   └── results.csv
├── docs/
│   └── experiment_report.md
├── requirements.txt
└── README.md
```

---

## 7. Kết Quả Kỳ Vọng

### 7.1 Bảng kết quả (sẽ điền sau thí nghiệm)

#### VNStock

| Model | Features | MAE | RMSE | MAPE (%) | R² | DA (%) | Train Time |
|-------|----------|-----|------|----------|-----|--------|------------|
| Linear Regression | Raw | — | — | — | — | — | — |
| Linear Regression | Engineered | — | — | — | — | — | — |
| Random Forest | Raw | — | — | — | — | — | — |
| Random Forest | Engineered | — | — | — | — | — | — |
| LightGBM | Raw | — | — | — | — | — | — |
| LightGBM | Engineered | — | — | — | — | — | — |
| LSTM | Raw | — | — | — | — | — | — |
| LSTM | Engineered | — | — | — | — | — | — |

#### Binance

| Model | Features | MAE | RMSE | MAPE (%) | R² | DA (%) | Train Time |
|-------|----------|-----|------|----------|-----|--------|------------|
| Linear Regression | Raw | — | — | — | — | — | — |
| Linear Regression | Engineered | — | — | — | — | — | — |
| Random Forest | Raw | — | — | — | — | — | — |
| Random Forest | Engineered | — | — | — | — | — | — |
| LightGBM | Raw | — | — | — | — | — | — |
| LightGBM | Engineered | — | — | — | — | — | — |
| LSTM | Raw | — | — | — | — | — | — |
| LSTM | Engineered | — | — | — | — | — | — |

### 7.2 Biểu đồ kỳ vọng

1. **Bar chart**: So sánh MAE / RMSE giữa 4 mô hình
2. **Line chart**: Actual vs. Predicted cho từng model trên tập test
3. **Heatmap**: Ablation matrix — Δ Performance (Raw → Engineered)
4. **Grouped bar chart**: DA (%) so sánh 4 models × 2 datasets

### 7.3 Giả thuyết ban đầu

| Giả thuyết | Dự đoán | Lý do |
|-------------|---------|-------|
| H1 | **LightGBM** sẽ cho RMSE/MAE thấp nhất trên VNStock | Gradient boosting rất mạnh trên tabular data, VNStock ít noise hơn crypto |
| H2 | **LSTM** sẽ competitive trên Binance | Crypto biến động mạnh, LSTM capture được sequential patterns |
| H3 | Feature engineering cải thiện **~15–25%** cho LR và RF, nhưng **<10%** cho LSTM | LSTM tự học features từ raw sequence, tree-based models phụ thuộc features thủ công |
| H4 | **Linear Regression** sẽ thua rõ rệt nhưng vẫn có DA > 50% | Thị trường có xu hướng (trend), LR bắt được trend cơ bản |

---

## 8. Rủi Ro & Biện Pháp

| Rủi ro | Biện pháp |
|--------|-----------|
| Data leakage do split sai | Time-based split, kiểm tra pipeline kỹ |
| LSTM overfitting | Dropout, Early Stopping, monitor val_loss |
| API rate limit | Cache dữ liệu local, retry logic |
| Non-stationarity chuỗi giá | Dùng returns thay vì raw price, differencing |
| LightGBM overfit với nhiều features | Regularization (`reg_alpha`, `reg_lambda`) |

---

## 9. Công Nghệ & Thư Viện

| Mục đích | Thư viện |
|----------|----------|
| Thu thập dữ liệu | `vnstock`, `python-binance` / `ccxt` |
| Xử lý dữ liệu | `pandas`, `numpy` |
| Feature Engineering | `ta` (technical analysis) |
| Linear Regression, Random Forest | `scikit-learn` |
| LightGBM | `lightgbm` |
| LSTM | `tensorflow` / `keras` |
| Visualization | `matplotlib`, `seaborn` |
| Notebook | `jupyter` |

---

## 10. Tài Liệu Tham Khảo

1. Fischer, T., & Krauss, C. (2018). *Deep learning with long short-term memory networks for financial market predictions.* European Journal of Operational Research.
2. Chen, T., & Guestrin, C. (2016). *XGBoost: A Scalable Tree Boosting System.* KDD.
3. Ke, G., et al. (2017). *LightGBM: A Highly Efficient Gradient Boosting Decision Tree.* NeurIPS.
4. Hochreiter, S., & Schmidhuber, J. (1997). *Long Short-Term Memory.* Neural Computation.

---

> **Ghi chú:** Kết quả thực nghiệm sẽ được cập nhật vào mục 7 sau khi hoàn thành training. Model tốt nhất sẽ được chọn dựa trên tiêu chí ở mục 5.2.
