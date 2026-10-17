# Triển khai bản production (`docker-compose.prod.yml`)

Tài liệu hướng dẫn dựng toàn bộ hệ thống ở chế độ production trên một máy có
Docker, rồi (tùy chọn) mở ra Internet bằng Cloudflare Tunnel để demo.

## 1. Kiến trúc khi chạy production

```
Người xem ──HTTPS──▶ Cloudflare ──tunnel──▶ cloudflared ─┐      (tùy chọn)
Người xem ──HTTP───────────────────────────────────────▶ nginx :80
                                                          ├─ /         → frontend (Next.js, next start)
                                                          └─ /api/v1/  → inference (FastAPI) + gắn X-API-Key
inference ─▶ postgres (TimescaleDB), redis, mlflow (Model Registry)
celery-worker + celery-beat ─▶ thu thập/làm sạch dữ liệu theo lịch
```

- Chỉ **nginx** mở cổng ra máy chủ (`NGINX_HTTP_PORT`, mặc định 80). Postgres,
  Redis, MLflow, inference đều chỉ nằm trong mạng Docker.
- Trình duyệt gọi `/api/v1/...` cùng tên miền; **nginx tự gắn `X-API-Key`**, nên
  khóa API không bị nhúng vào mã JavaScript. Hệ quả là API qua nginx mở cho mọi
  người xem web, được bảo vệ bằng giới hạn tần suất: nginx 10 request/giây/IP
  (burst 40) cho `/api/v1/`, cộng giới hạn theo phút của inference cho
  `/predict` và `/explain` (`RATE_LIMIT_PER_MINUTE`).
- IP người xem được nginx chuyển qua `X-Forwarded-For` (uvicorn chạy
  `--proxy-headers`); khi đi qua tunnel, nginx lấy IP thật từ `CF-Connecting-IP`
  (chỉ tin header này khi kết nối đến từ mạng nội bộ Docker).
- nginx chỉ phục vụ HTTP. HTTPS do Cloudflare đảm nhận (mục 5), hoặc do một
  reverse proxy/certbot trên máy chủ (mục 6).

## 2. Yêu cầu máy

| Hạng mục | Tối thiểu | Ghi chú |
|---|---|---|
| CPU | 2 vCPU | Đo 17/10/2026 trên máy 16 luồng: build khoảng 6,5 phút, `prod_bootstrap.sh` khoảng 19 phút |
| RAM | 4 GB (khuyến nghị 8 GB) | 9 container chạy cùng lúc |
| Ổ đĩa | 30 GB trống | Image khoảng 14 GB (training 4,8 GB, inference 4,6 GB) + volume dữ liệu |
| Phần mềm | Docker Engine + Docker Compose v2, Git | Linux, hoặc Windows/macOS có Docker Desktop |

## 3. Dựng hệ thống

```bash
git clone https://github.com/Ennela/NCKH-CryptographicAnalysis.git
cd NCKH-CryptographicAnalysis
git checkout develop
```

Tạo file `.env` ở thư mục gốc (không commit). Mật khẩu và khóa nên sinh ngẫu
nhiên, ví dụ `python -c "import secrets; print(secrets.token_urlsafe(32))"`:

```dotenv
ENV=production
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<mật khẩu ngẫu nhiên>
POSTGRES_DB=stock_crypto_db
API_KEY_SECRET=<khóa ngẫu nhiên>
SENTRY_DSN=
# Đổi nếu cổng 80 của máy đã bị dùng
NGINX_HTTP_PORT=80
```

`DEBUG` mặc định là `false` trong file compose prod (bật lên sẽ in mọi câu SQL
ra log). Không cần `NEXT_PUBLIC_API_URL`/`NEXT_PUBLIC_API_KEY`: frontend prod
gọi API cùng tên miền và nginx gắn khóa.

Build và chạy:

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

## 4. Nạp dữ liệu và model lần đầu

Máy mới có cơ sở dữ liệu và MLflow Registry trống. Chép snapshot dữ liệu đã khóa
(không có trong Git, xem `docs/dataset.md`) vào
`data/snapshots/ohlcv_full_current/`, rồi chạy:

```bash
bash scripts/prod_bootstrap.sh
```

Script lần lượt: nạp snapshot → kiểm tra hợp đồng dữ liệu → nối dữ liệu crypto từ
cuối snapshot tới hiện tại → train 4 mô hình cho 9 chuỗi và đăng ký vào MLflow →
khởi động lại inference. Dùng `--skip-train` để bỏ bước train; đặt
`BOOTSTRAP_SERIES="ACB:1d BTCUSDT:1h"` để train ít chuỗi hơn.

Sau đó mở `http://<máy chủ>:<NGINX_HTTP_PORT>/`.

**Giới hạn đã biết:** gói `vnstock` đang bị PyPI cách ly nên image ingestion mặc
định không cài; dữ liệu cổ phiếu dừng ở cuối snapshot, chỉ crypto tự cập nhật
theo lịch. Xem `docs/dataset.md`.

## 5. Mở ra Internet bằng Cloudflare Tunnel (demo)

Không cần mở cổng router, không cần tên miền, có HTTPS sẵn.

### 5.1. Quick tunnel (không cần tài khoản)

```bash
docker compose -f docker-compose.prod.yml --profile tunnel up -d cloudflared
docker compose -f docker-compose.prod.yml logs cloudflared | grep trycloudflare.com
```

Địa chỉ dạng `https://<chuỗi-ngẫu-nhiên>.trycloudflare.com` in trong log. Địa chỉ
**đổi mỗi lần container khởi động lại** và Cloudflare chỉ dành quick tunnel cho
thử nghiệm, nên hợp với buổi demo hơn là chạy lâu dài. Tắt tunnel:

```bash
docker compose -f docker-compose.prod.yml stop cloudflared
```

### 5.2. Named tunnel (địa chỉ cố định)

Cần tài khoản Cloudflare và một tên miền đã trỏ nameserver về Cloudflare.

1. Cloudflare Zero Trust → Networks → Tunnels → Create a tunnel (cloudflared).
2. Phần Public hostname: chọn tên miền con, Service `HTTP`, URL `nginx:80`.
3. Sao chép token, thêm vào `.env`: `TUNNEL_TOKEN=<token>`.
4. Tạo `docker-compose.tunnel.yml` (không commit) để đổi lệnh của `cloudflared`:

   ```yaml
   services:
     cloudflared:
       command: ["tunnel", "--no-autoupdate", "run"]
       environment:
         - TUNNEL_TOKEN=${TUNNEL_TOKEN}
   ```

5. Chạy:
   `docker compose -f docker-compose.prod.yml -f docker-compose.tunnel.yml --profile tunnel up -d cloudflared`.

## 6. Máy chủ có IP công khai (không dùng tunnel)

Đặt `NGINX_HTTP_PORT=80`, mở cổng 80/443 trên tường lửa, trỏ tên miền về IP máy
chủ và cấp chứng chỉ HTTPS bằng một reverse proxy trên máy chủ (ví dụ Caddy, tự
cấp chứng chỉ Let's Encrypt) chuyển tiếp về `http://127.0.0.1:<NGINX_HTTP_PORT>`.
Khi đó nên bật proxy của Cloudflare hoặc giới hạn truy cập theo IP nếu không muốn
API mở cho mọi người.

## 7. Đã kiểm thử (17/10/2026, Docker Desktop trên Windows, `NGINX_HTTP_PORT=8088`)

- `up -d --build` từ volume trống: mọi dịch vụ chạy, MLflow `healthy`.
- `prod_bootstrap.sh`: nạp snapshot (fingerprint khớp), nối crypto 10 mã tới
  17/10 (1h: khoảng 2.399 nến/mã, 1d: 101 nến/mã), train và đăng ký đủ 36 model.
- Qua nginx, không gửi khóa: 5 màn hình tải dữ liệu thật; `/predict` và
  `/explain` của cả 4 mô hình trả 200; bấm "Tiến hành dự báo" trên giao diện chạy được.
- Khóa API thật không có trong `.next/` của frontend.
- Inference thấy IP người gọi (không phải IP nginx); `X-Forwarded-For` do client
  tự gửi bị bỏ qua.
- 80 request đồng thời: nginx cho qua 41, trả 429 cho 39; `/explain` vượt
  khoảng 60 lượt/phút bị inference trả 429.
- Tạo lại container inference: nginx tự theo IP mới, không 502.

## 8. Vận hành

| Việc | Lệnh |
|---|---|
| Xem trạng thái | `docker compose -f docker-compose.prod.yml ps` |
| Xem log một dịch vụ | `docker compose -f docker-compose.prod.yml logs -f inference` |
| Cập nhật mã nguồn | `git pull` rồi `docker compose -f docker-compose.prod.yml up -d --build` |
| Dừng (giữ dữ liệu) | `docker compose -f docker-compose.prod.yml down` |
| Xóa sạch cả dữ liệu | `docker compose -f docker-compose.prod.yml down -v` |

Dữ liệu nằm trong các volume `postgres_prod_data`, `redis_prod_data`,
`mlflow_prod_data`; `down` không xóa chúng, `down -v` thì có.
