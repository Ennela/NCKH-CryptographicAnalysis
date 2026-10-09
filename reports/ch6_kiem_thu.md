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
| **Ingestion** | `test_pipeline.py`, `test_tasks.py`, `test_cleaning.py`, `test_celery_app.py`... | Luồng thu thập từ adapter, chuẩn hóa múi giờ, kích hoạt task Celery, kết nối DB sau khi fork | Unit/Integration | Pass trên CI (có TimescaleDB); fail nếu chạy trên máy không có DB test |
| **Training** | `test_arima.py`, `test_gru.py`, `test_benchmark.py`... | Khởi tạo mô hình, quy tắc fit scaler, kiểm tra định dạng benchmark | Unit | Pass |
| **Shared** | `test_dataset_contract.py`, `test_mappers.py`... | Đối chiếu fingerprint OHLCV, chuyển đổi DTO sang Entity | Integration | Pass |

*Nhận xét phần chưa có test (Technical Debt):* 
1. Hệ thống hoàn toàn chưa có Unit Test (Jest) hay E2E Test (Cypress) cho giao diện Frontend. 
2. Luồng Ingestion chưa có cơ chế mock database đúng chuẩn nên các bài test tích hợp đang thất bại khi chạy trên máy sạch.

**(c) Đo hiệu năng api**

Đo lại ngày 07/10/2026 bằng `reports/src/measure_latency.py` (`POST /api/v1/predict`, ACB 1d, 5 bước; chi tiết và số liệu thô: `reports/validations/api_latency_2026-10-07.md`). Cả 164/164 request trả HTTP 200.

| Mô hình | Lần gọi đầu (tải model) | Model chạy thật — p95 | Trúng cache — p95 |
|---|---:|---:|---:|
| ARIMA | 4,66 s | 559 ms | 40 ms |
| XGBoost | 1,23 s | 555 ms | 27 ms |
| Random Forest | 0,84 s | 681 ms | 38 ms |
| GRU | 4,10 s | 293 ms | 39 ms |

Kết luận: API **đạt** tiêu chí p95 ≤ 2 giây với cả bốn mô hình ở trạng thái vận hành. Ngoại lệ là request đầu tiên sau khi khởi động service (ARIMA, GRU mất hơn 4 giây để tải model từ MLflow), chỉ xảy ra một lần.

Lần đo trước chỉ có số liệu ARIMA vì các mô hình đo sau đều nhận HTTP 429: rate limiter làm mới TTL sau mọi request nên khóa client sau request thứ 60 tính tổng. Lỗi đã được sửa (PR #65) trước khi đo lại.

**(d) Tỷ lệ job thành công của pipeline thu thập (NFR-08: ≥ 95 % trong ≥ 24 giờ)**

Số liệu đọc trực tiếp từ bảng `ops.job_log` (mỗi job ghi trạng thái vào bảng này), giai đoạn vận hành 16/09 – 05/10/2026 trên stack local:

| Loại job | Thành công | Thất bại | Kẹt ở `running` |
|---|---:|---:|---:|
| ingest (thu thập) | 29 | 0 | 0 |
| clean (làm sạch) | 31 | 4 | 11 |

- Tỷ lệ thành công: **60/75 = 80 %** (ingest 100 %, clean 67 %) → **chưa đạt** tiêu chí ≥ 95 %.
- Nguyên nhân: Celery worker chạy prefork, các tiến trình con dùng chung kết nối Postgres của tiến trình cha nên tác vụ clean chạy đồng thời làm hỏng giao dịch của nhau. Đã tái hiện (20 tác vụ đồng thời: 15/20 và 12/20 thành công) và sửa (20/20 ở cả 2 lần chạy) ở PR #67.
- Đo lại sau khi sửa: pipeline chạy liên tục từ 09/10/2026 21:58 (giờ VN) để đo đủ 24 giờ — **chưa có kết quả** tại thời điểm cập nhật.
- Số liệu cũ ("11 thành công, 0 thất bại, 100 %") lấy từ log container trong một khoảng ngắn, không khớp `ops.job_log` nên đã được thay.

**(e) Bảo mật**
Kiểm chứng thực tế các kịch bản gọi API:
1. **Thiếu API Key:** Hệ thống trả về `422 Unprocessable Entity` (FastAPI chặn ngay từ khâu validate header bắt buộc).
   - Phản hồi: `{"detail":[{"type":"missing","loc":["header","x-api-key"],"msg":"Field required","input":null}]}`
2. **Gửi model_name không hợp lệ:** Hệ thống trả về `422 Unprocessable Entity` do tên mô hình không nằm trong danh sách trắng (allowed models).
3. **Spam vượt Rate Limit:** Khi gọi liên tục hàng chục request, hệ thống trả về mã `429 Too Many Requests` và từ chối phục vụ để chống spam.
4. **Quản lý bí mật (Secrets):** Dự án đã cấu hình pre-commit sử dụng `gitleaks` để tự động quét và chặn commit nếu phát hiện lộ API key. File `.env` chứa khóa thật được loại trừ thông qua `.gitignore`, chỉ đưa lên file `.env.example`.