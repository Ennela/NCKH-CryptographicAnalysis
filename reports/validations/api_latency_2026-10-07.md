# Đo độ trễ API dự báo (RQ5 — tiêu chí p95 ≤ 2 giây) — 07/10/2026

## Cách đo

- Script: `reports/src/measure_latency.py` (chỉ dùng thư viện chuẩn Python). Số liệu
  thô từng request: `reports/validations/api_latency_2026-10-07.csv`.
- Hệ thống: stack Docker local (máy phát triển Windows, CPU), `inference` khởi động
  lại ngay trước khi đo. Code `develop` `b81f17f` + bản sửa rate limit (PR #65).
- Request: `POST /api/v1/predict`, `ACB`, `1d`, `steps = 5`, đo thời gian đầu-cuối phía
  client (gồm mạng nội bộ Docker).
- Ba kịch bản cho mỗi mô hình:
  - **first_call**: request đầu tiên sau khi container khởi động — tải model từ MLflow
    vào bộ nhớ (1 lần).
  - **cache_miss**: xóa khóa cache Redis trước mỗi request, model chạy thật (10 lần).
  - **cache_hit**: lặp lại cùng request, trả từ Redis (30 lần).
- Request được giãn 1,1 giây/lần để nằm dưới `RATE_LIMIT_PER_MINUTE = 60`.
- Percentile theo hạng gần nhất; với 10 mẫu, p95 chính là giá trị lớn nhất.

## Kết quả (ms) — 164/164 request trả HTTP 200

| Mô hình | first_call | cache_miss p50 | cache_miss p95 | cache_hit p50 | cache_hit p95 |
|---|---:|---:|---:|---:|---:|
| ARIMA | 4 656 | 213 | 559 | 21 | 40 |
| XGBoost | 1 226 | 460 | 555 | 17 | 27 |
| Random Forest | 839 | 576 | 681 | 21 | 38 |
| GRU | 4 097 | 186 | 293 | 17 | 39 |

## Kết luận

- **Đạt p95 ≤ 2 giây** cho cả 4 mô hình ở trạng thái vận hành bình thường: p95 khi
  model thật sự chạy ≤ 0,68 giây, khi trúng cache ≤ 0,04 giây.
- **Ngoại lệ**: request đầu tiên sau khi khởi động `inference` mất 4,1–4,7 giây với
  ARIMA và GRU (tải model từ MLflow). Chỉ xảy ra một lần mỗi model mỗi lần khởi động;
  có thể loại bỏ bằng bước nạp sẵn (warm-up) model khi service khởi động.
- Hạn chế: đo tuần tự từ một client trên máy phát triển, chưa đo tải đồng thời.

## Vì sao lần đo trước (Chương 6) báo lỗi

Lần đo trong `reports/ch6_kiem_thu.md` chỉ có số liệu ARIMA, các mô hình khác "phản hồi
lỗi". Nguyên nhân là lỗi của rate limiter, không phải lỗi mô hình: bộ đếm làm mới TTL
60 giây sau mọi request nên không bao giờ về 0 khi request đến đều đặn, và client bị trả
`429` sau request thứ 60 tính tổng. Lần đo đầu tiên ngày 07/10 (trước khi sửa, cùng
kịch bản) lặp lại đúng hiện tượng này: 52/164 request bị `429`, toàn bộ là các request
sau request thứ 60. Đã sửa ở PR #65 (đếm theo từng phút cố định).
