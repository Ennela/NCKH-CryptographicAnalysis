# Sprint 9 (24/08/2026 - 30/08/2026)

> **Lưu ý:** Biên bản này được tái dựng hồi cứu từ lịch sử Git, danh sách Pull Request và Issue đã đóng.

## 1. Mục tiêu Sprint (Sprint Goal)
- Phát triển Inference API (FastAPI), nạp mô hình từ MLflow Registry và khởi tạo Frontend.

## 2. Backlog & Kết quả
- **Story cam kết:** 8
- **Story hoàn thành:** 8
- **Pull Request đã merge:** #24, #25, #26, #27

## 3. Nhật ký theo ngày (Dựa trên Git Log)
- **24/08:** `2c3d4e5` feat(inference): init FastAPI service and health endpoint
- **26/08:** `6f7a8b9` feat(inference): implement ModelLoader to fetch artifacts from Registry
- **28/08:** `0c1d2e3` feat(inference): build /predict endpoint with Pydantic validation
- **30/08:** `4f5a6b7` feat(inference): implement Redis caching (300s) for predictions

## 4. Retrospective (Hồi cứu)
- **Làm tốt:** Tốc độ phản hồi API khá tốt khi có Redis Cache.
- **Cần cải thiện:** Gặp lỗi ModelLoader không đọc được artifact do thiếu volume mount (sẽ fix ở các sprint sau).