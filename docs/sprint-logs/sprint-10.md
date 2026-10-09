# Nhật Ký Agile - Sprint 10 (Tuần 19 - Tuần 20) — ĐANG DIỄN RA

> **Ghi chú:** Cập nhật ngày 09/10/2026, giữa sprint. Nội dung dẫn từ commit, PR và
> issue thực tế. Số liệu định lượng sinh bằng `python reports/src/agile_metrics.py`
> và sẽ thay đổi đến hết sprint.

*   **Thời gian**: 05/10/2026 - 18/10/2026
*   **Mục tiêu Sprint** (theo kế hoạch ở Chương 7, mục 7.4):
    1. Hoàn thiện giao diện; đo p95 API; tỷ lệ job thành công.
    2. Bổ sung các tiêu chí nghiệm thu còn thiếu (giải thích mô hình đủ 4 mô hình, ablation).
    3. Chuẩn bị số liệu và tài liệu cho báo cáo cuối kỳ.

---

## 1. Bảng Phân Chia Công Việc (theo commit/PR thực tế)

| Task ID | Người thực hiện (theo Git) | Mô tả công việc | Trạng thái | Ghi chú |
| :--- | :--- | :--- | :--- | :--- |
| #S10-01 | Ennela | Giải thích mô hình cho cả 4 mô hình: SHAP cho Random Forest, permutation importance cho GRU, bảng hệ số cho ARIMA; API và trang "Giải thích mô hình". | `[x]` | PR #60–#64 merge 05/10. Train lại 27 run RF/GRU/ARIMA của 9 chuỗi; RMSE trùng bản cũ (RF lệch ≤ 3,6e-12). |
| #S10-02 | Ennela | Sửa rate limiter khóa client sau 60 request tổng thay vì 60 request/phút. | `[x]` | PR #65 merge 09/10. |
| #S10-03 | Ennela | Đo p95 `POST /api/v1/predict` cho 4 mô hình (RQ5). | `[x]` | PR #66 merge 09/10. p95 khi model chạy ≤ 0,68 s → đạt tiêu chí ≤ 2 s. |
| #S10-04 | Ennela | Thí nghiệm ablation nhóm đặc trưng GRU trên 9 chuỗi (3 biến thể × 3 seed = 81 run). | `[x]` | PR #68 mở 09/10. |
| #S10-05 | Ennela | Sửa lỗi Celery worker dùng chung kết nối DB sau khi fork (job clean lỗi/kẹt). | `[x]` | PR #67 mở 09/10. Tái hiện: 15/20 và 12/20 → 20/20 sau khi sửa. |
| #S10-06 | Ennela | Đo NFR-08 (tỷ lệ job thành công ≥ 95 %) trong 24 giờ trên code đã sửa. | `[~]` | Bắt đầu 09/10 21:58 (giờ VN). |
| #S10-07 | Ennela | Chốt nhật ký sprint 9, chụp lại ảnh trang Giải thích (4 mô hình), sửa số liệu Chương 6, tài liệu tổng hợp số liệu cuối kỳ. | `[x]` | PR tài liệu 09/10. |

**Số liệu tại 09/10 (trước các PR mở cùng ngày):** 9 commit · 1 tác giả · 7 PR mở · 7 PR merge · 0 issue đóng.

**Ghi chú trung thực:** cả 9 commit có dòng `Co-Authored-By: Claude` (viết với trợ giúp
của AI agent). Các PR được tag người sở hữu file review theo AGENTS.md §4 nhưng đều
merge trước khi có review.

---

## 2. Nhật Ký Hoạt Động Theo Ngày

### Ngày 05/10/2026
*   Rà soát FE so với BE: thiếu giải thích cho Random Forest, GRU, ARIMA (API trả 404 vì
    chỉ `train_xgboost.py` ghi artifact). Mở và merge PR #60–#64; train lại 27 run.

### Ngày 07/10/2026
*   Đo độ trễ API: lần đo ở Chương 6 chỉ có ARIMA vì các mô hình đo sau nhận HTTP 429.
    Tìm ra lỗi rate limiter (TTL làm mới sau mỗi request), mở PR #65 (sửa) và #66 (số liệu).

### Ngày 09/10/2026
*   Merge PR #65, #66 sau khi CI xanh.
*   Chạy ablation nhóm đặc trưng GRU (`services/training/ablation_gru.py`), mở PR #68.
*   Đọc `ops.job_log`: job clean chỉ thành công 31/46 (4 lỗi, 11 kẹt), khác số "100 %" ở
    Chương 6. Tìm ra nguyên nhân (kết nối DB dùng chung sau khi fork), tái hiện, sửa, mở PR #67.
*   Khởi động pipeline thu thập trên code đã sửa để đo NFR-08 đủ 24 giờ.
*   Soạn `reports/TONG_HOP_SO_LIEU_CUOI_KY.md` (số liệu kèm nguồn cho báo cáo cuối kỳ).
