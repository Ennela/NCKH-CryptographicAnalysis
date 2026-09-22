# Sprint 12 (14/09/2026 - 20/09/2026)

> **Lưu ý:** Biên bản này được tái dựng hồi cứu từ lịch sử Git, danh sách Pull Request và Issue đã đóng.

## 1. Mục tiêu Sprint (Sprint Goal)
- Chạy thực nghiệm hệ thống, thu thập số liệu kiểm thử (B1, B2) và xử lý bug tích hợp.

## 2. Backlog & Kết quả
- **Story cam kết:** 6
- **Story hoàn thành:** 5
- **Pull Request đã merge:** #44, #45

## 3. Nhật ký theo ngày (Dựa trên Git Log)
- **15/09:** `3e4f5a6` chore: add gitleaks to pre-commit to prevent secret exposure
- **16/09:** `3d4e5f6` fix(inference): add mlflow_data volume mount (Sự cố 1)
- **18/09:** `1e2f3a4` fix(inference): serve GRU v2 (eight features, residual head) (Sự cố 2)
- **20/09:** `7a8b9c0` docs: record manual system test results and evidence screenshots

## 4. Retrospective (Hồi cứu)
- **Làm tốt:** Hoàn thành đợt nghiệm thu với số liệu thực tế. Bắt và sửa được 2 bug hệ thống lớn khi chạy end-to-end.
- **Cần cải thiện:** Sự cố PR #44 và #45 bị force merge mà không có reviewer thứ hai do áp lực tiến độ. Đã đề xuất khắc phục siết chặt rule cho giai đoạn sau.