# Nhật Ký Agile - Sprint 1 (Tuần 1 - Tuần 2)

*   **Thời gian**: 01/06/2026 - 14/06/2026
*   **Mục tiêu Sprint**:
    1. Thiết lập toàn bộ khung mã nguồn dự án (scaffolding).
    2. Chạy docker-compose kết nối thành công Database TimescaleDB, Redis và MLflow.
    3. Hoàn thành việc thu thập dữ liệu thô (raw data crawling) cho BTC/USDT (Binance) và FPT (Vnstock).
    4. Thiết kế các schema database và API contract ban đầu.

---

## 1. Bảng Phân Chia Công Việc (Sprint Backlog)

| Task ID | Thành viên phụ trách | Mô tả công việc | Trạng thái | Ghi chú |
| :--- | :--- | :--- | :--- | :--- |
| #S1-01 | **Dev 1 (Leader)** | Khởi tạo cấu trúc monorepo, Docker Compose, CI/CD Actions, hạ tầng local. | `[x]` | Hoàn thành scaffolding. |
| #S1-02 | **Dev 2** | Triển khai crawler ccxt (Binance) và vnstock trong service `ingestion`. | `[x]` | Hoàn thành: collector Binance/vnstock thêm 08/06 (commit `994f81c`, `aa37acd`), refactor sang MarketRepository 09/06 (`433c3fc`, `9ace78b`). (bổ sung hồi cứu 26/07/2026) |
| #S1-03 | **Dev 2** | Cấu hình Celery beat và tasks để tự động chạy crawler theo chu kỳ. | `[x]` | Hoàn thành: `celery_app.py` có beat_schedule (crontab crypto mỗi giờ, stock theo ngày), `tasks.py` có task ingest thật tại thời điểm merge PR #5 (11/06, commit `1f8fb03`). (bổ sung hồi cứu 26/07/2026) |
| #S1-04 | **Dev 3** | Viết code tính toán đặc trưng (MACD, RSI, Volatility) trong thư viện `shared/utils`. | `[x]` | Hoàn thành: `shared/utils/metrics.py` có `calculate_rsi`, `calculate_macd`, `calculate_volatility`, `calculate_returns` từ trong sprint. (bổ sung hồi cứu 26/07/2026) |
| #S1-05 | **Dev 4** | Xây dựng class Dataloader chuẩn bị dữ liệu đầu vào cho mô hình mạng. | `[x]` | Hoàn thành: class `DataLoader` (`services/training/data_loader.py`) có `engineer_features`, `prepare_train_test_split` và time-series CV split. (bổ sung hồi cứu 26/07/2026) |
| #S1-06 | **Dev 5** | Tạo khung dự án Next.js, cấu hình TypeScript, cài đặt ECharts. | `[x]` | Hoàn thành: `frontend/` có Next.js 14 + TypeScript + `echarts`/`echarts-for-react`, các page dashboard/forecast/symbols/explainability. (bổ sung hồi cứu 26/07/2026) |

---

## 2. Nhật Ký Hằng Ngày (Daily Standup Summary)

### Ngày 03/06/2026
*   **Dev 1**: Hoàn thành cấu trúc boilerplate, tạo Makefile và docker-compose.
*   **Dev 2**: Bắt đầu tìm hiểu thư viện vnstock và ccxt.
*   **Dev 3 & 4**: Nghiên cứu lý thuyết các chỉ số tài chính cần tính toán.
*   **Dev 5**: Cấu hình Next.js App Router.

---

## 3. Retrospective (Đánh giá cuối Sprint)

*(Phần dưới đây được hoàn thiện hồi cứu từ lịch sử Git/GitHub, không phải biên
bản họp trực tiếp — bổ sung hồi cứu 26/07/2026)*

*   **Điểm tốt (What went well)**:
    *   Cơ sở hạ tầng code được setup sẵn, các thành viên clone về là chạy được ngay qua Docker.
    *   Toàn bộ 6 task backlog hoàn thành trong sprint; PR #4 và PR #5
        (`feat/automated-tests-and-ingestion-refactor`) merge vào `develop`
        ngày 10-11/06. (bổ sung hồi cứu 26/07/2026)
    *   Có test suite tự động với DB rollback fixtures ngay từ sprint đầu
        (commit `71b6dcc`, 09/06). (bổ sung hồi cứu 26/07/2026)
    *   Chuẩn hóa hạ tầng DB sớm: SQLAlchemy async engine + Alembic migration,
        lớp MarketRepository dùng chung cho ingestion (commit `5a82565`,
        `d1c90cf`, 09/06). (bổ sung hồi cứu 26/07/2026)
*   **Điểm cần cải thiện (What could be improved)**:
    *   Tốc độ tìm hiểu API vnstock còn hơi chậm do thiếu tài liệu tiếng Anh.
    *   Hai collector Binance/vnstock ban đầu được thêm dưới `api/` như hai
        FastAPI service rời (commit `994f81c`, `aa37acd`, 08/06) rồi mới
        refactor về repository chung — cần thống nhất thiết kế trước khi code
        để tránh refactor lại; việc gộp `api/*` vào `services/ingestion` vẫn
        là ngoại lệ đang mở trong AGENTS.md mục 12.2. (bổ sung hồi cứu
        26/07/2026)
    *   Sprint log không được cập nhật trạng thái task trong sprint, phải tái
        dựng hồi cứu sau gần 7 tuần. (bổ sung hồi cứu 26/07/2026)
*   **Hành động cải tiến (Action items)**:
    *   Dev 1 sẽ tổ chức một buổi coding chung (pair programming) hỗ trợ Dev 2 viết adapter.
    *   Duy trì việc ghi sprint log ngay trong sprint thay vì cuối kỳ. (bổ
        sung hồi cứu 26/07/2026)
