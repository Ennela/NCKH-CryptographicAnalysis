# Tài Liệu Hợp Đồng API (Inference Service)

Dịch vụ Inference cung cấp các HTTP API RESTful phục vụ dự báo giá, tra cứu mô
hình, danh sách mã tài sản, dữ liệu OHLCV lịch sử, giải thích mô hình (SHAP) và
các API phân tích dữ liệu (thống kê, chỉ báo kỹ thuật, chất lượng dữ liệu, nhật
ký job).

*   **Phiên bản API**: `v1`
*   **Base URL**: `http://localhost:8000` (các endpoint nghiệp vụ nằm dưới `/api/v1`)
*   **Cập nhật lần cuối**: 28/09/2026 — đối chiếu với `services/inference/main.py`,
    `shared/schemas/predict.py` và `shared/schemas/analytics.py`.

> **Trạng thái triển khai:** mọi endpoint trong tài liệu này chạy thật trên
> PostgreSQL/TimescaleDB và MLflow Registry (không còn mock từ PR #40).
> Mục 8–11 (analytics) được thêm ở nhánh `feature/frontend-redesign`.

---

## 1. Xác thực & Rate limit (chung cho mọi endpoint `/api/v1/*`)

Truyền Header sau trong mọi request:

```http
X-API-Key: your-secure-api-key-here
```

*   Khóa hợp lệ được cấu hình qua biến môi trường `API_KEY_SECRET`
    (`shared/config/settings.py`). Thiếu hoặc sai khóa → `401 Unauthorized`.
*   Rate limit (chỉ áp dụng cho `POST /api/v1/predict` và `GET /api/v1/explain`):
    giới hạn theo cặp (API key, IP) bằng Redis, đếm theo **từng phút cố định**
    (mỗi phút một khóa Redis riêng), ngưỡng cấu hình qua
    `settings.RATE_LIMIT_PER_MINUTE` (mặc định 60 request/phút). Vượt ngưỡng →
    `429 Too Many Requests`; sang phút mới bộ đếm bắt đầu lại. Nếu Redis không
    chạy, rate limit được bỏ qua (thiết kế fail-open).
*   `GET /health` KHÔNG yêu cầu API key (phục vụ Docker/K8s healthcheck).

---

## 2. GET /health — Kiểm tra sức khỏe service

*   **URL**: `/health`
*   **Method**: `GET`
*   **Auth**: Không cần.

### Response (JSON - 200 OK)

```json
{
  "status": "healthy",
  "service": "inference"
}
```

---

## 3. POST /api/v1/predict — Dự báo giá

Lấy dự báo giá cho một mã tài sản trong N bước thời gian tiếp theo.

*   **URL**: `/api/v1/predict`
*   **Method**: `POST`
*   **Headers**:
    *   `Content-Type: application/json`
    *   `X-API-Key: <your_key>`

### Body Request (JSON)

| Trường | Kiểu | Bắt buộc | Mặc định | Mô tả |
| :--- | :--- | :--- | :--- | :--- |
| `ticker_id` | String | Đúng | | Mã định danh tài sản (ví dụ: `ACB`, `FPT`, `BTCUSDT`) |
| `model_name` | String | Đúng | | Một trong: `arima`, `xgboost`, `random_forest`, `gru` |
| `steps` | Integer | Sai | `5` | Số bước dự báo về tương lai, hợp lệ `1..30` |
| `timeframe` | String | Sai | Suy ra từ `asset_class` | `"1d"` hoặc `"1h"`. Nếu bỏ trống: stock → `1d`, crypto → `1h` |

> Ghi chú chuyển tiếp: schema hiện tại (`shared/schemas/predict.py`) còn chấp
> nhận `lstm` (di sản cũ, LSTM đã bị loại khỏi phạm vi đề tài) và chưa nhận
> `random_forest` / `timeframe`. PR backend song song sẽ chốt danh sách model
> đúng bốn mô hình của đề tài như bảng trên.

**Ví dụ Request Body**:

```json
{
  "ticker_id": "ACB",
  "model_name": "xgboost",
  "steps": 3,
  "timeframe": "1d"
}
```

### Response (JSON - 200 OK)

| Trường | Kiểu | Mô tả |
| :--- | :--- | :--- |
| `ticker_id` | String | Mã tài sản |
| `model_name` | String | Tên mô hình thực tế xử lý |
| `prediction_time` | String (ISO 8601) | Thời điểm chạy dự đoán (UTC) |
| `predictions` | Array | Danh sách kết quả dự báo trong tương lai |
| `predictions[].target_time` | String (ISO 8601) | Thời gian đích được dự đoán |
| `predictions[].predicted_value` | Float | Giá trị dự đoán |

**Ví dụ Response Body**:

```json
{
  "ticker_id": "ACB",
  "model_name": "xgboost",
  "prediction_time": "2026-07-26T09:15:00Z",
  "predictions": [
    { "target_time": "2026-07-27T09:15:00Z", "predicted_value": 21.45 },
    { "target_time": "2026-07-28T09:15:00Z", "predicted_value": 21.52 },
    { "target_time": "2026-07-29T09:15:00Z", "predicted_value": 21.48 }
  ]
}
```

### Mã lỗi

| Mã | Ý nghĩa |
| :--- | :--- |
| `401` | Thiếu hoặc sai `X-API-Key` |
| `404` | `ticker_id` không tồn tại trong `market.symbol` |
| `429` | Vượt rate limit |
| `503` | Model chưa có trong MLflow Model Registry (chưa được train/register cho ticker này) |

Kết quả dự báo được cache trong Redis 5 phút theo khóa
`(ticker_id, model_name, steps)`.

---

## 4. GET /api/v1/models — Danh sách mô hình

Lấy danh sách các mô hình đã được đăng ký trên MLflow Model Registry và sẵn
sàng phục vụ, kèm metrics thu được trên tập Test.

*   **URL**: `/api/v1/models`
*   **Method**: `GET`
*   **Headers**: `X-API-Key: <your_key>`

### Response (JSON - 200 OK)

Danh sách đối tượng `{model_name, version, status, metrics, last_updated}`.
`model_name` là tên trong Registry dạng `<TICKER>_<timeframe>_<model>`.
`metrics` là `null` nếu run huấn luyện không ghi đủ MAE/RMSE/MAPE; các trường
`naive_*` (baseline Naive trên cùng tập test) và `directional_accuracy` là
`null` nếu run không ghi.

**Ví dụ Response Body** (minh họa định dạng — số liệu thí nghiệm chính thức xem
`docs/experiment_report.md`):

```json
[
  {
    "model_name": "ACB_1d_gru",
    "version": "2",
    "status": "active",
    "metrics": {
      "mae": 0.2731, "rmse": 0.3874, "mape": 1.3102,
      "naive_mae": 0.2727, "naive_rmse": 0.3902, "naive_mape": 1.3087,
      "directional_accuracy": 0.551
    },
    "last_updated": "2026-09-16T10:12:03Z"
  }
]
```

---

## 5. GET /api/v1/symbols — Danh sách mã tài sản (đã hoạt động)

Lấy toàn bộ mã tài sản `status = 'active'` từ `market.symbol` (join
`market.exchange`), sắp xếp theo `asset_class` rồi `ticker`.

*   **URL**: `/api/v1/symbols`
*   **Method**: `GET`
*   **Headers**: `X-API-Key: <your_key>`

### Response (JSON - 200 OK)

**Ví dụ Response Body**:

```json
[
  {
    "ticker": "BTCUSDT",
    "asset_class": "crypto",
    "exchange_code": "BINANCE",
    "company_name": null
  },
  {
    "ticker": "ACB",
    "asset_class": "stock",
    "exchange_code": "HOSE",
    "company_name": "Ngân hàng TMCP Á Châu"
  }
]
```

---

## 6. GET /api/v1/ohlcv — Dữ liệu OHLCV lịch sử (đã hoạt động)

Truy vấn nến lịch sử từ hypertable `market.ohlcv` cho một mã tài sản.

*   **URL**: `/api/v1/ohlcv`
*   **Method**: `GET`
*   **Headers**: `X-API-Key: <your_key>`

### Query Parameters

| Tham số | Kiểu | Bắt buộc | Mặc định | Mô tả |
| :--- | :--- | :--- | :--- | :--- |
| `ticker` | String | Đúng | | Mã tài sản, ví dụ `FPT`, `BTCUSDT` |
| `timeframe` | String | Sai | `1d` | Một trong: `1m`, `5m`, `15m`, `1h`, `4h`, `1d`, `1w` |
| `limit` | Integer | Sai | `100` | Số nến tối đa, hợp lệ `1..500` |

### Response (JSON - 200 OK)

Danh sách nến, **sắp xếp mới nhất trước** (newest-first); frontend tự đảo
ngược nếu cần vẽ chart theo chiều thời gian tăng dần.

**Ví dụ Response Body**:

```json
[
  {
    "ts": "2026-07-25T00:00:00+00:00",
    "open": 21.30,
    "high": 21.60,
    "low": 21.25,
    "close": 21.45,
    "volume": 1250000.0
  }
]
```

### Mã lỗi

| Mã | Ý nghĩa |
| :--- | :--- |
| `400` | `timeframe` không nằm trong danh sách cho phép |
| `404` | `ticker` không tồn tại hoặc không `active` |

---

## 7. GET /api/v1/explain — Giải thích mô hình

Trả về phần giải thích của model, đọc từ artifact
`explainability/feature_importance.json` mà entrypoint train của từng model ghi
vào run MLflow. Mỗi loại model dùng một phương pháp phù hợp, cho biết qua
trường `method`:

| `model_name` | `method` | Ý nghĩa của `importance` | Trường bổ sung |
| :--- | :--- | :--- | :--- |
| `xgboost`, `random_forest` | `shap_tree_explainer` | Độ quan trọng của cây (gain / impurity) | `mean_abs_shap`: trung bình \|SHAP\| trên tập test |
| `gru` | `permutation_importance` | RMSE tăng thêm (đơn vị giá) khi xáo trộn feature trên tập test | `importance_std`; cấp response: `baseline_rmse`, `n_repeats`, `n_samples` |
| `arima` | `arima_coefficients` | \|hệ số\| của tham số ARIMA (ARIMA chỉ dùng giá đóng cửa nên không có feature để xếp hạng) | `coefficient` (có dấu), `std_error`, `p_value` (có thể `null`); cấp response: `order`, `n_observations` |

Các trường bổ sung đều tùy chọn: artifact cũ chỉ có `importance`/`mean_abs_shap`
vẫn đọc được.

*   **URL**: `/api/v1/explain`
*   **Method**: `GET`
*   **Headers**: `X-API-Key: <your_key>`

### Query Parameters

| Tham số | Kiểu | Bắt buộc | Mặc định | Mô tả |
| :--- | :--- | :--- | :--- | :--- |
| `ticker` | String | Đúng | | Mã tài sản |
| `timeframe` | String | Sai | `1d` | Khung thời gian |
| `model_name` | String | Sai | `xgboost` | `xgboost`, `random_forest`, `gru`, `arima` |

### Response (JSON - 200 OK)

**Ví dụ — XGBoost / Random Forest**:

```json
{
  "ticker": "ACB",
  "timeframe": "1d",
  "model_name": "xgboost",
  "method": "shap_tree_explainer",
  "features": [
    {"feature": "close_lag_1", "importance": 0.31, "mean_abs_shap": 0.145},
    {"feature": "rsi_14", "importance": 0.12, "mean_abs_shap": 0.056}
  ],
  "generated_at": "2026-07-26T09:20:00Z",
  "n_samples": 78
}
```

**Ví dụ — GRU**:

```json
{
  "ticker": "ACB",
  "timeframe": "1d",
  "model_name": "gru",
  "method": "permutation_importance",
  "features": [
    {"feature": "close", "importance": 1.204, "importance_std": 0.083},
    {"feature": "return_1d", "importance": -0.002, "importance_std": 0.004}
  ],
  "baseline_rmse": 0.387,
  "n_repeats": 5,
  "n_samples": 71
}
```

**Ví dụ — ARIMA**:

```json
{
  "ticker": "ACB",
  "timeframe": "1d",
  "model_name": "arima",
  "method": "arima_coefficients",
  "features": [
    {"feature": "ar.L1", "importance": 0.42, "coefficient": -0.42, "std_error": 0.05, "p_value": 0.001},
    {"feature": "ma.L1", "importance": 0.47, "coefficient": 0.47, "std_error": 0.05, "p_value": 0.0004},
    {"feature": "sigma2", "importance": 0.16, "coefficient": 0.16, "std_error": 0.01, "p_value": 0.0}
  ],
  "order": [1, 1, 1],
  "n_observations": 444
}
```

### Mã lỗi

| Mã | Ý nghĩa |
| :--- | :--- |
| `400` | `timeframe` hoặc `model_name` không hợp lệ |
| `404` | Model chưa đăng ký, hoặc run chưa có artifact giải thích (train lại bằng entrypoint tương ứng) |
| `503` | Không kết nối được MLflow |

---

## 8. GET /api/v1/stats — Thống kê mô tả dữ liệu

Thống kê trên toàn bộ dữ liệu đã làm sạch (`market.ohlcv`) của mọi mã có dữ
liệu ở khung thời gian được chọn. Dùng cho bảng thông số ở trang
"Dữ liệu & Phân tích" và "Tổng quan".

*   **Query**: `timeframe` = `1d` (mặc định) | `1h`. Sai giá trị → `400`.
*   **Response**: danh sách `SymbolStats`:
    `ticker, asset_class, timeframe, bars, first_ts, last_ts, lowest_low,
    highest_high, mean_close, std_close, first_close, last_close, change_pct,
    mean_volume, max_volume, return_std_pct, rsi_14, macd, macd_signal`.
    *   `change_pct` = (giá cuối / giá đầu − 1) × 100.
    *   `return_std_pct` = độ lệch chuẩn lợi suất giữa hai nến liên tiếp (%),
        dùng làm thước đo độ biến động.
    *   `rsi_14`, `macd`, `macd_signal`: chỉ báo tại nến gần nhất, tính trên
        cùng lượng lịch sử (310 nến) như biểu đồ `/indicators` mặc định nên hai
        nơi hiển thị cùng giá trị.

## 9. GET /api/v1/indicators — Nến kèm chỉ báo kỹ thuật

*   **Query**: `ticker` (bắt buộc), `timeframe` (`1d`|`1h`), `limit` (20–1000,
    mặc định 250).
*   **Response**: `{ticker, timeframe, points[]}`; mỗi điểm có
    `ts, open, high, low, close, volume, sma_20, sma_50, rsi_14, macd,
    macd_signal, macd_hist` (chỉ báo `null` trong giai đoạn khởi động).
*   Server nạp thêm 60 nến trước cửa sổ để SMA 50 / RSI / MACD đã ổn định ở nến
    đầu tiên. RSI và MACD dùng chung công thức `shared/utils/metrics.py` với
    pipeline huấn luyện. Mọi chỉ báo chỉ nhìn về quá khứ (có test kiểm tra).
*   **Mã lỗi**: `404` mã không tồn tại hoặc không có dữ liệu khung này.

## 10. GET /api/v1/data-quality — Hồ sơ chất lượng dữ liệu

*   **Query**: `timeframe` (`1d`|`1h`).
*   **Response**: danh sách `DataQualityReport`: `bars, expected_bars,
    missing_bars, completeness_pct, zero_volume_bars, invalid_ohlc_bars,
    return_outliers, volume_outliers, last_pipeline_check`.
    *   `expected_bars`: cổ phiếu theo lịch thứ 2–6 (chưa trừ ngày lễ), crypto
        theo lịch liên tục (ngày hoặc giờ).
    *   Outlier theo quy tắc IQR (k = 1,5) giống `services/ingestion/app/cleaning.py`,
        nhưng tính trên lợi suất thay vì mức giá để không gắn cờ cả giai đoạn xu hướng.
    *   `last_pipeline_check`: bản ghi `cleaning_pipeline` mới nhất trong
        `ops.data_quality_check` (`null` nếu dữ liệu nạp từ snapshot).

## 11. GET /api/v1/jobs — Nhật ký tác vụ thu thập/làm sạch

*   **Query**: `limit` (1–100, mặc định 20).
*   **Response**: danh sách `JobLogEntry` từ `ops.job_log` (mới nhất trước):
    `job_type, job_name, status, ticker, timeframe, started_at, finished_at,
    duration_ms, rows_affected, error_message`.
*   `status` thuộc enum `ops.job_status`: `pending | running | success | failed | skipped`.

Các endpoint 8–11 yêu cầu `X-API-Key`, trả `503` nếu cơ sở dữ liệu lỗi.

---

## 12. Mã Lỗi Phổ Biến (tổng hợp)

*   `400 Bad Request`: JSON sai định dạng hoặc tham số ngoài khoảng hợp lệ
    (ví dụ `steps > 30`, `timeframe` không hỗ trợ).
*   `401 Unauthorized`: `X-API-Key` sai. (Thiếu hẳn header → FastAPI trả
    `422` vì header được khai báo bắt buộc.)
*   `404 Not Found`: Ticker không tồn tại, hoặc artifact được yêu cầu chưa có.
*   `429 Too Many Requests`: Vượt quá `RATE_LIMIT_PER_MINUTE` (mặc định 60/phút).
*   `503 Service Unavailable`: Model chưa có trong MLflow Model Registry.
*   `500 Internal Server Error`: Lỗi hệ thống không xác định.
