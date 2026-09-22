# Nhật Ký Agile - Sprint 4 (Tuần 7 - Tuần 8)

> **Ghi chú:** Tái dựng hồi cứu từ lịch sử Git/GitHub ngày 26/07/2026. File này
> không được ghi trong sprint; mọi nội dung dưới đây đều dẫn từ commit, PR và
> issue thực tế, không phải biên bản họp.

*   **Thời gian**: 13/07/2026 - 26/07/2026
*   **Mục tiêu Sprint** *(tái dựng từ nội dung công việc thực tế)*:
    1. Hoàn thiện 4 pipeline model độc lập trên locked snapshot (XGBoost,
       Random Forest, GRU, ARIMA) theo Issue #16-#19.
    2. Định nghĩa benchmark protocol dùng chung (Issue #15) và chạy benchmark
       chính thức 4 mô hình trên ACB 1d (Issue #20).
    3. Khôi phục CI (test + lint) và ghi nhận bằng chứng validation.

---

## 1. Bảng Phân Chia Công Việc (Sprint Backlog — theo Issue trên GitHub)

| Task ID | Người thực hiện (theo Git) | Mô tả công việc | Trạng thái | Ghi chú |
| :--- | :--- | :--- | :--- | :--- |
| #S4-01 (Issue #15) | Ennela | Định nghĩa benchmark protocol dùng chung (`docs/experiment_protocol.md`). | `[x]` | PR #21 merge 21/07; issue đóng 24/07. |
| #S4-02 | Ennela | Pipeline XGBoost trên locked snapshot: loader, feature engineering causal, naive baseline, Optuna, tests, docs. | `[x]` | Chuỗi commit 13/07 (`8ebcbe1`…`62e1bba`), PR #13/#14 merge 16/07. |
| #S4-03 (Issue #16) | Ennela | Chuẩn hóa output benchmark của XGBoost. | `[x]` | PR #25 merge 22/07; issue đóng 24/07. |
| #S4-04 (Issue #17) | Ennela | Sửa và harden metrics đánh giá Random Forest. | `[x]` | PR #22 (21/07) + PR #26 (22/07); issue đóng 24/07. |
| #S4-05 (Issue #18) | Ennela | Pipeline GRU tái lập được + naive evaluation; harden validation. | `[x]` | PR #23 (22/07) + PR #27 (22/07); issue đóng 24/07. |
| #S4-06 (Issue #19) | Ennela | Căn chỉnh ARIMA rolling forecast với test targets; cô lập pre-test artifact; ghi bằng chứng post-merge. | `[x]` | PR #24 (22/07), #28 (23/07), #30 (23/07); PR #31 đóng không merge; issue đóng 23/07. Evidence: `reports/validations/issue_19_arima_post_merge.md`. |
| #S4-07 | Ennela | Khôi phục CI: test + lint gates, TimescaleDB cho tests, async pytest. | `[x]` | PR #29 merge 23/07 (`33f4ecc`, `872e275`, `ef029b8`). |
| #S4-08 (Issue #20) | Ennela | Benchmark 4 mô hình trên ACB 1d: evaluator có validation, chạy chính thức, ghi kết quả. | `[x]` | PR #32 merge 24/07 (commit `03f8721`); issue đóng 24/07. Evaluator chạy 23/07, cả 4 run `valid`. Báo cáo: `docs/experiment_report.md`. |
| #S4-09 | Ennela | Đưa evidence benchmark vào Git + bổ sung mục threats-to-validity. | `[ ]` | PR #34, #35 mở ngày 26/07, đang chờ review (chưa merge tại thời điểm tái dựng). |

---

## 2. Nhật Ký Hoạt Động Theo Ngày (tái dựng từ lịch sử commit/PR)

### Ngày 13/07/2026
*   Chuỗi 10 commit xây pipeline XGBoost trên locked snapshot: loader snapshot
    (`8ebcbe1`), feature engineering causal (`d039bec`), vòng đời
    validation-aware (`7692b2d`), naive baseline đầy đủ (`98d0bfa`), fail-fast
    MLflow (`3a4b9e3`), entrypoint train tái lập (`a29b195`), tests
    (`9c20c2c`), docs (`62e1bba`). Merge PR #12 (MLflow artifacts).

### Ngày 16/07/2026
*   Merge PR #13 và #14 (`feature/xgboost-pipeline`): căn chỉnh model
    ownership trong docs (`e5cf9b9`), validate dataset trong contract window
    (`98bc118`).

### Ngày 17/07/2026
*   Tạo 6 issue benchmark trên GitHub: #15 (protocol), #16 (XGBoost output),
    #17 (Random Forest metrics), #18 (GRU), #19 (ARIMA), #20 (benchmark ACB 1d).

### Ngày 21/07/2026
*   Merge PR #21 — benchmark protocol (`bcdacec`).
*   Merge PR #22 — sửa metrics Random Forest (`bf78314`).
*   Commit pipeline GRU (`90a96f2`).

### Ngày 22/07/2026
*   Merge PR #23 (GRU pipeline), #24 (ARIMA alignment, `aefb486`),
    #25 (XGBoost benchmark output, `de996d7`), #26 (harden Random Forest
    validation, `0989aee`), #27 (harden GRU validation, `8a0d2dd`).
*   Commit cô lập ARIMA pre-test artifact (`ab1cf9a`).

### Ngày 23/07/2026
*   Merge PR #28 (ARIMA artifact) và PR #29 (khôi phục CI: `33f4ecc`,
    `872e275`, `ef029b8`).
*   Merge PR #30 — ghi bằng chứng ARIMA post-merge
    (`reports/validations/issue_19_arima_post_merge.md`); Issue #19 đóng.
*   Xây evaluator benchmark 4 mô hình (`e826aea`, `e449f0d`), chạy benchmark
    chính thức ACB 1d (evaluator run 14:30 UTC, 4/4 run `valid`), ghi kết quả
    (`362c9c8`, `034d2aa`).

### Ngày 24/07/2026
*   Merge PR #32 vào `develop` (merge commit `03f8721`). Issues #15, #16,
    #17, #18, #20 đóng. PR #31 (final sign-off) đóng không merge.

### Ngày 26/07/2026
*   Merge PR #33 (`develop` → `main`).
*   Mở PR #34 (commit evidence benchmark vào `docs/evidence/ACB_1d/`) và
    PR #35 (mục threats-to-validity cho `docs/experiment_report.md`) — đang
    chờ review.

---

## 3. Retrospective (Đánh giá cuối Sprint — tái dựng)

*(Không có biên bản họp retrospective cho sprint này; các nhận xét dưới đây
rút ra từ lịch sử Git/GitHub ngày 26/07/2026.)*

*   **Điểm tốt (What went well)**:
    *   Sprint có khối lượng chuyển giao lớn nhất dự án: 15 PR merge (#12-#14,
        #21-#30, #32, #33), 6 issue
        đóng, benchmark 4 mô hình ACB 1d hoàn tất với đủ quality gate và
        evidence.
    *   Quy trình issue → branch → PR → review → merge được tuân thủ nhất
        quán (mỗi issue #15-#20 có nhánh và PR riêng).
    *   CI được khôi phục (test + lint + TimescaleDB) ngay trước khi merge
        benchmark, đúng thứ tự ưu tiên.
    *   Kết quả benchmark được ghi trung thực: ARIMA đứng đầu RMSE nhưng chỉ
        hơn Naive 0.52%, ba model còn lại không vượt Naive — báo cáo không
        phóng đại kết quả.
*   **Điểm cần cải thiện (What could be improved)**:
    *   Post-merge re-run của evaluator trên `develop` (tương tự quy trình
        Issue #19) chưa được thực hiện — còn tồn sang sprint kế tiếp.
    *   Giai đoạn B của protocol (BTCUSDT 1h) chưa bắt đầu.
    *   Sprint log và một số tài liệu (`docs/api.md`, `docs/dataset.md`)
        không được cập nhật cùng nhịp với code, phải refresh hồi cứu.
*   **Hành động cải tiến (Action items)**:
    *   Chạy post-merge verification cho benchmark ACB 1d trên `develop`,
        tạo thư mục evidence mới (không ghi đè `docs/evidence/ACB_1d/`).
    *   Lên kế hoạch Giai đoạn B — BTCUSDT 1h theo
        `docs/experiment_protocol.md` mục 9.
    *   Cập nhật docs trong cùng PR với thay đổi hành vi hệ thống (đúng
        Definition of Done mục 9 trong AGENTS.md).
