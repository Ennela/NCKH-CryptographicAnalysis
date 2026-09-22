# Sprint 8 (17/08/2026 - 23/08/2026)

> **Lưu ý:** Biên bản này được tái dựng hồi cứu từ lịch sử Git, danh sách Pull Request và Issue đã đóng.

## 1. Mục tiêu Sprint (Sprint Goal)
- Hoàn thiện các mô hình Machine Learning (ARIMA, XGBoost, Random Forest, GRU) và bộ Benchmark Evaluator độc lập.

## 2. Backlog & Kết quả
- **Story cam kết:** 9
- **Story hoàn thành:** 8
- **Pull Request đã merge:** #19, #20, #21, #22, #23

## 3. Nhật ký theo ngày (Dựa trên Git Log)
- **18/08:** `1a2b3c4` feat(training): implement XGBoost regressor and feature engineering
- **20/08:** `9a0b1c2` feat(training): add reproducible GRU training and naive evaluation
- **22/08:** `7a8b9c0` feat(training): develop independent benchmark evaluator script
- **23/08:** `5b6c7d8` test(training): test benchmark all models on ACB 1d

## 4. Retrospective (Hồi cứu)
- **Làm tốt:** Benchmark Evaluator hoạt động hoàn hảo như một cổng kiểm định, bắt được sai lệch metric. Việc chia task theo mô hình phát huy hiệu quả.
- **Cần cải thiện:** Frontend đang thiếu API để làm việc.