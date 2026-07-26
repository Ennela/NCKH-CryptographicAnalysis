# Nhật Ký Agile - Sprint 2 (Tuần 3 - Tuần 4)

> **Ghi chú:** Tái dựng hồi cứu từ lịch sử Git/GitHub ngày 26/07/2026. File này
> không được ghi trong sprint; mọi nội dung dưới đây đều dẫn từ commit, PR và
> issue thực tế, không phải biên bản họp.

*   **Thời gian**: 15/06/2026 - 28/06/2026
*   **Mục tiêu Sprint** *(tái dựng từ nội dung công việc thực tế)*:
    1. Ổn định nhánh `develop` sau đợt refactor ingestion/test của Sprint 1 và
       đưa các thay đổi đã tích hợp lên `main`.
    2. Dọn dẹp tài liệu repo: viết lại README theo thông tin nhóm, gỡ các file
       cấu hình AI agent không dùng.
    3. Sửa lỗi frontend trang symbols.

---

## 1. Bảng Phân Chia Công Việc (Sprint Backlog — tái dựng)

| Task ID | Người thực hiện (theo Git) | Mô tả công việc | Trạng thái | Ghi chú |
| :--- | :--- | :--- | :--- | :--- |
| #S2-01 | Noah | Tinh gọn README: bỏ hướng dẫn setup/development lỗi thời, chỉnh format và tiêu đề mục. | `[x]` | Commit `bce05e3` (25/06), `37e2255` (27/06). |
| #S2-02 | Ennela | Viết lại README với thông tin nhóm và cấu trúc dự án; gỡ cấu hình AI agent (`copilot-instructions.md`, …). | `[x]` | Commit `4c6fb2b`, `8c74eb8` (27/06); xử lý conflict README tại `7459228`. |
| #S2-03 | Ennela | Sửa lỗi trang symbols trên frontend. | `[x]` | Commit `ef5d273` "fix(FE): fixed symbols errors" (27/06), vào `develop` qua PR #7. |
| #S2-04 | Cả nhóm | Merge tích hợp: PR #6, #8 (`develop` → `main`), PR #7 (`feat/automated-tests-and-ingestion-refactor` → `develop`). | `[x]` | Merge ngày 27/06. |

---

## 2. Nhật Ký Hoạt Động Theo Ngày (tái dựng từ lịch sử commit)

*Không có commit nào trong khoảng 15/06 - 24/06; toàn bộ hoạt động ghi nhận
được dồn vào cuối sprint. Lý do không được ghi lại trong lịch sử, nên không
suy đoán ở đây.*

### Ngày 25/06/2026
*   Noah: gỡ phần hướng dẫn setup/development khỏi README (`bce05e3`).

### Ngày 27/06/2026
*   Merge PR #6 (`develop` → `main`).
*   Ennela: viết lại README với thông tin nhóm & cấu trúc dự án (`4c6fb2b`),
    gỡ `copilot-instructions.md` (`8c74eb8`), sửa lỗi FE trang symbols
    (`ef5d273`).
*   Merge PR #7 (nhánh `feat/automated-tests-and-ingestion-refactor` còn lại
    từ Sprint 1) vào `develop`; giải quyết conflict README (`7459228`).
*   Merge PR #8 (`develop` → `main`); Noah chỉnh format README (`37e2255`).

---

## 3. Retrospective (Đánh giá cuối Sprint — tái dựng)

*(Không có biên bản họp retrospective cho sprint này; các nhận xét dưới đây
rút ra từ lịch sử Git ngày 26/07/2026.)*

*   **Điểm tốt (What went well)**:
    *   Nợ tích hợp của Sprint 1 được đóng: PR #7 merge xong, `main` được đồng
        bộ hai lần (PR #6, #8).
    *   Tài liệu README được đưa về đúng hiện trạng dự án.
*   **Điểm cần cải thiện (What could be improved)**:
    *   Gần 10 ngày đầu sprint không có hoạt động ghi nhận được trên repo;
        khối lượng công việc dồn vào 2 ngày cuối.
    *   Khối lượng chuyển giao của sprint thấp so với Sprint 1 (chủ yếu là
        docs/cleanup, không có tính năng mới).
*   **Hành động cải tiến (Action items)**:
    *   Giữ nhịp commit đều trong sprint thay vì dồn cuối kỳ (thực tế Sprint 3
        và 4 sau đó có nhịp bàn giao tốt hơn).
