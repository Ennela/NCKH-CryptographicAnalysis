# VNStock FastAPI Data Collector

Dự án dùng **FastAPI + Vnstock + PostgreSQL** để tự động lấy dữ liệu cổ phiếu Việt Nam và lưu vào database PostgreSQL.

Luồng hoạt động:

```text
Vnstock API → FastAPI Python → PostgreSQL → pgAdmin / API / SQL
```

---

## 1. Chức năng chính

Dự án hiện hỗ trợ:

- Lấy dữ liệu giá cổ phiếu dạng OHLCV.
- Lấy nhiều mã cổ phiếu cùng lúc.
- Lấy nhiều khung thời gian như `1D`, `1h`, `15m`.
- Lưu dữ liệu vào PostgreSQL.
- Chống lưu trùng bằng khóa `symbol + interval + candle_time`.
- Xem trạng thái lấy dữ liệu qua API.
- Xem thống kê dữ liệu đã lấy.
- Có thể mở rộng thêm dữ liệu công ty, báo cáo tài chính, bảng giá và intraday.

---

## 2. Cấu trúc thư mục

```text
vnstock_fastapi
│
├── app
│   ├── __init__.py
│   ├── database.py
│   ├── models.py
│   ├── vnstock_client.py
│   └── main.py
│
├── .env
├── requirements.txt
└── README.md
```

---

## 3. Cài đặt môi trường

Mở PowerShell:

```powershell
cd E:\vnstock_fastapi
py -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Cài thư viện:

```powershell
pip install -r requirements.txt
```

Nếu chưa có `requirements.txt`, cài trực tiếp:

```powershell
pip install fastapi "uvicorn[standard]" sqlalchemy "psycopg[binary]" python-dotenv pandas tqdm vnstock
```

Kiểm tra Vnstock:

```powershell
python -c "from vnstock import Market; print('VNSTOCK OK')"
```

---

## 4. Cấu hình file `.env`

Ví dụ:

```env
DATABASE_URL=postgresql+psycopg://postgres:MAT_KHAU_POSTGRES_CUA_BAN@localhost:5432/vnstock_db

AUTO_COLLECT_ON_STARTUP=true

AUTO_SYMBOL_SOURCE=CUSTOM
AUTO_SYMBOL_LIMIT=0
AUTO_SYMBOLS=FPT,VNM,HPG,VCB,TCB,CTG,BID,MBB,ACB,SSI,VND,HCM,MWG,PNJ,GAS,PLX,VIC,VHM,VRE,MSN

AUTO_INTERVALS=1D
AUTO_START_DATE=2024-01-01
AUTO_END_DATE=

AUTO_COLLECT_OHLCV=true
AUTO_COLLECT_COMPANY=false
AUTO_COLLECT_FINANCE=false
AUTO_COLLECT_PRICE_BOARD=false
AUTO_COLLECT_INTRADAY=false

AUTO_SLEEP_SECONDS=8
```

Ý nghĩa một số biến:

| Biến | Ý nghĩa |
|---|---|
| `DATABASE_URL` | Chuỗi kết nối PostgreSQL |
| `AUTO_COLLECT_ON_STARTUP` | Tự động lấy dữ liệu khi chạy server |
| `AUTO_SYMBOL_SOURCE` | Nguồn danh sách mã: `CUSTOM`, `VN30`, `ALL` |
| `AUTO_SYMBOLS` | Danh sách mã tự chọn |
| `AUTO_INTERVALS` | Khung thời gian cần lấy |
| `AUTO_START_DATE` | Ngày bắt đầu lấy dữ liệu |
| `AUTO_END_DATE` | Ngày kết thúc, để trống là đến hiện tại |
| `AUTO_SLEEP_SECONDS` | Thời gian nghỉ giữa các request để tránh rate limit |

---

## 5. Chạy chương trình

Trong PowerShell:

```powershell
cd E:\vnstock_fastapi
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --no-access-log
```

Nếu chạy đúng, terminal sẽ hiện:

```text
Uvicorn running on http://127.0.0.1:8000
```

---

## 6. Các đường dẫn API

Trang chính:

```text
http://127.0.0.1:8000
```

Giao diện Swagger:

```text
http://127.0.0.1:8000/docs
```

Xem trạng thái collector:

```text
http://127.0.0.1:8000/collector/status
```

Xem tổng số dòng dữ liệu:

```text
http://127.0.0.1:8000/stats
```

Xem danh sách mã đã lấy:

```text
http://127.0.0.1:8000/symbols
```

Xem tóm tắt dữ liệu:

```text
http://127.0.0.1:8000/summary
```

Nếu đã bật dữ liệu mở rộng:

```text
http://127.0.0.1:8000/raw-summary
```

---

## 7. Các bảng trong PostgreSQL

### Bảng `stock_ohlcv`

Lưu dữ liệu giá cổ phiếu theo thời gian.

| Cột | Ý nghĩa |
|---|---|
| `id` | ID tự tăng |
| `symbol` | Mã cổ phiếu, ví dụ `FPT`, `VNM` |
| `interval` | Khung thời gian, ví dụ `1D`, `1h`, `15m` |
| `candle_time` | Thời gian nến |
| `open_price` | Giá mở cửa |
| `high_price` | Giá cao nhất |
| `low_price` | Giá thấp nhất |
| `close_price` | Giá đóng cửa |
| `volume` | Khối lượng giao dịch |
| `raw_data` | Dữ liệu gốc dạng JSON |
| `created_at` | Thời điểm lưu vào database |

### Bảng `stock_raw_data`

Lưu dữ liệu mở rộng dạng JSONB, ví dụ:

- Thông tin công ty.
- Cổ đông.
- Ban lãnh đạo.
- Cổ tức.
- Sự kiện.
- Tin tức.
- Báo cáo tài chính.
- Chỉ số tài chính.
- Bảng giá.
- Intraday.

---

## 8. Xem dữ liệu bằng pgAdmin

Mở pgAdmin → chọn database:

```text
vnstock_db
```

Mở Query Tool rồi chạy các câu SQL dưới đây.

### Kiểm tra tổng số dòng

```sql
SELECT COUNT(*)
FROM stock_ohlcv;
```

### Xem đã lấy những mã nào

```sql
SELECT DISTINCT symbol
FROM stock_ohlcv
ORDER BY symbol;
```

### Xem dữ liệu tổng hợp theo mã

```sql
SELECT 
    symbol,
    interval,
    COUNT(*) AS so_dong,
    MIN(candle_time) AS tu_ngay,
    MAX(candle_time) AS den_ngay
FROM stock_ohlcv
GROUP BY symbol, interval
ORDER BY symbol, interval;
```

### Xem toàn bộ dữ liệu giá

```sql
SELECT 
    symbol,
    interval,
    candle_time,
    open_price,
    high_price,
    low_price,
    close_price,
    volume
FROM stock_ohlcv
ORDER BY symbol, interval, candle_time;
```

### Xem 1000 dòng mới nhất

```sql
SELECT 
    symbol,
    interval,
    candle_time,
    open_price,
    high_price,
    low_price,
    close_price,
    volume
FROM stock_ohlcv
ORDER BY candle_time DESC, symbol
LIMIT 1000;
```

### Xem riêng mã FPT

```sql
SELECT 
    symbol,
    interval,
    candle_time,
    open_price,
    high_price,
    low_price,
    close_price,
    volume
FROM stock_ohlcv
WHERE symbol = 'FPT'
ORDER BY candle_time DESC;
```

---

## 9. Xem dữ liệu mở rộng

Nếu đã bật:

```env
AUTO_COLLECT_COMPANY=true
AUTO_COLLECT_FINANCE=true
AUTO_COLLECT_PRICE_BOARD=true
```

Dữ liệu sẽ nằm trong bảng:

```text
stock_raw_data
```

### Xem có những loại dữ liệu nào

```sql
SELECT 
    symbol,
    data_type,
    period,
    COUNT(*) AS so_dong
FROM stock_raw_data
GROUP BY symbol, data_type, period
ORDER BY symbol, data_type, period;
```

### Xem thông tin công ty FPT

```sql
SELECT 
    symbol,
    data_type,
    payload
FROM stock_raw_data
WHERE symbol = 'FPT'
AND data_type IN ('overview', 'profile', 'shareholders', 'officers', 'dividends');
```

### Xem báo cáo tài chính FPT

```sql
SELECT 
    symbol,
    data_type,
    period,
    payload
FROM stock_raw_data
WHERE symbol = 'FPT'
AND data_type IN ('income_statement', 'balance_sheet', 'cash_flow', 'ratio');
```

---

## 10. Vấn đề Rate Limit của Vnstock

Nếu terminal hiện:

```text
GIỚI HẠN API ĐÃ ĐẠT TỐI ĐA
Rate Limit Exceeded
```

nghĩa là chương trình gọi API quá nhanh.

Cách xử lý:

```env
AUTO_SLEEP_SECONDS=8
```

Nếu vẫn bị giới hạn, tăng lên:

```env
AUTO_SLEEP_SECONDS=10
```

hoặc:

```env
AUTO_SLEEP_SECONDS=12
```

Với gói Guest, không nên lấy quá nhiều loại dữ liệu cùng lúc.

---

## 11. Gợi ý cấu hình theo từng giai đoạn

### Giai đoạn 1: Lấy dữ liệu giá ngày

```env
AUTO_SYMBOL_SOURCE=CUSTOM
AUTO_SYMBOLS=FPT,VNM,HPG,VCB,TCB,CTG,BID,MBB,ACB,SSI
AUTO_INTERVALS=1D
AUTO_COLLECT_OHLCV=true
AUTO_COLLECT_COMPANY=false
AUTO_COLLECT_FINANCE=false
AUTO_SLEEP_SECONDS=8
```

### Giai đoạn 2: Mở rộng nhiều mã hơn

```env
AUTO_SYMBOLS=FPT,VNM,HPG,VCB,TCB,CTG,BID,MBB,ACB,SSI,VND,HCM,MWG,PNJ,GAS,PLX,VIC,VHM,VRE,MSN
AUTO_INTERVALS=1D
AUTO_SLEEP_SECONDS=8
```

### Giai đoạn 3: Thêm dữ liệu công ty

```env
AUTO_COLLECT_COMPANY=true
AUTO_SLEEP_SECONDS=10
```

### Giai đoạn 4: Thêm báo cáo tài chính

```env
AUTO_COLLECT_FINANCE=true
AUTO_SLEEP_SECONDS=12
```

Chưa nên bật ngay:

```env
AUTO_COLLECT_INTRADAY=true
```

vì intraday nặng và dễ chạm giới hạn API.

---

## 12. Ghi chú

Nếu terminal hiện:

```text
seen=100 inserted=0
```

Nghĩa là:

```text
seen=100      → Vnstock trả về 100 dòng dữ liệu
inserted=0    → dữ liệu đã tồn tại trong PostgreSQL nên không lưu trùng
```

Đây không phải lỗi.

Nếu muốn lấy thêm dữ liệu mới, hãy mở rộng `AUTO_SYMBOLS`, `AUTO_INTERVALS` hoặc thay đổi `AUTO_START_DATE`.
