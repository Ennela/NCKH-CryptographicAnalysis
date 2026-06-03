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
| #S1-02 | **Dev 2** | Triển khai crawler ccxt (Binance) và vnstock trong service `ingestion`. | `[ ]` | Đang viết logic crawl. |
| #S1-03 | **Dev 2** | Cấu hình Celery beat và tasks để tự động chạy crawler theo chu kỳ. | `[ ]` | Đang liên kết Redis. |
| #S1-04 | **Dev 3** | Viết code tính toán đặc trưng (MACD, RSI, Volatility) trong thư viện `shared/utils`. | `[ ]` | Đang thảo luận công thức. |
| #S1-05 | **Dev 4** | Xây dựng class Dataloader chuẩn bị dữ liệu đầu vào cho mô hình mạng. | `[ ]` | Cần Time-series split. |
| #S1-06 | **Dev 5** | Tạo khung dự án Next.js, cấu hình TypeScript, cài đặt ECharts. | `[ ]` | Đang code Dashboard. |

---

## 2. Nhật Ký Hằng Ngày (Daily Standup Summary)

### Ngày 03/06/2026
*   **Dev 1**: Hoàn thành cấu trúc boilerplate, tạo Makefile và docker-compose.
*   **Dev 2**: Bắt đầu tìm hiểu thư viện vnstock và ccxt.
*   **Dev 3 & 4**: Nghiên cứu lý thuyết các chỉ số tài chính cần tính toán.
*   **Dev 5**: Cấu hình Next.js App Router.

---

## 3. Retrospective (Đánh giá cuối Sprint)

*(Sẽ điền vào buổi họp kết thúc Sprint 1)*

*   **Điểm tốt (What went well)**:
    *   Cơ sở hạ tầng code được setup sẵn, các thành viên clone về là chạy được ngay qua Docker.
*   **Điểm cần cải thiện (What could be improved)**:
    *   Tốc độ tìm hiểu API vnstock còn hơi chậm do thiếu tài liệu tiếng Anh.
*   **Hành động cải tiến (Action items)**:
    *   Dev 1 sẽ tổ chức một buổi coding chung (pair programming) hỗ trợ Dev 2 viết adapter.
