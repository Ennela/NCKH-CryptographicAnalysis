# Nhật Ký Agile - Sprint 5 (Tuần 9 - Tuần 10)

> **Ghi chú:** Tái dựng hồi cứu từ lịch sử Git/GitHub ngày 28/09/2026. File này
> không được ghi trong sprint; mọi nội dung dưới đây đều dẫn từ commit, PR và
> issue thực tế, không phải biên bản họp. Số liệu định lượng sinh bằng
> `python reports/src/agile_metrics.py` (xem `reports/agile_metrics.csv`).

*   **Thời gian**: 27/07/2026 - 09/08/2026
*   **Mục tiêu Sprint** *(không có Sprint Goal được ghi lại; tái dựng từ công việc thực tế)*:
    1. Phác thảo giao diện trang Dự báo (mockup HTML/CSS).

---

## 1. Bảng Phân Chia Công Việc (theo commit/PR thực tế)

| Task ID | Người thực hiện (theo Git) | Mô tả công việc | Trạng thái | Ghi chú |
| :--- | :--- | :--- | :--- | :--- |
| #S5-01 | Hieu | Mockup HTML/CSS trang Dự báo (thanh bộ lọc, khung biểu đồ, thẻ đánh giá mô hình). | `[~]` | Commit `d819fb5`, `e971218` (07/08) trên nhánh `frontend-hieu`; không mở PR, chưa tích hợp vào Next.js. |

**Số liệu sprint:** 2 commit · 1 tác giả · 0 PR mở · 0 PR merge · 0 issue đóng.

---

## 2. Nhật Ký Hoạt Động Theo Ngày

### Ngày 07/08/2026
*   Hieu đẩy 2 commit `update1` lên nhánh `frontend-hieu`: thêm thư mục
    `frontend/HTML & CSS demo/` (mockup tĩnh), `package-lock.json`, sửa
    `tsconfig.json`.

*Không có commit, PR hay issue nào khác trong sprint.*

---

## 3. Retrospective (tái dựng)

*   **Điểm tốt:** Có bản phác thảo giao diện đầu tiên từ thành viên nhóm Frontend.
*   **Điểm cần cải thiện:**
    *   Sprint gần như không có hoạt động trên repo sau đợt bàn giao lớn của Sprint 4
        (57 commit, 22 PR merge). Không có Sprint Goal, backlog hay issue nào được tạo.
    *   Mockup không đi qua PR nên không ai review; commit message không theo
        Conventional Commits (AGENTS.md §8).
*   **Hành động cải tiến:** Mỗi sprint phải có ít nhất một issue/Sprint Goal ghi trên
    GitHub; công việc frontend mở PR vào `develop` để được review sớm.
