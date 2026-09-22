# Sprint 11 (07/09/2026 - 13/09/2026)

> **Lưu ý:** Biên bản này được tái dựng hồi cứu từ lịch sử Git, danh sách Pull Request và Issue đã đóng.

## 1. Mục tiêu Sprint (Sprint Goal)
- Triển khai bảo mật API (API Key, Rate Limit), trang giải thích mô hình SHAP, và luồng CI.

## 2. Backlog & Kết quả
- **Story cam kết:** 8
- **Story hoàn thành:** 7
- **Pull Request đã merge:** #31, #32, #33, #34

## 3. Nhật ký theo ngày (Dựa trên Git Log)
- **07/09:** `3f4a5b6` feat(inference): add X-API-Key middleware and Redis rate limiting
- **09/09:** `1c2d3e4` feat(training): calculate and log SHAP values for tree models
- **11/09:** `5f6a7b8` feat(inference): add /explain endpoint to serve SHAP artifacts
- **13/09:** `7e6d5c4` chore(ci): implement Python Tests and Lint workflows via GitHub Actions

## 4. Retrospective (Hồi cứu)
- **Làm tốt:** Hệ thống bảo mật fail-open bằng Redis hoạt động đúng thiết kế. CI chặn được code lỗi.
- **Cần cải thiện:** Dấu hiệu dồn commit vào một tài khoản đẩy hộ bắt đầu xuất hiện.