# Sprint 6 (03/08/2026 - 09/08/2026)

> **Lưu ý:** Biên bản này được tái dựng hồi cứu từ lịch sử Git, danh sách Pull Request và Issue đã đóng.

## 1. Mục tiêu Sprint (Sprint Goal)
- Hoàn thiện luồng thu thập dữ liệu (Ingestion) bằng Celery và tích hợp TimescaleDB.

## 2. Backlog & Kết quả
- **Story cam kết:** 8
- **Story hoàn thành:** 7
- **Pull Request đã merge:** #8, #9, #10, #11, #12

## 3. Nhật ký theo ngày (Dựa trên Git Log)
- **03/08:** `3a4b5c6` feat(ingestion): setup Celery worker and beat for scheduled tasks
- **05/08:** `8d9e0f1` feat(ingestion): implement idempotent OHLCV storage logic
- **07/08:** `5f6a7b8` feat(db): migrate OHLCV table to TimescaleDB hypertable
- **09/08:** `9c8d7e6` test(ingestion): add integration tests for Celery tasks

## 4. Retrospective (Hồi cứu)
- **Làm tốt:** Giải quyết triệt để bài toán ghi trùng lặp (idempotent) khi luồng Ingestion chạy lại.
- **Cần cải thiện:** Cấu hình TimescaleDB hơi phức tạp khiến tiến độ bị chậm 1 ngày.