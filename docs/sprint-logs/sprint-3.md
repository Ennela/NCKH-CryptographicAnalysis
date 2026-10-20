# Nhật Ký Agile - Sprint 3 (Tuần 5 - Tuần 6)

> **Ghi chú:** Tái dựng hồi cứu từ lịch sử Git/GitHub ngày 26/07/2026. File này
> không được ghi trong sprint; mọi nội dung dưới đây đều dẫn từ commit, PR và
> issue thực tế, không phải biên bản họp.

*   **Thời gian**: 29/06/2026 - 12/07/2026
*   **Mục tiêu Sprint** *(tái dựng từ nội dung công việc thực tế)*:
    1. Hoàn thiện pipeline dữ liệu: làm sạch OHLCV, Celery tasks định kỳ,
       script backfill.
    2. Chuẩn hóa pipeline training để so sánh công bằng 4 mô hình
       (ARIMA / XGBoost / Random Forest / GRU).
    3. Khóa dataset contract chính thức của nhóm (`configs/group_dataset.json`)
       kèm snapshot fingerprint.

---

## 1. Bảng Phân Chia Công Việc (Sprint Backlog — tái dựng)

| Task ID | Người thực hiện (theo Git) | Mô tả công việc | Trạng thái | Ghi chú |
| :--- | :--- | :--- | :--- | :--- |
| #S3-01 | Ennela | Pipeline làm sạch OHLCV + Celery tasks + script backfill. | `[x]` | Commit `fffc075` (05/07), lên `main` qua PR #9 (05/07). |
| #S3-02 | Ennela | Chuẩn hóa training pipeline cho bài toán so sánh 4 mô hình. | `[x]` | Commit `78bec2b`, merge qua PR #10 (`68994c0`, 08/07). |
| #S3-03 | Ennela | Khóa dataset contract chính thức: `group_dataset_v1`, snapshot `ohlcv_full_current`, fingerprint `381cd2ee…d6d2`. | `[x]` | Commit `4b660b7`, merge qua PR #11 (09/07). Từ 08/07 áp dụng "Quy tắc bắt buộc" trong `docs/dataset.md`. |
| #S3-04 | Ennela | Chia sẻ MLflow artifacts với container training (fix volume). | `[x]` | Commit `a80b038` (12/07), merge qua PR #12 (`14e01ed`, 13/07 — ngày đầu Sprint 4). |

---

## 2. Nhật Ký Hoạt Động Theo Ngày (tái dựng từ lịch sử commit)

### Ngày 05/07/2026
*   Ennela: thêm pipeline làm sạch OHLCV, Celery tasks và script backfill
    (`fffc075`); merge PR #9 đưa thay đổi lên `main`.

### Ngày 08/07/2026
*   Ennela: chuẩn hóa training pipeline cho so sánh 4 mô hình (`78bec2b`);
    Noah merge PR #10 vào `develop` (`68994c0`).
*   Từ ngày này, quy tắc bắt buộc về dataset contract (train qua contract mặc
    định, `make check-dataset` trước khi train, MLflow run phải gắn
    `dataset_version=group_dataset_v1`) có hiệu lực — xem `docs/dataset.md`.

### Ngày 09/07/2026
*   Ennela: khóa dataset contract chính thức, điền `snapshot_fingerprint`
    (`4b660b7`); Noah merge PR #11 (`97ca590`).

### Ngày 12/07/2026
*   Ennela: sửa chia sẻ MLflow artifacts cho training (`a80b038`); PR #12
    được merge ngày 13/07 (đầu Sprint 4).

---

## 3. Retrospective (Đánh giá cuối Sprint — tái dựng)

*(Không có biên bản họp retrospective cho sprint này; các nhận xét dưới đây
rút ra từ lịch sử Git ngày 26/07/2026.)*

*   **Điểm tốt (What went well)**:
    *   Nền tảng tái lập thí nghiệm được chốt: dataset contract khóa
        fingerprint, quy tắc train chính thức có hiệu lực từ 08/07 — đây là
        tiền đề trực tiếp cho chuỗi benchmark ở Sprint 4.
    *   Pipeline dữ liệu (cleaning + Celery + backfill) hoàn thiện, đóng phần
        việc ingestion còn dang dở từ đầu dự án.
*   **Điểm cần cải thiện (What could be improved)**:
    *   Lịch sử commit trong sprint tập trung ở một tài khoản Git (Ennela,
        Noah review/merge); đóng góp của các thành viên khác không truy vết
        được qua Git trong giai đoạn này.
    *   Không có commit trong khoảng 29/06 - 04/07 (nửa đầu sprint trống).
*   **Hành động cải tiến (Action items)**:
    *   Mỗi thành viên modeling tự commit phần model mình sở hữu theo phân
        công D18 trong AGENTS.md (thực tế Sprint 4 đã triển khai theo hướng
        mỗi model một entrypoint riêng).
