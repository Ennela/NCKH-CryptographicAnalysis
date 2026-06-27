# Hệ Thống Thu Thập, Phân Tích Trực Quan & Dự Báo Giá Cổ Phiếu & Tiền Số

Hệ thống tự động thu thập dữ liệu giá từ **thị trường chứng khoán Việt Nam** (vnstock) và **thị trường tiền mã hóa** (Binance), lưu trữ hiệu năng cao bằng **TimescaleDB**, huấn luyện các mô hình dự báo chuỗi thời gian (**ARIMA, XGBoost, LSTM, GRU**), quản lý vòng đời mô hình bằng **MLflow** và hiển thị trực quan thông qua ứng dụng **Next.js & ECharts** kết hợp giải thích mô hình bằng **SHAP**.

---

## Thành Viên Nhóm

| STT | Họ và Tên | Mã Sinh Viên | Lớp |
|:---:|-----------|:------------:|:----:|
| 1 | **Đỗ Quang Hà** *(Chủ nhiệm đề tài)* | 23810310132 | D18CNPM2 |
| 2 | Nguyễn Văn Kiên | 23810310138 | D18CNPM2 |
| 3 | Khiếu Đình Trung Nguyên | 24810310401 | D19CNPM4 |
| 4 | Nguyễn Trọng Đại | 23810310120 | D18CNPM2 |
| 5 | Lê Hải Nam | 23810310377 | D18CNPM5 |
| 6 | Nguyễn Trọng Hiếu | 24810340513 | D19CNPM1 |

---

## 🛠️ Stack Công Nghệ

| Thành phần | Công nghệ |
|------------|-----------|
| **Backend** | Python 3.11 + FastAPI (Kiến trúc đa dịch vụ) |
| **Database** | PostgreSQL 16 + TimescaleDB (Hypertable cho chuỗi thời gian) |
| **Task Queue** | Redis + Celery & Celery Beat |
| **ML / DL** | PyTorch (LSTM, GRU), XGBoost, Statsmodels (ARIMA), Optuna, MLflow |
| **Giải thích mô hình** | SHAP (SHapley Additive exPlanations) |
| **Frontend** | React 18 + Next.js (App Router, TypeScript) + Apache ECharts |
| **DevOps & CI/CD** | Docker & Docker Compose, GitHub Actions, Sentry |
| **Code Quality** | Ruff (lint & format), Pytest, pre-commit hooks |

---

## Cấu Trúc Thư Mục

```
NCKH/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                    # CI: Lint (Ruff) + Test (Pytest)
│   │   └── deploy.yml                # CD: Build & Deploy tự động
│   ├── CODEOWNERS                    # Phân quyền review theo thư mục
│   └── pull_request_template.md      # Template cho Pull Request
│
├── docs/
│   ├── architecture.md               # Tài liệu kiến trúc hệ thống & ERD
│   ├── api.md                        # Hợp đồng API (endpoints, request/response)
│   ├── experiment_report.md          # Báo cáo kết quả thí nghiệm ML
│   └── sprint-logs/                  # Nhật ký Agile/Scrum theo sprint
│
├── infra/
│   ├── postgres/init.sql             # Khởi tạo DB, TimescaleDB, Hypertables
│   └── nginx/nginx.conf              # Reverse Proxy cho Production
│
├── shared/                           # Package Python dùng chung (pip install -e .)
│   ├── config/settings.py            # Đọc cấu hình từ .env (pydantic-settings)
│   ├── db/
│   │   ├── models.py                 # SQLAlchemy ORM models (market schema)
│   │   ├── session.py                # Engine & Session factory
│   │   ├── mappers.py                # Object mappers (DB ↔ Pydantic)
│   │   ├── base.py                   # Declarative Base
│   │   └── repositories/             # Repository pattern cho truy vấn DB
│   ├── schemas/
│   │   ├── ohlcv.py                  # Schema OHLCV (Open-High-Low-Close-Volume)
│   │   └── predict.py                # Schema Request/Response cho dự báo
│   └── utils/
│       ├── logging.py                # Structured logging
│       ├── metrics.py                # Chỉ số kỹ thuật (RSI, MACD, Returns, Volatility)
│       └── timezone.py               # Xử lý múi giờ UTC
│
├── services/
│   ├── ingestion/                    # Dịch vụ THU THẬP dữ liệu
│   │   ├── adapters/
│   │   │   ├── binance_adapter.py    #   ↳ Adapter CCXT/Binance (crypto)
│   │   │   └── vnstock_adapter.py    #   ↳ Adapter vnstock (cổ phiếu VN)
│   │   ├── celery_app.py             # Cấu hình Celery worker & beat
│   │   ├── tasks.py                  # Celery tasks: lập lịch thu thập
│   │   ├── main.py                   # FastAPI health-check endpoint
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── training/                     # Dịch vụ HUẤN LUYỆN mô hình
│   │   ├── models/
│   │   │   ├── arima_model.py        #   ↳ ARIMA baseline (statsmodels)
│   │   │   ├── xgboost_model.py      #   ↳ XGBoost + SHAP
│   │   │   └── nn_models.py          #   ↳ LSTM & GRU (PyTorch)
│   │   ├── data_loader.py            # Tải & chia dữ liệu theo thời gian
│   │   ├── train.py                  # Script huấn luyện chính
│   │   ├── evaluate.py               # Đánh giá mô hình (MAE, RMSE, MAPE)
│   │   ├── mlflow_utils.py           # Tiện ích log MLflow
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   └── inference/                    # Dịch vụ DỰ BÁO (API chính)
│       ├── main.py                   # FastAPI: /predict, /models, /symbols
│       ├── model_loader.py           # Load model từ MLflow Registry
│       ├── redis_cache.py            # Redis caching cho kết quả dự báo
│       ├── Dockerfile
│       └── requirements.txt
│
├── frontend/                         # Ứng dụng WEB (Next.js + TypeScript)
│   ├── app/
│   │   ├── page.tsx                  # Trang chủ (Dashboard)
│   │   ├── layout.tsx                # Layout chung
│   │   ├── forecast/page.tsx         # Trang dự báo giá
│   │   ├── symbols/page.tsx          # Trang danh sách mã chứng khoán/crypto
│   │   └── explainability/           # Trang giải thích mô hình SHAP
│   ├── components/
│   │   ├── chart.tsx                 # Component biểu đồ ECharts
│   │   └── navbar.tsx                # Thanh điều hướng
│   ├── Dockerfile
│   └── package.json
│
├── api/                              # Collector cũ (đang gộp vào services/ingestion)
│   ├── binance_fastapi/              #   ↳ API thu thập Binance (legacy)
│   └── vnstock_fastapi/              #   ↳ API thu thập vnstock (legacy)
│
├── scripts/
│   ├── backfill.py                   # Backfill dữ liệu lịch sử
│   └── seed_db.py                    # Seed dữ liệu mẫu vào DB
│
├── migrations/                       # Alembic migrations (quản lý schema DB)
│   ├── env.py
│   └── versions/
│
├── tests/                            # Unit & Integration tests
│   ├── conftest.py
│   ├── test_db_connection.py
│   ├── test_mappers.py
│   ├── test_market_repo.py
│   └── test_settings.py
│
├── docker-compose.yml                # Môi trường Development
├── docker-compose.prod.yml           # Môi trường Production (+ Nginx)
├── Makefile                          # Lệnh tắt: dev-up, test, lint, seed...
├── alembic.ini                       # Cấu hình Alembic
├── .env.example                      # Biến môi trường mẫu
├── .pre-commit-config.yaml           # Pre-commit hooks
├── .gitignore
├── AGENTS.md                         # Quy tắc phát triển cho nhóm & AI agent
└── README.md                         # ← Bạn đang ở đây
```

---

##  Hướng Dẫn Cài Đặt & Chạy

### Yêu cầu hệ thống

- [Docker](https://docs.docker.com/get-docker/) & [Docker Compose](https://docs.docker.com/compose/install/) (khuyến nghị)
- Hoặc nếu chạy không qua Docker: **Python 3.11+**, **Node.js 18+**, **PostgreSQL 16** (với TimescaleDB), **Redis**

### 1. Clone repository

```bash
git clone https://github.com/Ennela/NCKH-CryptographicAnalysis.git
cd NCKH-CryptographicAnalysis
```

### 2. Thiết lập biến môi trường

```bash
cp .env.example .env
```

Mở file `.env` và cập nhật các thông số:
- Thông tin kết nối **PostgreSQL** (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, ...)
- **API Keys** (Binance, vnstock nếu cần)
- Cấu hình **Redis**, **MLflow**, **Sentry**

### 3. Khởi động Development (Docker Compose)

```bash
make dev-up
```

Tất cả dịch vụ sẽ được build và khởi tạo tự động:

| Dịch vụ | URL | Mô tả |
|---------|-----|-------|
| **Frontend** (Next.js) | [http://localhost:3000](http://localhost:3000) | Giao diện web chính |
| **Inference API** (FastAPI) | [http://localhost:8000](http://localhost:8000) | API dự báo & quản lý mô hình |
| **Ingestion API** | [http://localhost:8001](http://localhost:8001) | Health check dịch vụ thu thập |
| **MLflow Tracking** | [http://localhost:5000](http://localhost:5000) | UI quản lý thí nghiệm ML |

### 4. Dừng hệ thống

```bash
# Dừng và xóa volumes (development)
make dev-down

# Hoặc chỉ dừng containers
docker-compose down
```

### 5. Khởi động Production (có Nginx Reverse Proxy)

```bash
make prod-up
```

---

## Phát Triển & Kiểm Thử

### Các lệnh Make thường dùng

```bash
make help               # Xem tất cả lệnh có sẵn

# Code Quality
make lint               # Kiểm tra lỗi lint (Ruff)
make format             # Tự động format code (Ruff)

# Testing
make test               # Chạy toàn bộ unit & integration tests

# Database
make migrate-generate   # Tạo migration mới (Alembic autogenerate)
make migrate-run        # Chạy migrations lên DB

# Dữ liệu
make seed               # Tạo dữ liệu mẫu (mã CK/crypto + nến giá)
make backfill           # Thu thập dữ liệu lịch sử thực tế
```

### Chạy Frontend riêng (không qua Docker)

```bash
cd frontend
npm install
npm run dev
```

Frontend sẽ chạy tại [http://localhost:3000](http://localhost:3000).

### Chạy Backend riêng (không qua Docker)

```bash
# Cài shared package ở chế độ editable
pip install -e shared/

# Chạy Inference API
cd services/inference
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Chạy Ingestion API
cd services/ingestion
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

---

## Quy Trình Machine Learning

```
Thu thập dữ liệu          Feature Engineering         Huấn luyện & Đánh giá
┌──────────────┐          ┌──────────────────┐        ┌───────────────────────┐
│  Binance API │──┐       │  RSI, MACD       │        │  ARIMA (baseline)     │
│  vnstock     │──┼──────▶│  Returns         │───────▶│  XGBoost + SHAP      │
│  Celery Beat │──┘       │  Volatility      │        │  LSTM / GRU (PyTorch) │
└──────────────┘          └──────────────────┘        └───────────┬───────────┘
                                                                  │
                          ┌──────────────────┐                    │
                          │  MLflow Tracking │◀───────────────────┘
                          │  & Registry      │
                          └────────┬─────────┘
                                   │
                          ┌────────▼─────────┐        ┌───────────────────────┐
                          │  Model Loader    │───────▶│  FastAPI /predict     │
                          │  + Redis Cache   │        │  Next.js Dashboard    │
                          └──────────────────┘        └───────────────────────┘
```

**Nguyên tắc quan trọng:**
- Chia dữ liệu **theo thời gian** (không xáo trộn) để tránh rò rỉ dữ liệu
- Scaler/Encoder chỉ **fit trên tập train**, transform cho valid/test
- Cố định **random seed** để đảm bảo tái lập kết quả
- Mọi thí nghiệm đều **log vào MLflow** (params, metrics, artifacts)
- So sánh với **baseline Naive** — kết quả không có baseline là vô nghĩa

---

## Tài Liệu Tham Khảo

- [`docs/architecture.md`](docs/architecture.md) — Kiến trúc hệ thống, luồng dữ liệu & ERD
- [`docs/api.md`](docs/api.md) — Hợp đồng API chi tiết (endpoints, request/response)
- [`docs/experiment_report.md`](docs/experiment_report.md) — Báo cáo kết quả thí nghiệm ML
- [`AGENTS.md`](AGENTS.md) — Quy tắc phát triển cho nhóm & AI agent

---

## Quy Tắc Git & Bảo Mật

- **Không commit trực tiếp** vào `main` hoặc `develop`. Tạo branch: `feature/<tên-tính-năng>`
- **Conventional Commits**: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`
- **Pull Request** cần ≥ 1 thành viên review & duyệt trước khi merge
- **Không commit** `.env`, API key, secret, hoặc dataset lớn vào repo

