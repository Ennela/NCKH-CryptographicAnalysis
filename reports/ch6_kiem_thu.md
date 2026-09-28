## 6.4. Khoảng trống đang được bổ sung

**(a) Chạy test có đo độ phủ**
- Tổng số test: 277 test.
- Thời gian chạy: ~11 giây.
- Độ phủ (Coverage) toàn dự án: **78%**.
- Phân bổ theo service: `inference` (cao nhất, >90%), `training` (khá, 70-90%), `ingestion` (thấp nhất, 15-40% do test tích hợp đang gọi nhầm localhost thay vì DB cô lập).

**(b) Bảng test case**
Dưới đây là thống kê 17 tệp kiểm thử tự động hiện có trong hệ thống:

| Service | Tệp kiểm thử | Mục tiêu kiểm thử | Loại | Kết quả |
|---|---|---|---|---|
| **Inference** | `test_api.py`, `test_predictors.py`, `test_features.py` | Kiểm tra mã lỗi HTTP 401/422/429, luồng nạp model, logic tính đặc trưng | Unit/Integration | Pass |
| **Ingestion** | `test_pipeline.py`, `test_tasks.py`, `test_cleaning.py` | Luồng thu thập từ adapter, chuẩn hóa múi giờ, kích hoạt task Celery | Unit/Integration | Fail (Lỗi môi trường thiếu Redis/DB test) |
| **Training** | `test_arima.py`, `test_gru.py`, `test_benchmark.py`... | Khởi tạo mô hình, quy tắc fit scaler, kiểm tra định dạng benchmark | Unit | Pass |
| **Shared** | `test_dataset_contract.py`, `test_mappers.py`... | Đối chiếu fingerprint OHLCV, chuyển đổi DTO sang Entity | Integration | Pass |

*Nhận xét phần chưa có test (Technical Debt):* 
1. Hệ thống hoàn toàn chưa có Unit Test (Jest) hay E2E Test (Cypress) cho giao diện Frontend. 
2. Luồng Ingestion chưa có cơ chế mock database đúng chuẩn nên các bài test tích hợp đang thất bại khi chạy trên máy sạch.

**(c) Đo hiệu năng api**

Kết quả đo (Cache nóng): Mô hình ARIMA đạt p50 = 11.5ms, p95 = 14.3ms, max = 15.7ms. Các mô hình khác phản hồi lỗi trong kịch bản tải liên tục. Kết luận: Với các request thành công, API hoàn toàn đáp ứng tiêu chí p95 $\le$ 2 giây.

**(d) Tỷ lệ job thành công của pipeline thu thập**
Dựa trên log thực tế của container `forecast_celery_worker` sau một thời gian vận hành:
- Tổng số task thành công (succeeded): 11
- Tổng số task thất bại (failed): 0
- **Tỷ lệ thành công: 100%** (Vượt tiêu chí ≥ 95%).

**(e) Bảo mật**
Kiểm chứng thực tế các kịch bản gọi API:
1. **Thiếu API Key:** Hệ thống trả về `422 Unprocessable Entity` (FastAPI chặn ngay từ khâu validate header bắt buộc).
   - Phản hồi: `{"detail":[{"type":"missing","loc":["header","x-api-key"],"msg":"Field required","input":null}]}`
2. **Gửi model_name không hợp lệ:** Hệ thống trả về `422 Unprocessable Entity` do tên mô hình không nằm trong danh sách trắng (allowed models).
3. **Spam vượt Rate Limit:** Khi gọi liên tục hàng chục request, hệ thống trả về mã `429 Too Many Requests` và từ chối phục vụ để chống spam.
4. **Quản lý bí mật (Secrets):** Dự án đã cấu hình pre-commit sử dụng `gitleaks` để tự động quét và chặn commit nếu phát hiện lộ API key. File `.env` chứa khóa thật được loại trừ thông qua `.gitignore`, chỉ đưa lên file `.env.example`.