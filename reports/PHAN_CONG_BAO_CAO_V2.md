# Phân công làm lại báo cáo cho thầy — Bản V2

**Ngày giao:** 22/09/2026 · **Hạn tổng:** 29/09/2026 (để còn 1 tuần ráp + duyệt trước mốc S12)
**Repo:** `develop` @ `55ee8f1` (đã merge PR #44, #45)

## 0. Vì sao phải làm lại

Thầy phản hồi bản DOCX trước (`Bao_cao_tien_do_NCKH_2026-09-17.docx`):

1. Quá sơ sài, cần **chi tiết hơn nhiều**.
2. Thiếu **phân tích – thiết kế hệ thống**.
3. Thiếu **hình ảnh minh họa**.
4. Cần có **mã nguồn** minh họa.
5. **Định hướng lại trọng tâm:** đề tài là *phát triển hệ thống phần mềm tích hợp AI*, **không phải** nghiên cứu AI thuần. Nghĩa là: kiến trúc, thiết kế, quy trình, kiểm thử, vận hành, tích hợp mô hình vào sản phẩm mới là phần chính; bảng số liệu MAE/RMSE chỉ là **một chương**, không phải toàn bộ báo cáo.

## 1. Cấu trúc báo cáo V2 và ai làm chương nào

| Ch. | Nội dung | Người làm |
|---|---|---|
| 1 | Mở đầu: bối cảnh, mục tiêu, phạm vi, phương pháp (Agile + ML) | **A** |
| 2 | Phân tích yêu cầu: chức năng / phi chức năng, actor, use case, user story | **A** |
| 3 | Thiết kế hệ thống: kiến trúc dịch vụ, ERD, thiết kế API, luồng dữ liệu, bảo mật | **A** |
| 4 | Triển khai & mã nguồn: trích code từng service, cấu trúc thư mục thực tế | **A** |
| 5 | Tích hợp AI vào hệ thống (MLOps): contract dữ liệu → train → MLflow Registry → serve | **A** |
| 6 | **Kiểm thử & đảm bảo chất lượng**: test, CI/CD, hiệu năng, bảo mật | **B** |
| 7 | **Quy trình Agile & quản lý dự án**: sprint 1–12, velocity, retrospective | **B** |
| 8 | Kết quả thực nghiệm (9 bộ dữ liệu, 36 run) | **A** |
| 9 | Đối chiếu kế hoạch ban đầu, hạn chế, kế hoạch còn lại | **A** |
| PL | Phụ lục: bảng kết quả chi tiết, hướng dẫn tái lập, **bộ ảnh minh chứng** | A + **B** |

> **A** = Hà (đang làm, có hỗ trợ AI) · **B** = người thứ hai.
> A ráp bản cuối. B nộp nguyên liệu theo đúng tên file quy ước bên dưới để ráp không phải sửa tay.

---

## 2. NHIỆM VỤ CỦA B

### B0 — Dựng lại hệ thống trên máy mình (bắt buộc trước mọi việc khác)

```bash
git checkout develop && git pull
cp .env.example .env          # giữ nguyên giá trị mặc định là chạy được
docker compose up -d --build  # 9 container
docker compose ps             # tất cả phải Up / healthy
```

Nạp dữ liệu và kiểm tra hợp đồng dataset:

```bash
docker compose run --rm -w /app training python scripts/import_dataset_snapshot.py --snapshot-dir data/snapshots/ohlcv_full_current --replace
```

```bash
docker compose run --rm -w /app training python scripts/check_group_dataset.py
```

Phải thấy dòng `Dataset check passed: local DB matches group_dataset_v1`. Nếu lỗi, xem mục 4 (Sự cố đã biết).

Huấn luyện 4 mô hình cho ACB (mỗi lệnh ~10–40 giây, riêng GRU lâu hơn):

```bash
docker compose run --rm training python train_arima.py --ticker ACB --timeframe 1d
```

Làm tương tự với `train_xgboost.py`, `train_random_forest.py`, `train_gru.py`. Ghi lại 4 `run_id` in ra ở cuối mỗi lệnh.

**Xong B0 khi:** 9 container chạy, dataset check PASS, MLflow UI (`http://localhost:5000`) thấy 4 experiment, và lệnh sau trả về JSON có mảng `predictions`:

```bash
curl -X POST http://localhost:8000/api/v1/predict -H "Content-Type: application/json" -H "X-API-Key: generate_a_secure_long_random_string_here" -d "{\"ticker_id\":\"ACB\",\"model_name\":\"gru\",\"steps\":3,\"timeframe\":\"1d\"}"
```

---

### B1 — Bộ ảnh minh chứng (ưu tiên cao nhất, hạn 25/09)

Đây là thứ thầy nhắc trực tiếp ("hình ảnh này nọ") và là thứ A **không thể tự làm thay**.

Lưu vào `docs/evidence/screenshots/` theo **đúng tên file** dưới đây (A sẽ chèn vào báo cáo bằng đúng tên này). PNG, chiều ngang **≥ 1400 px**, chụp full khung không lẫn thanh taskbar.

| Tên file | Nội dung phải thấy rõ |
|---|---|
| `01_dashboard.png` | Trang chủ: 4 ô thống kê (25 mã / 15 CP / 10 crypto / số model) + bảng danh sách mã |
| `02_symbols.png` | Trang Symbols, có dữ liệu giá thật |
| `03_forecast_form.png` | Trang Forecast **trước khi** bấm: đã chọn ACB + GRU + số bước |
| `04_forecast_chart.png` | Trang Forecast **sau khi** dự báo: biểu đồ nến OHLC + đường dự báo nối tiếp |
| `05_forecast_models_table.png` | Bảng "Mô hình đã đăng ký (MLflow Registry)" có MAE/RMSE/MAPE |
| `06_explainability_shap.png` | Trang SHAP Explain: biểu đồ mức ảnh hưởng feature của XGBoost |
| `07_swagger_overview.png` | `http://localhost:8000/docs` — thấy đủ 5 endpoint |
| `08_swagger_predict.png` | Mở rộng `POST /api/v1/predict`: schema request + response mẫu |
| `09_mlflow_experiments.png` | MLflow UI, danh sách experiment |
| `10_mlflow_run_detail.png` | Một run `ACB_1d_gru`: tab Parameters + Metrics nhìn thấy cùng lúc |
| `11_mlflow_registry.png` | MLflow → Models: danh sách model đã đăng ký |
| `12_docker_ps.png` | Terminal `docker compose ps`: 9 container Up/healthy |
| `13_ci_green.png` | GitHub Actions: 1 lần chạy CI xanh đủ **4 job** (lấy ở PR #45) |
| `14_pr_review.png` | Trang PR #45: mô tả + checks xanh |
| `15_board_agile.png` | GitHub Projects / Issues: board sprint (minh chứng cho RQ4) |
| `16_pytest.png` | Terminal kết quả `pytest` (xem B2) |

Gửi bằng PR: nhánh `docs/evidence-screenshots`, chỉ chứa thư mục ảnh.

> Lưu ý: `.gitignore` đang bỏ qua `*.zip` chứ không bỏ `*.png`, nên ảnh commit được bình thường. Nếu file ảnh > 2 MB thì nén lại trước khi commit.

---

### B2 — Chương 6: Kiểm thử & đảm bảo chất lượng (hạn 27/09)

Nộp file `reports/ch6_kiem_thu.md`. Cần **số liệu thật**, không viết chung chung.

**(a) Chạy test có đo độ phủ**

```bash
docker compose run --rm -w /app -e PYTHONPATH=/app training sh -c "pip install -q pytest pytest-asyncio pytest-mock httpx coverage && coverage run -m pytest --disable-warnings && coverage report"
```

Ghi lại: tổng số test pass/fail, thời gian chạy, độ phủ theo từng service. Chụp `16_pytest.png`.

**(b) Bảng test case** — lập bảng từ 17 file test hiện có (`services/*/tests/`, `tests/`), mỗi dòng: tên test · mục tiêu kiểm thử · loại (unit / integration) · kết quả. Nhóm theo service. Nêu rõ những phần **chưa có test** (đây là điểm trung thực thầy sẽ đánh giá cao).

**(c) Đo hiệu năng API — trả lời RQ5** (hiện đề tài **chưa có** số liệu này, tiêu chí nghiệm thu ghi p95 ≤ 2 giây)

Viết script `scripts/measure_api_latency.py`: gọi `POST /api/v1/predict` **50 lần** cho mỗi tổ hợp {4 mô hình} × {ACB 1d, BTCUSDT 1d}, ghi thời gian từng request, xuất CSV `artifacts/benchmarks/api_latency.csv` với các cột `model,symbol,timeframe,run_index,elapsed_ms,status_code,cache_hit` và in ra bảng tóm tắt p50 / p95 / p99 / max.

Bắt buộc phải đo **hai lần cho mỗi tổ hợp**: lần đầu (cache Redis rỗng, phải nạp model) và các lần sau (cache nóng) — hai con số này khác nhau rất nhiều và báo cáo phải nói rõ cả hai. Kết luận: có đạt p95 ≤ 2 s không, ở điều kiện nào.

**(d) Tỷ lệ job thành công của pipeline thu thập — cũng thuộc RQ5**

Tiêu chí đặt ra là ≥ 95%. Bảng `ops.job_log` đã có trong `infra/postgres/init.sql` nhưng **hiện không có dòng code nào ghi vào**. Hai lựa chọn, chọn 1 và ghi rõ trong báo cáo:

- *Cách nhanh:* để Celery Beat chạy ≥ 24 giờ, đếm số task thành công/thất bại từ log của `forecast_celery_worker` (`docker logs forecast_celery_worker`), lập bảng.
- *Cách chuẩn:* bổ sung ghi `ops.job_log` trong `services/ingestion/tasks.py` (mở PR riêng), rồi truy vấn thống kê bằng SQL.

**(e) Bảo mật** — kiểm chứng và chụp bằng chứng cho 3 điều: gọi API thiếu `X-API-Key` → 401; gọi quá `RATE_LIMIT_PER_MINUTE` lần/phút → 429; gửi `model_name` không hợp lệ → 422. Ghi lại lệnh `curl` và phản hồi thực tế. Nêu thêm: pre-commit có gitleaks quét secret, `.env` không commit.

---

### B3 — Chương 7: Quy trình Agile & quản lý dự án (hạn 27/09)

Nộp file `reports/ch7_agile.md`. Đây là chương trả lời **RQ4** và hiện là phần **yếu nhất** của đề tài: mới có `docs/sprint-logs/sprint-1..4.md`, đều là bản *tái dựng hồi cứu* từ lịch sử Git, trong khi kế hoạch cam kết 12 sprint.

Việc cần làm:

1. Viết `docs/sprint-logs/sprint-5.md` … `sprint-12.md` theo **đúng mẫu** của `sprint-4.md` (Sprint Goal · bảng backlog · nhật ký theo ngày · retrospective). Dựng lại từ nguồn thật: `git log --since=... --until=...`, danh sách PR (`gh pr list --state all`), issue đã đóng. **Ghi rõ ở đầu file** phần nào là tái dựng hồi cứu — đừng bịa biên bản họp.
2. Lập bảng tổng hợp 12 sprint: số story cam kết / hoàn thành, số PR merge, số commit → dùng vẽ **velocity chart** và **burndown**. Xuất số liệu ra `reports/agile_metrics.csv` (cột: `sprint,start,end,committed,completed,prs_merged,commits`) để A vẽ biểu đồ.
3. Viết phần phân tích định tính trả lời RQ4: Agile đã giúp gì (ví dụ: chia nhỏ theo model giúp 4 người làm song song không đụng nhau; CI chặn merge giúp không vỡ nhánh chính), và **vấn đề thật**: lịch sử commit tập trung ở một tài khoản, một số PR merge không có reviewer thứ hai (PR #44, #45) → đề xuất cách khắc phục nốt giai đoạn cuối.

---

### B4 — Trang Quản trị / Log (ưu tiên thấp hơn, hạn 29/09, làm nếu kịp)

Tiêu chí nghiệm thu yêu cầu Web App có **≥ 5 màn hình**; hiện chỉ có 4 (Dashboard, Symbols, Forecast, SHAP Explain). Thiếu đúng **trang quản trị/log** mà kế hoạch đã liệt kê.

Phạm vi tối thiểu: `frontend/app/admin/page.tsx` hiển thị (1) trạng thái các dịch vụ qua `/health`, (2) danh sách model đã đăng ký từ `GET /api/v1/models`, (3) bảng job thu thập gần nhất. Nếu mục (3) chưa có API thì bổ sung endpoint `GET /api/v1/jobs` đọc `ops.job_log` — ăn khớp luôn với B2(d).

Mở PR riêng, tag cả nhóm review vì `services/inference/` và `frontend/` là phần dùng chung.

---

## 3. Quy ước phối hợp

- Mỗi hạng mục = **một nhánh + một PR** riêng: `docs/evidence-screenshots`, `docs/ch6-kiem-thu`, `docs/ch7-agile`, `feat/admin-page`.
- Commit theo Conventional Commits, PR phải **CI xanh** và có **≥ 1 review** (AGENTS.md §8) — lần này làm cho đúng, vì chính chương 7 sẽ nói về kỷ luật quy trình.
- File `.md` nộp cho A: viết **nội dung**, không cần lo định dạng; A chịu trách nhiệm dựng DOCX.
- Số liệu phải kèm nguồn: lệnh đã chạy, run ID, đường dẫn file. Không có số thì ghi "chưa đo", **không ước lượng**.
- Vướng gì nhắn ngay, đừng để tới hạn.

## 4. Sự cố đã biết trên máy đã dựng thử

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `docker compose up` treo rất lâu ở bước tải image / `pip install` | Một số CDN (deb.debian.org, pypi.org, ghcr.io) bị nghẽn ở mạng VN, có lúc chỉ ~20–40 KB/s | Kiên nhẫn chờ, hoặc đổi mạng/VPN. Nếu vẫn treo hàng giờ: dùng mirror `mirror.bizflycloud.vn/debian` và `mirrors.sustech.edu.cn/pypi/web/simple` (chỉ sửa file Dockerfile tạm ở máy mình, **không commit**) |
| Cổng 5432 / 6379 / 8000 / 3000 bị chiếm | Máy đang chạy project khác | Dừng project kia, hoặc tạo `docker-compose.override.yml` ở máy mình đổi cổng (**không commit** file này) |
| `/api/v1/predict` báo `No such file or directory: /mlflow/artifacts/...` | Thiếu mount volume MLflow | Đã sửa ở PR #44 — chỉ cần `git pull` nhánh `develop` mới nhất |
| `/predict` với `model_name=gru` báo `X has 2 features, but MinMaxScaler is expecting 8` | Inference chưa cập nhật GRU v2 | Đã sửa ở PR #45 — `git pull` |
| Evaluator benchmark báo `Official benchmark requires a clean committed worktree` khi chạy trong container trên Windows | Khác biệt CRLF/filemode giữa Windows và Linux làm `git status` không sạch | Thêm vào lệnh: `-e GIT_CONFIG_COUNT=3 -e GIT_CONFIG_KEY_0=core.autocrlf -e GIT_CONFIG_VALUE_0=true -e GIT_CONFIG_KEY_1=core.filemode -e GIT_CONFIG_VALUE_1=false -e GIT_CONFIG_KEY_2=safe.directory -e GIT_CONFIG_VALUE_2=/app` |

## 5. Tóm tắt hạn

| Ngày | B phải xong |
|---|---|
| 25/09 | B0 + B1 (16 ảnh, PR đã mở) |
| 27/09 | B2 (`ch6_kiem_thu.md` + `api_latency.csv`) và B3 (`ch7_agile.md` + `agile_metrics.csv` + sprint 5–12) |
| 29/09 | B4 nếu kịp; sửa nốt góp ý của A sau khi ráp |
