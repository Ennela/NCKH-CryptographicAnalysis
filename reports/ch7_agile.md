# Chương 7. Quy trình Agile & Quản lý dự án

Chương này trả lời câu hỏi nghiên cứu RQ4: *"Quy trình Agile và hệ thống CI/CD ảnh hưởng
như thế nào đến khả năng kiểm soát rủi ro trong một dự án có thành phần AI?"*

> **Nguồn số liệu.** Mọi con số trong chương được đếm từ lịch sử Git và GitHub API bằng
> `python reports/src/agile_metrics.py` (kết quả: `reports/agile_metrics.csv`) và các lệnh
> `git`/`gh` ghi kèm từng bảng, chốt ngày 28/09/2026. Nhóm **không dùng board/story
> point**, nên không có số liệu "story cam kết / hoàn thành"; commit, PR và issue được dùng
> làm đại lượng thay thế. Sprint 1–8 là tái dựng hồi cứu (`docs/sprint-logs/`), không phải
> biên bản họp.

## 7.1. Nhịp sprint và khối lượng công việc

Dự án chạy sprint 2 tuần, bắt đầu 01/06/2026. Tại thời điểm viết báo cáo, sprint 9 đang
diễn ra; sprint 10–12 là kế hoạch (mục 7.4).

| Sprint | Thời gian | Commit | Tác giả | PR mở | PR merge | PR đóng không merge | Issue đóng |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | 01/06 – 14/06 | 15 | 3 | 3 | 3 | 0 | 0 |
| 2 | 15/06 – 28/06 | 5 | 2 | 3 | 3 | 0 | 0 |
| 3 | 29/06 – 12/07 | 5 | 2 | 4 | 3 | 0 | 0 |
| 4 | 13/07 – 26/07 | 57 | 3 | 22 | 22 | 1 | 6 |
| 5 | 27/07 – 09/08 | 2 | 1 | 0 | 0 | 0 | 0 |
| 6 | 10/08 – 23/08 | 2 | 2 | 1 | 0 | 0 | 0 |
| 7 | 24/08 – 06/09 | 3 | 1 | 2 | 0 | 1 | 0 |
| 8 | 07/09 – 20/09 | 2 | 1 | 2 | 4 | 0 | 0 |
| 9* | 21/09 – 04/10 | 8 | 3 | 4 | 2 | 0 | 0 |

*\* Sprint 9 chưa kết thúc, số liệu tính đến 28/09.*

**Nhận xét.** Khối lượng công việc trên repo **không đều**: Sprint 4 chiếm 57/99 commit và
22/37 PR merge của cả chín sprint, vì đây là sprint hoàn thiện 4 pipeline mô hình và
benchmark (issue #15–#20). Sprint 5–8 gần như không có hoạt động trên repo (2–3 commit
mỗi sprint). Một phần công việc của giai đoạn này không để lại dấu vết trong Git — ví dụ
36 lần huấn luyện ngày 16–17/09 chỉ lưu trong MLflow và `artifacts/` (bị `.gitignore`);
nhưng việc không có Sprint Goal hay issue nào trong 8 tuần là một khoảng trống quản lý thật.

## 7.2. Những gì quy trình đã làm được

**1. Luồng issue → nhánh → PR → merge ở Sprint 4.** Sáu issue #15–#20 (protocol, XGBoost,
Random Forest, GRU, ARIMA, benchmark) mỗi issue có nhánh và PR riêng, cả sáu đóng trong
7 ngày (17/07 → 24/07). Đây là sprint duy nhất quy trình được áp dụng đầy đủ, và cũng là
sprint có năng suất cao nhất.

**2. Chia việc theo mô hình, không theo tầng.** AGENTS.md §4 giao mỗi người trọn một mô hình
(feature + model + entrypoint + test riêng). Cách chia này giúp các thay đổi mô hình không
đụng nhau: trong lịch sử repo, không có xung đột merge nào giữa các tệp của bốn mô hình.

**3. CI bắt lỗi trước khi merge.** GitHub Actions chạy 4 job (lint & format, Python tests,
Docker Compose dry run, frontend build) trên mọi PR. Ví dụ cụ thể: PR #49 (22/09) bị job
lint báo đỏ (`ruff format --check`), và việc chạy lại hệ thống thật ngày 16–17/09 phát hiện
2 lỗi tích hợp (PR #44, #45) mà test đơn vị không bắt được — cả hai được sửa kèm test hồi quy.

**4. Công việc hỏng được làm lại có lý do, không bị vứt bỏ.** PR #41 (GRU, 23/08) tạo nhánh
từ `main` nên kéo theo 70+ tệp rác; PR #43 áp dụng lại đúng 2 tệp thay đổi trên `develop`
và ghi rõ lý do thay thế.

## 7.3. Các khoảng trống quy trình (trung thực)

**1. Không có review thật.** Lệnh
`gh pr list --state merged --json number,reviews` cho thấy **39 PR đã merge, chỉ 1 PR (#38)
có review**. Tệp `.github/CODEOWNERS` có tồn tại, nhưng **cả `main` và `develop` đều không bật
branch protection** (`gh api repos/<owner>/<repo>/branches/develop/protection` → 404), nên
CODEOWNERS chỉ gợi ý người review chứ không chặn merge. Quy tắc "≥ 1 người review"
(AGENTS.md §8) vì vậy chỉ tồn tại trên giấy. Ngày 28/09, PR #46–#48 cũng được merge
không có review, theo quyết định của chủ repo, để kịp hạn báo cáo.

**2. Đóng góp tập trung vào một tài khoản.** `git log --remotes --no-merges` ghi nhận
103 commit: Ennela 80, nguyendaj36 8, daj 6, Nam 3, Hieu 3, Noah 2, doquangha1306 1.
Một phần nguyên nhân là thành viên gửi tệp cho trưởng nhóm commit hộ; hệ quả là lịch sử
Git không phản ánh đúng phân công ở AGENTS.md §4 và khó truy vết trách nhiệm.

**3. CI đỏ nhiều.** Trong 100 lượt chạy CI gần nhất, các lượt kích hoạt bởi pull request
có 34 lượt thất bại và 23 lượt thành công. CI đóng vai trò cảnh báo, nhưng không có quy tắc
bắt buộc "CI xanh mới được merge" ở cấp repo.

**4. Tạo nhánh sai gốc lặp lại.** PR #41 (23/08) và PR #47, #48, #49 (22/09) đều tạo từ
hoặc nhắm vào `main` thay vì `develop`. Nếu merge nguyên trạng, `main` sẽ nhận toàn bộ
`develop` chưa kiểm duyệt. Lỗi được phát hiện nhờ kích thước diff bất thường
(+7.600 dòng cho vài tệp thay đổi thật).

**5. Nhật ký sprint không được ghi đúng lúc.** Toàn bộ sprint log 1–8 là tái dựng hồi cứu.
Bản tái dựng đầu tiên của sprint 5–12 (PR #48, 22/09) chứa mã commit và số liệu story
không tồn tại trong lịch sử Git, và ghi sprint 10–12 như đã hoàn thành; bản này đã được
viết lại từ dữ liệu thật trước khi merge. Đây là bài học trực tiếp cho RQ4: **khi quy trình
không để lại dấu vết trong lúc làm, việc tái dựng sau đó dễ sai lệch** — kể cả khi dùng
công cụ AI để hỗ trợ.

## 7.4. Trả lời RQ4 và kế hoạch 3 sprint cuối

**Kết luận cho RQ4.** Trong dự án này, phần *tự động* của quy trình (CI chạy trên mọi PR,
hợp đồng dataset có fingerprint, evaluator benchmark có cổng kiểm định) kiểm soát rủi ro
kỹ thuật hiệu quả hơn phần *dựa vào con người* (review, Sprint Goal, nhật ký sprint). Các
rủi ro kỹ thuật lớn nhất (rò rỉ dữ liệu, lệch hợp đồng đặc trưng giữa train và serve) đều bị
chặn hoặc phát hiện bằng máy; còn các lỗi quy trình (merge không review, nhánh sai gốc,
nhật ký sai) chỉ bị phát hiện muộn, khi có người kiểm tra thủ công.

**Kế hoạch sprint 10–12 (05/10 – 15/11/2026)** — chưa diễn ra:

| Sprint | Thời gian | Mục tiêu dự kiến |
|---:|---|---|
| 10 | 05/10 – 18/10 | Hoàn thiện giao diện (trang phân tích dữ liệu, thu thập & làm sạch, quản trị); đo p95 API; tỷ lệ job thành công từ `ops.job_log`. |
| 11 | 19/10 – 01/11 | Hoàn thiện báo cáo cuối kỳ; kiểm thử end-to-end; chuẩn bị demo. |
| 12 | 02/11 – 15/11 | Nghiệm thu, sửa góp ý, merge `develop` → `main`. |

**Hành động khắc phục áp dụng ngay từ sprint 10:**
- Bật branch protection cho `develop` và `main`: bắt buộc CI xanh và ≥ 1 approval.
- Mỗi sprint mở một issue "Sprint Goal" và gắn các PR vào đó, để sprint log được ghi
  trong lúc làm thay vì tái dựng sau.
- Mỗi thành viên tự commit/push từ tài khoản của mình.
- Mọi nhánh tạo bằng `git switch -c <nhanh> origin/develop`; PR mặc định nhắm `develop`.
