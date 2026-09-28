# Nhật Ký Agile - Sprint 7 (Tuần 13 - Tuần 14)

> **Ghi chú:** Tái dựng hồi cứu từ lịch sử Git/GitHub ngày 28/09/2026. File này
> không được ghi trong sprint; mọi nội dung dưới đây đều dẫn từ commit, PR và
> issue thực tế, không phải biên bản họp. Số liệu định lượng sinh bằng
> `python reports/src/agile_metrics.py` (xem `reports/agile_metrics.csv`).

*   **Thời gian**: 24/08/2026 - 06/09/2026
*   **Mục tiêu Sprint** *(không có Sprint Goal được ghi lại; tái dựng từ công việc thực tế)*:
    1. Kiểm định phương pháp luận (audit) của 4 mô hình benchmark.
    2. Đưa cải tiến GRU residual vào `develop` đúng quy trình.

---

## 1. Bảng Phân Chia Công Việc (theo commit/PR thực tế)

| Task ID | Người thực hiện (theo Git) | Mô tả công việc | Trạng thái | Ghi chú |
| :--- | :--- | :--- | :--- | :--- |
| #S7-01 | Ennela | Audit phương pháp luận cho ARIMA, XGBoost, Random Forest, GRU (`docs/audit/`). | `[x]` | Commit `b2c2c78` (02/09), PR #42 mở 02/09, merge 07/09 (Sprint 8). |
| #S7-02 | Ennela | Làm lại GRU residual trên `develop`, căn lại hợp đồng scaler (8 đặc trưng). | `[x]` | Commit `e80fd60` (02/09), PR #43 mở 02/09, merge 07/09 (Sprint 8). Thay thế PR #41. |
| #S7-03 | Ennela | Đóng PR #41 (nhánh tạo từ `main`) và ghi lý do. | `[x]` | Đóng không merge ngày 02/09, bình luận "Superseded by #43". |
| #S7-04 | Ennela | Chỉnh `.gitignore` (thư viện Python, snapshot nén). | `[x]` | Commit `8ca2bce` (02/09), đi cùng PR #42/#43. |

**Số liệu sprint:** 3 commit · 1 tác giả · 2 PR mở · 0 PR merge · 1 PR đóng không merge · 0 issue đóng.

---

## 2. Nhật Ký Hoạt Động Theo Ngày

### Ngày 02/09/2026
*   Commit 3 thay đổi: audit 4 mô hình (`b2c2c78`), GRU residual trên `develop`
    (`e80fd60`), `.gitignore` (`8ca2bce`).
*   Mở PR #42 (`docs/model-audits`) và PR #43 (`fix/gru-residual-architecture`).
*   Đóng PR #41 không merge; PR #43 áp dụng lại đúng phần thay đổi GRU (2 tệp)
    trên nền `develop`.

*Không có hoạt động nào trên repo từ 24/08 đến 01/09 và từ 03/09 đến 06/09.*

---

## 3. Retrospective (tái dựng)

*   **Điểm tốt:**
    *   Công việc của một thành viên (PR #41) không bị bỏ đi mà được giữ lại ý tưởng
        và áp dụng lại sạch sẽ, có ghi rõ lý do.
    *   Audit phương pháp luận được viết thành tài liệu trong repo, làm căn cứ cho báo cáo.
*   **Điểm cần cải thiện:**
    *   Toàn bộ commit của sprint thuộc một tài khoản.
    *   Hai PR mở nhưng chưa có người review trong sprint.
*   **Hành động cải tiến:** Chỉ định người review cho mỗi PR ngay khi mở.
