# Binance FastAPI Data Collector

Dự án FastAPI dùng để tự động lấy dữ liệu nến KLINES từ Binance Spot và lưu vào PostgreSQL để phục vụ phân tích dữ liệu hoặc huấn luyện mô hình Machine Learning.

## 1. Chức năng chính

- Lấy dữ liệu nến OHLCV từ Binance Spot.
- Lưu dữ liệu vào PostgreSQL.
- Hỗ trợ nhiều đồng coin cùng lúc.
- Hỗ trợ nhiều khung thời gian: `1m`, `5m`, `15m`, `1h`, `4h`, `1d`...
- Tự động lấy dữ liệu khi khởi chạy chương trình.
- Có thanh tiến trình khi tải dữ liệu.
- Không lưu trùng dữ liệu nhờ khóa unique theo `symbol`, `interval`, `open_time`.
- Có API kiểm tra trạng thái collector.
- Có API xem thống kê số dòng dữ liệu đã lưu.

## 2. Công nghệ sử dụng

- Python
- FastAPI
- Uvicorn
- SQLAlchemy
- PostgreSQL
- Psycopg
- HTTPX
- Python Dotenv
- TQDM

## 3. Cấu trúc thư mục

```text
binance_fastapi/
│
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── database.py
│   ├── models.py
│   └── binance_client.py
│
├── .venv/
├── .env
├── requirements.txt
└── README.md
```

## 4. Cài đặt môi trường

Mở PowerShell trong thư mục dự án:

```powershell
cd E:\binance_fastapi
```

Tạo môi trường ảo:

```powershell
py -m venv .venv
```

Cho phép PowerShell chạy script trong phiên hiện tại:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Kích hoạt môi trường ảo:

```powershell
.\.venv\Scripts\Activate.ps1
```

Cài thư viện:

```powershell
pip install -r requirements.txt
```

Nếu chưa có `requirements.txt`, có thể cài trực tiếp:

```powershell
pip install fastapi "uvicorn[standard]" sqlalchemy "psycopg[binary]" python-dotenv httpx tqdm
```

## 5. Cấu hình PostgreSQL

Tạo database trong PostgreSQL với tên:

```text
binance_db
```

Tạo file `.env` trong thư mục gốc của dự án:

```env
DATABASE_URL=postgresql+psycopg://postgres:MAT_KHAU_POSTGRES@localhost:5432/binance_db

AUTO_COLLECT_ON_STARTUP=true

AUTO_START_DATE=2024-01-01T00:00:00
AUTO_END_DATE=

AUTO_SYMBOL_MODE=USDT
AUTO_SYMBOL_LIMIT=5

AUTO_INTERVALS=1m,5m,15m,1h
AUTO_CHUNK=month

AUTO_SLEEP_SECONDS=0.2
AUTO_SAVE_RAW=false
AUTO_REPEAT_MINUTES=0
```

Lưu ý: không chia sẻ file `.env` vì trong đó có mật khẩu PostgreSQL.

## 6. Ý nghĩa các cấu hình `.env`

| Biến | Ý nghĩa |
|---|---|
| `DATABASE_URL` | Chuỗi kết nối PostgreSQL |
| `AUTO_COLLECT_ON_STARTUP` | Tự động tải dữ liệu khi chạy server |
| `AUTO_START_DATE` | Ngày bắt đầu lấy dữ liệu |
| `AUTO_END_DATE` | Ngày kết thúc. Để trống nghĩa là lấy đến hiện tại |
| `AUTO_SYMBOL_MODE` | Lọc coin theo quote asset, ví dụ `USDT`, hoặc `ALL` |
| `AUTO_SYMBOL_LIMIT` | Giới hạn số coin cần lấy. `0` nghĩa là lấy tất cả |
| `AUTO_INTERVALS` | Danh sách khung thời gian cần lấy |
| `AUTO_CHUNK` | Chia dữ liệu theo `day` hoặc `month` |
| `AUTO_SLEEP_SECONDS` | Thời gian nghỉ giữa các request |
| `AUTO_SAVE_RAW` | Có lưu dữ liệu JSON thô hay không |
| `AUTO_REPEAT_MINUTES` | Tự chạy lại sau số phút. `0` nghĩa là không lặp |

## 7. Khởi chạy chương trình

Chạy server FastAPI:

```powershell
python -m uvicorn app.main:app --no-access-log
```

Nếu chạy thành công sẽ thấy:

```text
Uvicorn running on http://127.0.0.1:8000
```

Mở trình duyệt:

```text
http://127.0.0.1:8000
```

Mở giao diện API:

```text
http://127.0.0.1:8000/docs
```

## 8. Các API chính

### Trang kiểm tra server

```http
GET /
```

Kết quả ví dụ:

```json
{
  "message": "Binance FastAPI dang chay",
  "docs": "/docs",
  "collector_status": "/collector/status"
}
```

### Xem trạng thái tải dữ liệu

```http
GET /collector/status
```

Khi đang chạy:

```json
{
  "running": true,
  "message": "Dang lay BTCUSDT 1m...",
  "current_symbol": "BTCUSDT",
  "current_interval": "1m"
}
```

Khi chạy xong:

```json
{
  "running": false,
  "message": "đã lấy xong dữ liệu"
}
```

### Xem thống kê dữ liệu

```http
GET /stats
```

Kết quả ví dụ:

```json
{
  "spot_klines": 250000,
  "agg_trades": 0,
  "order_book_snapshots": 0,
  "raw_binance_data": 0
}
```

### Lấy dữ liệu một coin

```http
POST /collect/klines
```

Tham số ví dụ:

```text
symbol=BTCUSDT
interval=1m
start=2024-01-01T00:00:00
end=2024-01-02T00:00:00
```

### Lấy nhiều coin và nhiều interval

```http
POST /collect/all-klines
```

Tham số ví dụ:

```text
symbol_mode=USDT
symbol_limit=5
intervals=1m,5m,15m,1h
start=2024-01-01T00:00:00
end=
chunk=month
```

## 9. Dữ liệu được lưu ở đâu?

Dữ liệu không được lưu thành file CSV trong thư mục project. Dữ liệu được lưu trực tiếp vào PostgreSQL:

```text
Database: binance_db
Table: spot_klines
```

PostgreSQL lưu file vật lý trong thư mục `data` của PostgreSQL, ví dụ:

```text
E:\postgresql\data
```

Không nên mở, sửa hoặc xóa trực tiếp các file trong thư mục `data` vì có thể làm hỏng database.

## 10. Các trường dữ liệu trong bảng `spot_klines`

| Cột | Ý nghĩa |
|---|---|
| `id` | ID tự tăng trong PostgreSQL |
| `symbol` | Cặp tiền, ví dụ `BTCUSDT` |
| `interval` | Khung thời gian, ví dụ `1m`, `5m`, `1h` |
| `open_time` | Thời gian mở nến dạng milliseconds |
| `close_time` | Thời gian đóng nến dạng milliseconds |
| `open_price` | Giá mở cửa |
| `high_price` | Giá cao nhất |
| `low_price` | Giá thấp nhất |
| `close_price` | Giá đóng cửa |
| `volume` | Khối lượng giao dịch theo base asset |
| `quote_asset_volume` | Khối lượng giao dịch theo quote asset |
| `number_of_trades` | Số lượng giao dịch trong nến |
| `taker_buy_base_asset_volume` | Khối lượng mua chủ động theo base asset |
| `taker_buy_quote_asset_volume` | Khối lượng mua chủ động theo quote asset |
| `ignore_value` | Trường phụ Binance trả về |
| `created_at` | Thời gian lưu vào PostgreSQL |

## 11. Câu lệnh SQL kiểm tra dữ liệu

Xem tổng số dòng:

```sql
SELECT COUNT(*)
FROM spot_klines;
```

Xem 50 dòng mới nhất:

```sql
SELECT 
    symbol,
    interval,
    to_timestamp(open_time / 1000) AS thoi_gian_mo_nen,
    to_timestamp(close_time / 1000) AS thoi_gian_dong_nen,
    open_price,
    high_price,
    low_price,
    close_price,
    volume,
    quote_asset_volume,
    number_of_trades,
    taker_buy_base_asset_volume,
    taker_buy_quote_asset_volume
FROM spot_klines
ORDER BY open_time DESC
LIMIT 50;
```

Xem đã lấy những coin nào:

```sql
SELECT DISTINCT symbol
FROM spot_klines
ORDER BY symbol;
```

Xem số dòng theo từng coin và interval:

```sql
SELECT 
    symbol,
    interval,
    COUNT(*) AS so_dong
FROM spot_klines
GROUP BY symbol, interval
ORDER BY symbol, interval;
```

Xem dữ liệu đã lấy từ ngày nào đến ngày nào:

```sql
SELECT 
    symbol,
    interval,
    COUNT(*) AS so_dong,
    to_timestamp(MIN(open_time) / 1000) AS tu_ngay,
    to_timestamp(MAX(open_time) / 1000) AS den_ngay
FROM spot_klines
GROUP BY symbol, interval
ORDER BY symbol, interval;
```

Xem riêng một coin:

```sql
SELECT 
    symbol,
    interval,
    to_timestamp(open_time / 1000) AS thoi_gian,
    open_price,
    high_price,
    low_price,
    close_price,
    volume,
    number_of_trades
FROM spot_klines
WHERE symbol = 'BTCUSDT'
AND interval = '1m'
ORDER BY open_time DESC
LIMIT 100;
```

## 12. Gợi ý cấu hình tải dữ liệu

Cấu hình test nhẹ:

```env
AUTO_SYMBOL_MODE=USDT
AUTO_SYMBOL_LIMIT=5
AUTO_INTERVALS=1m,5m,15m,1h
AUTO_START_DATE=2025-12-01T00:00:00
AUTO_END_DATE=
AUTO_CHUNK=month
```

Cấu hình vừa:

```env
AUTO_SYMBOL_MODE=USDT
AUTO_SYMBOL_LIMIT=50
AUTO_INTERVALS=1m,5m,15m,1h,4h,1d
AUTO_START_DATE=2024-01-01T00:00:00
AUTO_END_DATE=
AUTO_CHUNK=month
```

Cấu hình rất lớn:

```env
AUTO_SYMBOL_MODE=ALL
AUTO_SYMBOL_LIMIT=0
AUTO_INTERVALS=1m,5m,15m,1h,4h,1d
AUTO_START_DATE=2020-01-01T00:00:00
AUTO_END_DATE=
AUTO_CHUNK=month
```

Cảnh báo: cấu hình rất lớn có thể chạy rất lâu và chiếm nhiều dung lượng ổ cứng.

## 13. Lỗi thường gặp

### Lỗi không kích hoạt được `.venv`

Chạy:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### Lỗi không tìm thấy module `app`

Đảm bảo đang đứng trong thư mục gốc:

```powershell
cd E:\binance_fastapi
python -m uvicorn app.main:app --no-access-log
```

### Lỗi kết nối PostgreSQL

Kiểm tra lại:

- PostgreSQL đang chạy chưa.
- Database `binance_db` đã được tạo chưa.
- Mật khẩu trong `.env` đã đúng chưa.
- Port PostgreSQL có phải `5432` không.

### Lỗi dữ liệu không tăng

Kiểm tra:

```sql
SELECT COUNT(*)
FROM spot_klines;
```

Nếu dữ liệu đã tồn tại, chương trình sẽ không lưu trùng nên số dòng có thể không tăng nhiều.

## 14. Ghi chú quan trọng

- Không chia sẻ file `.env`.
- Không xóa trực tiếp thư mục `E:\postgresql\data`.
- Không nên bật `AUTO_SYMBOL_MODE=ALL` ngay từ đầu.
- Nên test với ít coin trước, sau đó tăng dần `AUTO_SYMBOL_LIMIT`.
- Dữ liệu đang lưu vào PostgreSQL, không phải file CSV trong thư mục project.
