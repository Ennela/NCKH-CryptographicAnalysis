# Tổng hợp số liệu cho báo cáo cuối kỳ (chốt ngày 09/10/2026)

> Tài liệu này gom **mọi con số** nhóm cần để viết báo cáo cuối kỳ, mỗi số kèm nguồn kiểm
> chứng (lệnh, tệp, PR, MLflow run). Không có số nào ước lượng hay tự điền: chỗ nào chưa đo
> được ghi là "chưa đo". Mọi số liệu lấy từ stack Docker local trên máy phát triển, nhánh
> `develop` (sau PR #66, commit `8580035`) cùng các PR mở ngày 09/10 ghi rõ ở từng mục.

---

## 1. Đối chiếu tiêu chí nghiệm thu (thay Bảng 9.2 của bản V2)

| Tiêu chí | Yêu cầu | Hiện trạng (09/10/2026) | Đánh giá | Nguồn |
|---|---|---|---|---|
| Thu thập tự động | Chạy theo lịch, có log | Celery Beat + Worker, log ở `ops.job_log`. Ingest 29/29 thành công. Clean 31/46 thành công trước khi sửa lỗi kết nối (mục 6). Cổ phiếu VN tạm dừng vì `vnstock` bị PyPI cách ly | Đạt (crypto); cổ phiếu tạm dừng | §6 |
| Độ tin cậy thu thập (NFR-08) | Tỷ lệ job thành công ≥ 95 % trong ≥ 24 giờ | 60/75 = 80 % (16/09–05/10); đã sửa nguyên nhân (PR #67); đang chạy lại 24 giờ từ 09/10 21:58 giờ VN | **Chưa đạt** — chờ số đo lại | §6 |
| Web App | ≥ 5 màn hình | 5 màn hình: Tổng quan, Dữ liệu & Phân tích, Dự báo AI, Giải thích mô hình, Thu thập & Làm sạch | **Đạt** | PR #51, #64; ảnh `docs/evidence/screenshots/ui/` |
| API dự báo | p95 ≤ 2 giây | p95 khi model chạy ≤ 0,68 s, khi trúng cache ≤ 0,04 s (cả 4 mô hình) | **Đạt** | §3; PR #66 |
| Bảo mật tối thiểu | API key, rate limit, kiểm tra đầu vào | Đủ 3 lớp; rate limit đã sửa (PR #65) | Đạt (rủi ro: API key lộ qua `NEXT_PUBLIC_API_KEY`) | `docs/api.md` |
| Số mô hình | ≥ 3 baseline + ≥ 1 học sâu | Naive, ARIMA, XGBoost, Random Forest, GRU (PyTorch) | Đạt | MLflow Registry: 36 model |
| So sánh trên cùng tập test | Bắt buộc | Có, kèm cổng kiểm định độc lập (evaluator) | Đạt | `services/training/benchmark_contract.py` |
| Ablation | ≥ 1 thí nghiệm | GRU bỏ nhóm đặc trưng, 9 chuỗi × 3 biến thể × 3 seed | **Đạt** | §4 |
| Vượt Naive ở ≥ 70 % số mã | Tiêu chí chính | 4/9 chuỗi (44 %) | **Chưa đạt** | §2 |
| Tài liệu | Đủ chương, trích dẫn, nhật ký sprint | Nhật ký sprint 1–10 (sprint 10 đang diễn ra); sprint 11–12 chưa diễn ra | Một phần | `docs/sprint-logs/` |

---

## 2. Kết quả dự báo so với Naive (9 chuỗi × 4 mô hình)

Nguồn: phiên bản mới nhất của 36 model trong MLflow Registry (truy vấn ngày 09/10). Các model
RF/GRU/ARIMA được train lại ngày 05/10 để sinh artifact giải thích; RMSE trùng bản cũ (GRU,
ARIMA lệch 0; RF lệch ≤ 3,6e-12 do thứ tự cộng số thực khi `n_jobs=-1`).

| Chuỗi | Mô hình tốt nhất | Cải thiện RMSE so với Naive | Các mô hình vượt Naive |
|---|---|---:|---|
| ACB 1d | GRU | +0,72 % | ARIMA, GRU |
| BTCUSDT 1d | ARIMA | −0,23 % | — |
| BTCUSDT 1h | ARIMA | −0,02 % | — |
| ETHUSDT 1d | GRU | −2,71 % | — |
| FPT 1d | GRU | −0,44 % | — |
| HPG 1d | Random Forest | +6,40 % | GRU, Random Forest |
| SOLUSDT 1d | ARIMA | −0,24 % | — |
| VCB 1d | GRU | +1,07 % | GRU |
| VNM 1d | ARIMA | +3,31 % | ARIMA, GRU |

- **4/9 chuỗi (44 %)** có ít nhất một mô hình vượt Naive → tiêu chí ≥ 70 % **chưa đạt**.
- Theo mô hình: GRU 4/9, ARIMA 2/9, Random Forest 1/9, XGBoost 0/9.
- Mức vượt đều nhỏ (0,7–6,4 %). Chưa có kiểm định ý nghĩa thống kê (ví dụ Diebold–Mariano).

---

## 3. Độ trễ API (RQ5)

Nguồn: `reports/validations/api_latency_2026-10-07.md` + `.csv`, script
`reports/src/measure_latency.py`. `POST /api/v1/predict`, ACB 1d, 5 bước; 164/164 request
HTTP 200.

| Mô hình | Lần gọi đầu (tải model) | Model chạy thật p50 / p95 | Trúng cache p50 / p95 |
|---|---:|---:|---:|
| ARIMA | 4 656 ms | 213 / 559 ms | 21 / 40 ms |
| XGBoost | 1 226 ms | 460 / 555 ms | 17 / 27 ms |
| Random Forest | 839 ms | 576 / 681 ms | 21 / 38 ms |
| GRU | 4 097 ms | 186 / 293 ms | 17 / 39 ms |

Hạn chế: đo tuần tự từ một client trên máy phát triển, chưa đo tải đồng thời. Lần đo trước
(Chương 6 cũ) bị rate limiter chặn: lỗi đã được sửa ở PR #65.

---

## 4. Thí nghiệm ablation (GRU)

**Câu hỏi:** bảy đặc trưng kỹ thuật (trung bình trượt 7/14, lợi suất 1/3/7 phiên, độ lệch
chuẩn cuộn 7/14) có giúp GRU dự báo tốt hơn so với chỉ dùng giá đóng cửa không?

**Thiết kế:** `services/training/ablation_gru.py` train lại GRU với 3 tập đặc trưng: `full` (8),
`close_moving_averages` (close + MA7 + MA14), `close_only` (1). Mọi thứ khác giữ nguyên:
cùng pipeline dữ liệu và scaler fit trên train của `train_gru.py`, cùng kiến trúc, early
stopping trên validation, đánh giá trên tập test. 9 chuỗi × 3 biến thể × 3 seed (42, 43, 44) =
81 run, log vào MLflow experiment `ablation_gru_features` (không đăng ký model).

**Kiểm tra tính đúng:** biến thể `full` với seed 42 tái lập **chính xác** RMSE của 9 model
GRU đang đăng ký (chênh lệch 0).

**Kết quả** (RMSE trung bình ± độ lệch chuẩn qua 3 seed; nguồn:
`reports/validations/ablation_gru_features_2026-10-09.csv`, tóm tắt bằng
`python reports/src/ablation_summary.py <csv>`):

| Chuỗi | Naive | full (8) | close + MA (3) | close_only (1) | close_only so với full | Vượt 2σ? |
|---|---:|---:|---:|---:|---:|:-:|
| ACB 1d | 0,3902 | 0,3873 ± 0,0004 | 0,3898 ± 0,0006 | 0,3895 ± < 0,0001 | +0,55 % (kém hơn) | Có |
| BTCUSDT 1d | 1386,27 | 1435,63 ± 3,06 | 1421,37 ± 0,56 | 1422,86 ± 2,81 | −0,89 % | Có |
| BTCUSDT 1h | 308,39 | 378,18 ± 9,79 | 411,37 ± 29,6 | 345,36 ± 7,66 | −8,68 % | Có |
| ETHUSDT 1d | 56,48 | 58,23 ± 0,24 | 57,88 ± 0,03 | 57,88 ± 0,01 | −0,60 % | Không |
| FPT 1d | 1,5785 | 1,5828 ± 0,0070 | 1,6123 ± 0,0055 | 1,5825 ± 0,0042 | −0,02 % | Không |
| HPG 1d | 0,4141 | 0,4137 ± 0,0003 | 0,4127 ± 0,0001 | 0,4126 ± 0,0003 | −0,27 % | Có |
| SOLUSDT 1d | 2,3431 | 2,7049 ± 0,0876 | 2,9140 ± 0,0547 | 2,5519 ± 0,0598 | −5,66 % | Không |
| VCB 1d | 1,0317 | 1,0214 ± 0,0015 | 1,0222 ± 0,0002 | 1,0197 ± 0,0001 | −0,17 % | Không |
| VNM 1d | 0,8614 | 0,8373 ± 0,0175 | 0,8557 ± 0,0032 | 0,8548 ± 0,0017 | +2,10 % (kém hơn) | Không |

("Vượt 2σ?": chênh lệch giữa close_only và full lớn hơn 2 lần độ lệch chuẩn giữa các seed —
quy tắc thô với 3 seed, **không phải** kiểm định thống kê.)

**Kết luận:**
- Bỏ 7 đặc trưng kỹ thuật, chỉ giữ `close`, cho RMSE trung bình **thấp hơn hoặc bằng** ở 7/9
  chuỗi. Chênh lệch vượt mức dao động giữa các seed ở 4/9 chuỗi: tốt hơn rõ ở BTCUSDT 1d,
  BTCUSDT 1h, HPG; kém hơn rõ ở ACB. 5 chuỗi còn lại nằm trong mức nhiễu.
- Nghĩa là trong cấu hình hiện tại, các đặc trưng kỹ thuật **không đem lại lợi ích ổn định**
  cho GRU. Kết quả này khớp với permutation importance (§5): GRU gần như chỉ dựa vào `close`.
- Không biến thể nào thay đổi bức tranh so với Naive: cả `full` lẫn `close_only` đều vượt
  Naive (theo trung bình 3 seed) ở cùng 4 chuỗi ACB, HPG, VCB, VNM.
- Độ dao động giữa các seed đáng kể ở một số chuỗi (VNM full: 0,8373 ± 0,0175), nên kết quả
  benchmark một seed (seed 42) cần được đọc kèm cảnh báo này.

---

## 5. Giải thích mô hình (XAI)

Nguồn: artifact `explainability/feature_importance.json` của từng run trong MLflow (PR
#60–#64); ảnh `ui_09`, `ui_17`–`ui_19`.

| Mô hình | Phương pháp | Phát hiện chính (9 chuỗi) |
|---|---|---|
| XGBoost | SHAP TreeExplainer (mean \|SHAP\| trên tập test) | Đứng đầu luôn là đặc trưng mức giá gần: `close_lag_1`, `rolling_mean_5`, `close_lag_10`, `rolling_min_10` |
| Random Forest | SHAP TreeExplainer | `close` đứng đầu ở 9/9 chuỗi, tiếp theo là `low` / `high` / `rolling_mean_20` |
| GRU | Permutation importance (xáo trộn từng đặc trưng trên tập test, 5 lần, seed cố định) | Xáo `close` làm RMSE tăng thêm 1,01–22,8 lần RMSE gốc (thấp nhất FPT, cao nhất BTCUSDT 1h); mọi đặc trưng khác làm RMSE tăng < 0,6 % RMSE gốc ở cả 9 chuỗi. Khớp với thiết kế residual (dự báo = giá gần nhất + hiệu chỉnh) |
| ARIMA(1,1,1) | Bảng hệ số, sai số chuẩn, p-value | Cả ar.L1 và ma.L1 có ý nghĩa (p < 0,05) ở 4/9 chuỗi: ACB, ETHUSDT, VCB, VNM; ở đó ar.L1 ≈ −ma.L1 (gần triệt tiêu → gần bước ngẫu nhiên). Không có ý nghĩa ở BTCUSDT 1d, FPT, HPG, SOLUSDT; BTCUSDT 1h ở ngưỡng (p = 0,052 / 0,069) |

**Hạn chế phát hiện được:** ARIMA ở BTCUSDT 1d và HPG có `ma.L1` = −7,87 và −6,73 (p ≈
0,70–0,98), vì bậc được cố định (1,1,1) và tắt ràng buộc khả nghịch
(`enforce_invertibility=False`). Ước lượng ở hai chuỗi này không đáng tin.

Chi tiết từng model (run ID, top đặc trưng): xem `reports/validations/explainability_2026-10-09.txt`.

---

## 6. Vận hành pipeline thu thập (`ops.job_log`)

Nguồn: truy vấn trực tiếp `ops.job_log` trên DB local.

| Giai đoạn | Loại job | Thành công | Thất bại | Kẹt ở `running` |
|---|---|---:|---:|---:|
| Vận hành 16/09 – 05/10 | ingest | 29 | 0 | 0 |
| Vận hành 16/09 – 05/10 | clean | 31 | 4 | 11 |

- Tỷ lệ thành công tổng: 60/75 = 80 %. Riêng ingest: 100 %; riêng clean: 67 %.
- Nguyên nhân lỗi clean: tiến trình con của Celery (prefork) dùng chung kết nối Postgres của
  tiến trình cha. Đã tái hiện (20 tác vụ đồng thời: 15/20 rồi 12/20 thành công) và sửa (20/20
  ở cả 2 lần chạy): **PR #67**.
- Các job thử nghiệm ngày 09/10 cũng được ghi vào `ops.job_log` (81 dòng, từ 14:45 UTC); khi
  thống kê cần loại theo `started_at`.
- Chương 6 cũ ghi "11 thành công, 0 thất bại" từ log container: số đó không khớp
  `ops.job_log` và nên thay bằng bảng trên.

---

## 7. Kiểm thử

- CI trên `develop` (run 37943063671, commit `8580035`): **335 test passed**, có dịch vụ
  TimescaleDB thật. Nhận xét "test ingestion fail do môi trường" ở Chương 6 chỉ đúng khi chạy
  trên máy không có DB.
- Test mới trong các PR ngày 09/10: ablation (5 test), Celery fork-safety (2 test).
- Frontend chưa có test tự động (không có tệp `*.test.*` / `*.spec.*`).

---

## 8. Quy mô hệ thống (thay Bảng 1.1 của bản V2)

| Hạng mục | Giá trị | Nguồn |
|---|---|---|
| Dịch vụ trong `docker-compose.yml` | 9: postgres, redis, mlflow, ingestion, celery-worker, celery-beat, training, inference, frontend | `docker-compose.yml` |
| API | 10 endpoint: `/health` công khai + 9 yêu cầu API key | `services/inference/main.py` |
| Bảng có dữ liệu | `market.*` 4/4; `ops.job_log`, `ops.data_quality_check`; nhóm `ml.*` 0/8 (chưa có luồng ghi) | truy vấn DB |
| Dữ liệu khóa (snapshot) | 192 740 dòng OHLCV, 25 mã (15 cổ phiếu VN + 10 crypto) | `data/snapshots/ohlcv_full_current/manifest.json` |
| Dữ liệu trong DB sau backfill | `market.ohlcv` 213 164 dòng | truy vấn DB |
| MLflow | 36 model đăng ký; 135 run trong 39 experiment | MLflow API |
| Pull Request đã merge | 57 (đến PR #66) | `gh pr list --state merged` |

---

## 9. Quy trình (Chương 7)

`reports/agile_metrics.csv` sinh lại ngày 09/10 bằng `reports/src/agile_metrics.py`:

| Sprint | Thời gian | Commit | Tác giả | PR mở | PR merge |
|---:|---|---:|---:|---:|---:|
| 9 | 21/09 – 04/10 | 22 | 3 | 14 | 13 |
| 10* | 05/10 – 18/10 | 9 | 1 | 7 | 7 |

\* đang diễn ra, tính đến 09/10 (trước các PR mở ngày 09/10).

- Nhật ký: `docs/sprint-logs/sprint-9.md` (đã chốt), `sprint-10.md` (đang diễn ra).
- Ghi chú trung thực: commit của tài khoản Ennela từ 22/09 đều có dòng
  `Co-Authored-By: Claude` (viết với trợ giúp AI agent). Hầu hết PR merge không có review
  của thành viên khác; branch protection vẫn chưa bật dù Chương 7 đã cam kết.

---

## 10. Hạn chế cần nêu trong báo cáo

1. Tiêu chí vượt Naive ở ≥ 70 % số mã chưa đạt (44 %); mức vượt nhỏ, chưa kiểm định thống kê.
2. Mô hình cây (XGBoost, RF) không ngoại suy được ra ngoài vùng giá đã thấy: thua Naive nặng ở
   chuỗi có xu hướng mạnh (SOLUSDT, BTCUSDT, ETHUSDT, FPT).
3. ARIMA bậc cố định (1,1,1), tắt ràng buộc khả nghịch → ước lượng không ổn định ở một số chuỗi.
4. Ablation và mọi kết quả dùng một lần chia train/val/test cố định; độ dao động mới ước lượng
   qua 3 seed.
5. Thu thập cổ phiếu VN tạm dừng do `vnstock` bị PyPI cách ly; FPT 1d còn khoảng trống
   08/07 – 11/09.
6. Nhóm bảng `ml.*` chưa có luồng ghi nên `/predict` không lưu lịch sử dự báo vào DB.
7. Lần gọi đầu sau khi khởi động inference mất 4,1–4,7 s với ARIMA/GRU (tải model từ MLflow).
8. API key nằm trong biến `NEXT_PUBLIC_*` nên lộ ra trình duyệt; chưa có đăng nhập.
9. Frontend chưa có test tự động.

---

## 11. Danh sách minh chứng

- Ảnh giao diện: `docs/evidence/screenshots/ui/ui_01` … `ui_19` (`ui_09`, `ui_17`–`ui_19`
  chụp lại ngày 09/10 cho 4 mô hình giải thích); sinh bằng `reports/src/capture.py`.
- Độ trễ API: `reports/validations/api_latency_2026-10-07.{md,csv}`.
- Ablation: `reports/validations/ablation_gru_features_2026-10-09.csv`, tóm tắt bằng
  `reports/src/ablation_summary.py`.
- Giải thích mô hình: `reports/validations/explainability_2026-10-09.txt`.
- Agile: `reports/agile_metrics.csv`, `docs/sprint-logs/`.
