# Tài Liệu Hợp Đồng API (Inference Service)

Dịch vụ Inference cung cấp các HTTP API RESTful phục vụ dự báo giá và quản lý mô hình.
Tất cả các API yêu cầu xác thực bằng API Key truyền qua Header `X-API-Key`.

*   **Phiên bản API**: `v1`
*   **Base URL**: `http://localhost:8000/api/v1`

---

## 1. Xác thực (Authentication)

Truyền Header sau trong mọi request:
```http
X-API-Key: your-secure-api-key-here
```

---

## 2. API Dự Báo Giá (Predict Price)

Lấy dự báo giá cho một mã tài sản trong N bước thời gian tiếp theo.

*   **URL**: `/predict`
*   **Method**: `POST`
*   **Headers**:
    *   `Content-Type: application/json`
    *   `X-API-Key: <your_key>`

### Body Request (JSON)
| Trường | Kiểu | Bắt buộc | Mặc định | Mô tả |
| :--- | :--- | :--- | :--- | :--- |
| `ticker_id` | String | Đúng | | Mã định danh tài sản (Ví dụ: `FPT`, `BTC/USDT`) |
| `model_name` | String | Đúng | | Tên mô hình cần dự đoán (`arima`, `xgboost`, `lstm`, `gru`) |
| `steps` | Integer | Sai | `5` | Số bước thời gian cần dự báo về tương lai (Khung 1h hoặc 1d tùy loại tài sản) |

**Ví dụ Request Body**:
```json
{
  "ticker_id": "BTC/USDT",
  "model_name": "xgboost",
  "steps": 3
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
  "ticker_id": "BTC/USDT",
  "model_name": "xgboost",
  "prediction_time": "2026-06-03T14:15:00Z",
  "predictions": [
    {
      "target_time": "2026-06-03T15:00:00Z",
      "predicted_value": 68250.45
    },
    {
      "target_time": "2026-06-03T16:00:00Z",
      "predicted_value": 68310.20
    },
    {
      "target_time": "2026-06-03T17:00:00Z",
      "predicted_value": 68190.85
    }
  ]
}
```

---

## 3. API Danh Sách Mô Hình Hoạt Động (Get Models)

Lấy danh sách các mô hình đã được đăng ký trên MLflow Model Registry và sẵn sàng phục vụ.

*   **URL**: `/models`
*   **Method**: `GET`
*   **Headers**:
    *   `X-API-Key: <your_key>`

### Response (JSON - 200 OK)
Trả về danh sách đối tượng mô hình kèm theo thông tin phiên bản và độ đo chất lượng thu được trên tập Test.

**Ví dụ Response Body**:
```json
[
  {
    "model_name": "arima",
    "version": "1",
    "status": "active",
    "metrics": {
      "mae": 150.25,
      "rmse": 180.40,
      "mape": 0.024
    },
    "last_updated": "2026-06-01T08:30:00Z"
  },
  {
    "model_name": "xgboost",
    "version": "3",
    "status": "active",
    "metrics": {
      "mae": 98.12,
      "rmse": 120.34,
      "mape": 0.015
    },
    "last_updated": "2026-06-02T12:00:00Z"
  },
  {
    "model_name": "lstm",
    "version": "2",
    "status": "staging",
    "metrics": {
      "mae": 85.50,
      "rmse": 105.10,
      "mape": 0.012
    },
    "last_updated": "2026-06-03T01:45:00Z"
  }
]
```

---

## 4. Mã Lỗi Phổ Biến (Error Codes)

*   `400 Bad Request`: Định dạng JSON bị sai hoặc giá trị tham số ngoài khoảng hợp lệ.
*   `401 Unauthorized`: Không truyền `X-API-Key` hoặc khóa không chính xác.
*   `429 Too Many Requests`: Vượt quá số lượng request cho phép mỗi phút (Rate limit).
*   `500 Internal Server Error`: Lỗi hệ thống hoặc mô hình không thể tải từ MLflow.
