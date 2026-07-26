# Tài Liệu Hợp Đồng API (Inference Service)

Dịch vụ Inference cung cấp các HTTP API RESTful phục vụ dự báo giá, tra cứu mô
hình, danh sách mã tài sản, dữ liệu OHLCV lịch sử và giải thích mô hình (SHAP).

*   **Phiên bản API**: `v1`
*   **Base URL**: `http://localhost:8000` (các endpoint nghiệp vụ nằm dưới `/api/v1`)
*   **Cập nhật lần cuối**: 26/07/2026 — đối chiếu với `services/inference/main.py`
    và `shared/schemas/predict.py`.

> **Trạng thái triển khai (quan trọng):** `POST /api/v1/predict` và
> `GET /api/v1/models` trong `services/inference/main.py` hiện vẫn trả kết quả
> **mock** (quỹ đạo giá giả lập, danh sách model cứng) để frontend phát triển
> song song. Một PR backend đang chạy song song ("feat: real model inference")
> sẽ thay phần mock bằng inference thật **theo đúng contract mô tả trong tài
> liệu này** (kèm endpoint mới `GET /api/v1/explain`). Các endpoint
> `/health`, `/api/v1/symbols`, `/api/v1/ohlcv` đã hoạt động thật trên DB.

---

## 1. Xác thực & Rate limit (chung cho mọi endpoint `/api/v1/*`)

Truyền Header sau trong mọi request:

```http
X-API-Key: your-secure-api-key-here
```

*   Khóa hợp lệ được cấu hình qua biến môi trường `API_KEY_SECRET`
    (`shared/config/settings.py`). Thiếu hoặc sai khóa → `401 Unauthorized`.
*   Rate limit: giới hạn theo cặp (API key, IP) bằng Redis, ngưỡng cấu hình qua
    `settings.RATE_LIMIT_PER_MINUTE` (mặc định 60 request/phút). Vượt ngưỡng →
    `429 Too Many Requests`. Nếu Redis không chạy, rate limit được bỏ qua
    (thiết kế fail-open).
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

Danh sách đối tượng `{model_name, version, status, metrics{mae, rmse, mape},
last_updated}`.

**Ví dụ Response Body**:

```json
[
  {
    "model_name": "arima",
    "version": "3",
    "status": "active",
    "metrics": { "mae": 0.2723, "rmse": 0.3882, "mape": 0.0131 },
    "last_updated": "2026-07-23T14:30:15Z"
  },
  {
    "model_name": "xgboost",
    "version": "1",
    "status": "active",
    "metrics": { "mae": 0.4826, "rmse": 0.6484, "mape": 0.0228 },
    "last_updated": "2026-07-23T14:30:15Z"
  }
]
```

> Trạng thái hiện tại: handler đang trả danh sách mock cố định (còn chứa
> `lstm`); việc đọc thật từ MLflow Registry thuộc PR backend song song nêu ở
> đầu tài liệu.

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

## 7. GET /api/v1/explain — Giải thích mô hình bằng SHAP (endpoint mới)

> Endpoint này thuộc PR backend song song ("feat: real model inference");
> contract dưới đây là hợp đồng đã thống nhất để frontend tích hợp trước.

Trả về mức độ quan trọng của từng feature (SHAP TreeExplainer) cho model dạng
cây (hiện áp dụng cho `xgboost`).

*   **URL**: `/api/v1/explain`
*   **Method**: `GET`
*   **Headers**: `X-API-Key: <your_key>`

### Query Parameters

| Tham số | Kiểu | Bắt buộc | Mặc định | Mô tả |
| :--- | :--- | :--- | :--- | :--- |
| `ticker` | String | Đúng | | Mã tài sản |
| `timeframe` | String | Sai | `1d` | Khung thời gian |
| `model_name` | String | Sai | `xgboost` | Model cần giải thích |

### Response (JSON - 200 OK)

**Ví dụ Response Body**:

```json
{
  "ticker": "ACB",
  "timeframe": "1d",
  "model_name": "xgboost",
  "method": "shap_tree_explainer",
  "features": [
    {
      "feature": "close_lag_1",
      "importance": 0.31,
      "mean_abs_shap": 0.145
    },
    {
      "feature": "rsi_14",
      "importance": 0.12,
      "mean_abs_shap": 0.056
    }
  ],
  "generated_at": "2026-07-26T09:20:00Z"
}
```

### Mã lỗi

| Mã | Ý nghĩa |
| :--- | :--- |
| `404` | Model chưa có artifact SHAP (chưa train hoặc chưa sinh giải thích) |

---

## 8. Mã Lỗi Phổ Biến (tổng hợp)

*   `400 Bad Request`: JSON sai định dạng hoặc tham số ngoài khoảng hợp lệ
    (ví dụ `steps > 30`, `timeframe` không hỗ trợ).
*   `401 Unauthorized`: Không truyền `X-API-Key` hoặc khóa không chính xác.
*   `404 Not Found`: Ticker không tồn tại, hoặc artifact được yêu cầu chưa có.
*   `429 Too Many Requests`: Vượt quá `RATE_LIMIT_PER_MINUTE` (mặc định 60/phút).
*   `503 Service Unavailable`: Model chưa có trong MLflow Model Registry.
*   `500 Internal Server Error`: Lỗi hệ thống không xác định.
