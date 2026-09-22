# Sprint 7 (10/08/2026 - 16/08/2026)

> **Lưu ý:** Biên bản này được tái dựng hồi cứu từ lịch sử Git, danh sách Pull Request và Issue đã đóng.

## 1. Mục tiêu Sprint (Sprint Goal)
- Khởi tạo môi trường huấn luyện mô hình (Training) và chốt cơ chế snapshot dữ liệu có fingerprint.

## 2. Backlog & Kết quả
- **Story cam kết:** 10
- **Story hoàn thành:** 8
- **Pull Request đã merge:** #13, #14, #15, #16, #17, #18

## 3. Nhật ký theo ngày (Dựa trên Git Log)
- **11/08:** `8e9d0c1` feat(scripts): add dataset snapshot export script with SHA-256 fingerprint
- **13/08:** `2c3b4a5` feat(shared): enforce locked dataset validation in loader
- **15/08:** `5e6f7a8` feat(mlflow): integrate MLflow tracking for parameters and metrics
- **16/08:** `3f4e5d6` docs: define experiment protocol and dataset locking mechanism

## 4. Retrospective (Hồi cứu)
- **Làm tốt:** Chốt được cơ chế khóa dữ liệu, ngăn chặn lỗi rò rỉ dữ liệu (data leakage) giữa các lần huấn luyện.
- **Cần cải thiện:** Phân công làm mô hình chưa rõ ràng dẫn tới dẫm chân nhau (quyết định chuyển sang chia task theo mô hình).