# Nhật Ký Agile - Sprint 9 (Tuần 17 - Tuần 18)

> **Ghi chú:** Ghi giữa sprint ngày 28/09/2026, chốt lại ngày 09/10/2026 sau khi sprint
> kết thúc. Nội dung dẫn từ commit, PR và issue thực tế. Số liệu định lượng sinh bằng
> `python reports/src/agile_metrics.py` (xem `reports/agile_metrics.csv`).

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
| #S9-04 | nguyendaj36 | Trang quản trị + `GET /api/v1/jobs`. | `[x]` (làm lại) | PR #49 mở 22/09: truy vấn sai tên cột `ops.job_log`, CI lint đỏ → đóng 28/09. `GET /api/v1/jobs` và màn hình "Thu thập & Làm sạch" (nhật ký job) làm lại trong PR #51. |
| #S9-05 | Ennela | Làm lại giao diện theo thiết kế của Hieu (5 màn hình); API `/stats`, `/indicators`, `/data-quality`, `/jobs`. | `[x]` | PR #51 merge 28/09. |
| #S9-06 | Ennela | Ingestion: `vnstock` thành phụ thuộc tùy chọn (PyPI cách ly gói), giờ nến UTC, backfill crypto, lịch thu thập đủ 25 mã, audit làm sạch toàn bộ dữ liệu thô. | `[x]` | PR #50, #52, #55, #56. |
| #S9-07 | Ennela | RSI 14 / MACD trong bảng thống kê; chụp lại ảnh UI; Chương X (dữ liệu). | `[x]` | PR #53, #54, #57, #58, #59. |

**Số liệu cả sprint:** 22 commit · 3 tác giả · 14 PR mở · 13 PR merge · 1 PR đóng không
merge (#49) · 0 issue đóng.

**Ghi chú trung thực:** 15/15 commit của tài khoản Ennela trong sprint này có dòng
`Co-Authored-By: Claude` (viết với trợ giúp của AI agent); 6 commit của daj/nguyendaj36
không có. 13 PR merge không có review của thành viên khác (repo chưa bật branch
protection).

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
*   Merge PR #50 (vnstock tùy chọn, CI xanh lại), #51 (giao diện mới 5 màn hình + 4 API
    phân tích), #52 (sửa lệch giờ nến crypto, backfill), #53 (16 ảnh UI mới).

### Ngày 29/09/2026
*   Merge PR #54 (chụp lại ảnh sau khi dữ liệu tải xong — lần chụp trước dính spinner),
    #55 (lịch thu thập 25 mã), #56 (audit làm sạch), #57 (RSI/MACD), #58 (ảnh), #59 (Chương X).

### 30/09 – 04/10/2026
*   Không có commit hay PR.

---

## 3. Đánh giá cuối sprint

*   Mục tiêu 1–3 đạt: báo cáo V2, ảnh minh chứng, Chương 6–7, giao diện 5 màn hình (tiêu chí
    "≥ 5 màn hình" đạt từ PR #51).
*   Chưa đạt: cổ phiếu VN không thu thập được tự động do `vnstock` bị PyPI cách ly; các
    hành động khắc phục quy trình đề ra ở Chương 7 (branch protection, issue Sprint Goal)
    chưa thực hiện.
