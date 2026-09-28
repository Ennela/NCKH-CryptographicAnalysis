# Nhật Ký Agile - Sprint 9 (Tuần 17 - Tuần 18) — ĐANG DIỄN RA

> **Ghi chú:** Cập nhật ngày 28/09/2026, giữa sprint. Nội dung dẫn từ commit, PR
> và issue thực tế. Số liệu định lượng sinh bằng
> `python reports/src/agile_metrics.py` và sẽ thay đổi đến hết sprint.

*   **Thời gian**: 21/09/2026 - 04/10/2026
*   **Mục tiêu Sprint**:
    1. Báo cáo tiến độ V2 theo hướng phát triển hệ thống (phân tích – thiết kế, hình ảnh, mã nguồn).
    2. Bộ ảnh minh chứng, chương Kiểm thử, chương Quy trình.
    3. Bổ sung phần mềm theo yêu cầu giảng viên: thu thập – làm sạch dữ liệu, bảng thống kê,
       dashboard phân tích, trang quản trị.

---

## 1. Bảng Phân Chia Công Việc (theo commit/PR thực tế)

| Task ID | Người thực hiện (theo Git) | Mô tả công việc | Trạng thái | Ghi chú |
| :--- | :--- | :--- | :--- | :--- |
| #S9-01 | Ennela | Báo cáo V2 (35 trang) + 7 sơ đồ + mã sinh báo cáo. | `[x]` | Commit `86c90ef` (22/09), PR #46 merge 28/09. |
| #S9-02 | nguyendaj36 | 16 ảnh minh chứng + `reports/ch6_kiem_thu.md`. | `[x]` | PR #47 mở 22/09, merge 28/09 (sau khi đổi đích `main` → `develop`, giữ 4 ảnh trùng tên theo bản V2). |
| #S9-03 | nguyendaj36 | Sprint log 5–12, `agile_metrics.csv`, `reports/ch7_agile.md`. | `[x]` | PR #48 mở 22/09. Bản đầu có mã commit, ngày PR và số liệu story không khớp lịch sử Git, và ghi sprint 10–12 như đã xong; được viết lại từ dữ liệu thật ngày 28/09 trước khi merge. |
| #S9-04 | nguyendaj36 | Trang quản trị + `GET /api/v1/jobs`. | `[ ]` | PR #49 mở 22/09: truy vấn sai tên cột `ops.job_log`, CI lint đỏ. Đóng; làm lại trong nhánh `feature/frontend-redesign`. |
| #S9-05 | Ennela | Làm lại giao diện theo thiết kế của Hieu; thêm trang phân tích dữ liệu, thu thập & làm sạch; API thống kê/chỉ báo/chất lượng dữ liệu. | `[~]` | Nhánh `feature/frontend-redesign`, bắt đầu 28/09. |

**Số liệu tại 28/09:** 8 commit · 3 tác giả · 4 PR mở · 2 PR merge (#46, #47) · 0 issue đóng.

---

## 2. Nhật Ký Hoạt Động Theo Ngày

### Ngày 22/09/2026
*   Commit báo cáo V2 và mã sinh báo cáo (`86c90ef`), mở PR #46.
*   nguyendaj36 mở PR #47, #48, #49. Cả ba được tạo với nhánh đích `main`
    (lặp lại lỗi của PR #41).

### Ngày 28/09/2026
*   Đổi nhánh đích PR #47–#49 sang `develop`.
*   Merge PR #46, #47. Viết lại nội dung PR #48 từ lịch sử Git/GitHub. Đóng PR #49.
*   Giảng viên yêu cầu bổ sung: cách thu thập dữ liệu, cách tổ chức – làm sạch – chuẩn hóa,
    bảng thông số dữ liệu, dashboard phân tích biến động → mở nhánh
    `feature/frontend-redesign`.
