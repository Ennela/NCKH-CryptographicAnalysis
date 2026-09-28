# Nhật Ký Agile - Sprint 8 (Tuần 15 - Tuần 16)

> **Ghi chú:** Tái dựng hồi cứu từ lịch sử Git/GitHub ngày 28/09/2026. File này
> không được ghi trong sprint; mọi nội dung dưới đây đều dẫn từ commit, PR và
> issue thực tế, không phải biên bản họp. Số liệu định lượng sinh bằng
> `python reports/src/agile_metrics.py` (xem `reports/agile_metrics.csv`).

*   **Thời gian**: 07/09/2026 - 20/09/2026
*   **Mục tiêu Sprint** *(tái dựng từ công việc thực tế)*:
    1. Dựng toàn bộ hệ thống trên máy local và chạy demo end-to-end.
    2. Huấn luyện 4 mô hình trên 9 bộ dữ liệu; sửa lỗi tích hợp phát sinh.
    3. Nộp báo cáo tiến độ lần 1 cho giảng viên.

---

## 1. Bảng Phân Chia Công Việc (theo commit/PR thực tế)

| Task ID | Người thực hiện (theo Git) | Mô tả công việc | Trạng thái | Ghi chú |
| :--- | :--- | :--- | :--- | :--- |
| #S8-01 | Ennela | Merge audit mô hình và GRU residual. | `[x]` | PR #42, #43 merge 07/09. |
| #S8-02 | Ennela | Sửa lỗi inference không đọc được artifact MLflow (thiếu mount volume). | `[x]` | Commit `2257b7a`, PR #44 merge 17/09. |
| #S8-03 | Ennela | Sửa inference phục vụ GRU v2 (8 đặc trưng + residual head). | `[x]` | Commit `526802a`, PR #45 merge 17/09. |
| #S8-04 | Ennela | Huấn luyện 4 mô hình × 9 bộ dữ liệu (36 MLflow run), tổng hợp kết quả. | `[x]` | Bằng chứng: `reports/src/all_results.csv` (36 dòng, commit ở PR #46). Không có commit riêng trong sprint vì artifact nằm trong `artifacts/` (gitignored). |
| #S8-05 | Ennela | Báo cáo tiến độ lần 1 (DOCX) gửi giảng viên. | `[x]` | Tệp `Bao_cao_tien_do_NCKH_2026-09-17.docx` — không commit vào repo. Phản hồi của giảng viên ghi tại `reports/PHAN_CONG_BAO_CAO_V2.md` §0. |

**Số liệu sprint:** 2 commit · 1 tác giả · 2 PR mở · 4 PR merge · 0 issue đóng.

---

## 2. Nhật Ký Hoạt Động Theo Ngày

### Ngày 07/09/2026
*   Merge PR #42 (audit 4 mô hình) và PR #43 (GRU residual) vào `develop`.

### Ngày 16-17/09/2026
*   Dựng 9 container, import snapshot, huấn luyện và chạy benchmark ACB 1d
    (4/4 run `valid`), mở rộng sang FPT/HPG/VCB/VNM 1d, BTC/ETH/SOL 1d, BTC 1h.
*   Hai lỗi tích hợp lộ ra khi chạy thật và được sửa trong ngày:
    PR #44 (mount volume MLflow vào inference) và PR #45 (hợp đồng đặc trưng GRU v2).
    Cả hai merge không có người review thứ hai.

### Ngày 17/09/2026
*   Gửi báo cáo tiến độ lần 1. Giảng viên nhận xét: quá sơ sài, thiếu phân tích –
    thiết kế hệ thống, thiếu hình ảnh và mã nguồn; cần định hướng lại là đề tài
    **phát triển hệ thống tích hợp AI**.

---

## 3. Retrospective (tái dựng)

*   **Điểm tốt:**
    *   Chạy thật end-to-end phát hiện 2 lỗi tích hợp mà test đơn vị không bắt được;
        cả hai được sửa kèm test.
    *   Có kết quả thực nghiệm trên 9 bộ dữ liệu thay vì chỉ ACB.
*   **Điểm cần cải thiện:**
    *   PR #44, #45 merge không review (repo không bật branch protection nên không có
        gì chặn việc này).
    *   Báo cáo lần 1 tập trung vào số liệu mô hình, bỏ qua phần hệ thống phần mềm —
        lệch với yêu cầu của đề tài.
*   **Hành động cải tiến:** Viết lại báo cáo theo hướng phát triển hệ thống (V2);
    chia việc báo cáo cho 2 người (`reports/PHAN_CONG_BAO_CAO_V2.md`).
