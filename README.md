# Hệ Thống Thu Thập, Phân Tích Trực Quan & Dự Báo Giá Cổ Phiếu & Tiền Số (VN-Stock & Crypto)

Dự án Nghiên cứu Khoa học và Đồ án tốt nghiệp 6 tháng phát triển bởi nhóm 5 sinh viên. Hệ thống tự động thu thập dữ liệu giá từ thị trường chứng khoán Việt Nam (`vnstock`) và thị trường tiền mã hóa (`ccxt`/Binance), lưu trữ hiệu năng cao bằng TimescaleDB, huấn luyện các mô hình dự báo chuỗi thời gian (ARIMA, XGBoost, LSTM, GRU), quản lý vòng đời mô hình bằng MLflow và hiển thị trực quan thông qua ứng dụng Next.js & ECharts kết hợp giải thích mô hình bằng SHAP.

---

## Stack Công Nghệ

*   **Backend**: Python 3.11 + FastAPI (Kiến trúc đa dịch vụ / Microservices)
*   **Database**: PostgreSQL 16 + TimescaleDB (Lưu trữ chuỗi thời gian dưới dạng Hypertable)
*   **Message Broker & Task Queue**: Redis + Celery & Celery Beat (Lập lịch thu thập dữ liệu)
*   **Machine Learning / Deep Learning**: PyTorch (LSTM/GRU), XGBoost (Baseline mạnh + giải thích bằng SHAP), Statsmodels (ARIMA baseline), Optuna (Tối ưu hóa hyperparameter), MLflow (Quản lý log và registry mô hình)
*   **Frontend**: React 18 + Next.js (App Router, TypeScript) + Apache ECharts (Biểu đồ phân tích kỹ thuật và dự báo)
*   **DevOps & CI/CD**: Docker & Docker Compose, GitHub Actions (CI: Ruff + Pytest; CD: Build & Deploy), Sentry (Giám sát lỗi)

---

## Cấu Trúc Monorepo

```txt
stock-crypto-forecast/
├─ .github/workflows/
│  ├─ ci.yml                      # CI: Lint (Ruff) + Test (Pytest) + Build test
│  └─ deploy.yml                  # CD: Build và Deploy tự động khi merge main
├─ docs/
│  ├─ architecture.md             # Tài liệu kiến trúc hệ thống, luồng dữ liệu & ERD
│  ├─ api.md                      # Hợp đồng API chi tiết (FastAPI /predict và /models)
│  └─ sprint-logs/                # Nhật ký Agile/Scrum của nhóm 5 thành viên
├─ infra/
│  ├─ postgres/init.sql           # Khởi tạo DB, kích hoạt TimescaleDB, tạo Hypertables
│  └─ nginx/nginx.conf            # Reverse Proxy cấu hình cho Nginx (bản Production)
├─ shared/                        # Package dùng chung được cài đặt dạng local library (pip -e)
│  ├─ config/                     # Đọc cấu hình từ .env qua pydantic-settings
│  ├─ db/                         # SQLAlchemy session, engine, model khai báo bảng
│  ├─ schemas/                    # Pydantic schemas dùng chung (OHLCV, Request/Response)
│  └─ utils/                      # Ghi log có cấu trúc, múi giờ UTC, các hàm tính toán chỉ số (Returns, Volatility, RSI, MACD, MAE, RMSE, MAPE)
├─ services/
│  ├─ ingestion/                  # Dịch vụ thu thập: CCXT (Binance) + Vnstock crawler, Celery beat & worker
│  ├─ training/                   # Dịch vụ train: Data loader, Feature engineering, PyTorch models, MLflow logger, train & evaluation scripts
│  └─ inference/                  # Dịch vụ dự báo: API FastAPI /predict và /models, Model loader cached từ MLflow, Redis caching, Rate-limit
├─ frontend/                      # Ứng dụng Next.js + TailwindCSS + ECharts
├─ scripts/                       # Các file kịch bản backfill dữ liệu lịch sử & seeding database
├─ docker-compose.yml             # Môi trường Local Development
├─ docker-compose.prod.yml        # Môi trường Production (Thêm Nginx)
├─ .env.example                   # Khai báo biến môi trường mẫu
├─ .gitignore
├─ Makefile                       # Công cụ chạy nhanh các lệnh dev/build/test/migrate
└─ README.md                      # Hướng dẫn này
```

---

## Hướng Dẫn Cài Đặt & Chạy Hệ Thống

### 1. Chuẩn bị môi trường
Yêu cầu máy cài sẵn **Docker** và **Docker Compose**.
Nếu muốn dev local không qua Docker, yêu cầu **Python 3.11** và **Node.js 18+**.

### 2. Thiết lập cấu hình môi trường
Tạo file `.env` từ file mẫu:
```bash
cp .env.example .env
```
Mở file `.env` ra và cập nhật các thông số cần thiết như thông tin kết nối DB, API Keys, v.v.

### 3. Khởi động môi trường Development bằng Docker Compose
Tất cả các dịch vụ (PostgreSQL + TimescaleDB, Redis, MLflow, Ingestion, Training, Inference, Frontend) sẽ được khởi tạo tự động:
```bash
make dev-up
```
Hệ thống sẽ chạy ở các cổng mặc định:
*   **FastAPI Inference (API chính)**: [http://localhost:8000](http://localhost:8000)
*   **Next.js Frontend**: [http://localhost:3000](http://localhost:3000)
*   **MLflow Tracking UI**: [http://localhost:5000](http://localhost:5000)
*   **FastAPI Ingestion (Health check)**: [http://localhost:8001](http://localhost:8001)

Để dừng tất cả các dịch vụ và làm sạch volume:
```bash
make dev-down
```

### 4. Khởi động bản Production (Bao gồm Nginx Reverse Proxy)
```bash
make prod-up
```

---

## Quy Trình Phát Triển & Kiểm Thử

### Kiểm tra code định dạng (Linter & Formatter)
Hệ thống sử dụng **Ruff** để duy trì chất lượng code sạch:
```bash
# Check lỗi lint
make lint

# Tự động sửa định dạng code
make format
```

### Chạy Unit Test
```bash
make test
```

### Chạy Seed dữ liệu ảo & Backfill lịch sử
Để đưa nhanh dữ liệu mẫu vào DB phục vụ phát triển frontend & backend:
```bash
# Tạo các mã chứng khoán/crypto mẫu và nến giá giả định
make seed

# Thu thập dữ liệu lịch sử thực tế (Ví dụ BTC/USDT trong 30 ngày)
make backfill
```

---

## Phân Chia Vai Trò Nhóm (5 Sinh Viên)

Để đảm bảo hiệu quả làm việc theo Agile, các thành viên được phân vai trò rõ ràng:

1.  **Dev 1 (Team Leader & MLOps)**: Phụ trách cấu hình Docker, CI/CD, MLflow Tracking/Registry, hạ tầng PostgreSQL/TimescaleDB và deployment.
2.  **Dev 2 (Data Engineer)**: Phát triển dịch vụ `ingestion`, viết crawler `vnstock` + `ccxt/binance`, lập lịch Celery beat và kiểm soát chất lượng dữ liệu đầu vào.
3.  **Dev 3 (ML/DL Developer - Baselines & Classic)**: Nghiên cứu các mô hình thống kê (ARIMA), mô hình Machine Learning cổ điển (XGBoost), tối ưu hóa Hyperparameters (Optuna) và tính năng giải thích mô hình SHAP.
4.  **Dev 4 (DL Developer - Deep Learning)**: Phát triển và tối ưu hóa các kiến trúc mạng nơ-ron chuỗi thời gian bằng PyTorch (LSTM, GRU), xử lý Data Loader và Time-series Split.
5.  **Dev 5 (Frontend Developer)**: Phát triển ứng dụng Web bằng Next.js, tích hợp thư viện vẽ biểu đồ ECharts (nến giá + đường dự báo tương lai), hiển thị biểu đồ lực lượng SHAP.

---

## Quy Tắc Commit & Làm Việc Nhóm

*   **Không commit trực tiếp vào `main`**: Luôn tạo branch từ `develop` theo cấu trúc: `feature/<tên-tính-năng>`.
*   **Quy ước commit message**: Tuân thủ conventional commits:
    *   `feat(ingestion): thêm crawler binance realtime`
    *   `fix(training): sửa lỗi chiều dữ liệu đầu vào LSTM`
    *   `docs(api): cập nhật hợp đồng phản hồi của /predict`
    *   `refactor(shared): tối ưu hóa tính toán MACD/RSI`
*   **Pull Request**: Phải chạy `make lint` thành công trên local trước khi tạo PR. GitHub Actions sẽ tự động kiểm thử code trước khi cho phép merge vào `develop`.
