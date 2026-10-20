# Nhật Ký Agile - Sprint 6 (Tuần 11 - Tuần 12)

> **Ghi chú:** Tái dựng hồi cứu từ lịch sử Git/GitHub ngày 28/09/2026. File này
> không được ghi trong sprint; mọi nội dung dưới đây đều dẫn từ commit, PR và
> issue thực tế, không phải biên bản họp. Số liệu định lượng sinh bằng
> `python reports/src/agile_metrics.py` (xem `reports/agile_metrics.csv`).

*   **Thời gian**: 10/08/2026 - 23/08/2026
*   **Mục tiêu Sprint** *(không có Sprint Goal được ghi lại; tái dựng từ công việc thực tế)*:
    1. Hoàn thiện mockup giao diện.
    2. Cải tiến pipeline GRU.

---

## 1. Bảng Phân Chia Công Việc (theo commit/PR thực tế)

| Task ID | Người thực hiện (theo Git) | Mô tả công việc | Trạng thái | Ghi chú |
| :--- | :--- | :--- | :--- | :--- |
| #S6-01 | Hieu | Cập nhật mockup HTML/CSS. | `[~]` | Commit `6ce2882` (10/08), nhánh `frontend-hieu`, không mở PR. |
| #S6-02 | nguyendaj36 | Cập nhật pipeline GRU (`gru_model.py`, `train_gru.py`) và audit GRU. | `[ ]` | Commit `85fe5fa` (23/08), mở PR #41 cùng ngày. PR bị đóng không merge ở Sprint 7 (xem sprint-7.md). |

**Số liệu sprint:** 2 commit · 2 tác giả · 1 PR mở · 0 PR merge · 0 issue đóng.

---

## 2. Nhật Ký Hoạt Động Theo Ngày

### Ngày 10/08/2026
*   Hieu cập nhật mockup (`6ce2882` — "Update HTML & CSS demo").

### Ngày 23/08/2026
*   nguyendaj36 commit `85fe5fa` "feat(gru): cap nhat toan bo code GRU pipeline moi"
    và mở PR #41 (`feature/gru-pipeline`).
*   Nhánh của PR #41 được tạo từ `main` thay vì `develop`, nên diff kéo theo cả thư
    mục `api/` đã xóa ở PR #36, tệp `2.txt` và tệp nhị phân
    `services/ingestion/celerybeat-schedule` (70+ tệp cho 2 tệp thay đổi thật).

---

## 3. Retrospective (tái dựng)

*   **Điểm tốt:** Thành viên phụ trách GRU chủ động cải tiến mô hình (hướng residual
    sau này được giữ lại ở PR #43).
*   **Điểm cần cải thiện:**
    *   Tạo nhánh sai gốc (`main` thay vì `develop`) và commit kèm tệp rác/tệp sinh ra
        lúc chạy — lỗi này lặp lại ở PR #47–#49 (Sprint 9).
    *   Hoạt động trên repo vẫn rất thấp (2 commit trong 2 tuần).
*   **Hành động cải tiến:** Ghi vào README quy trình tạo nhánh
    `git switch -c feature/<ten> origin/develop`; bổ sung `.gitignore` cho
    `celerybeat-schedule` (đã làm ở PR #44).
