# NCKH-CryptographicAnalysis

## Overview
Hệ thống thu thập, phân tích và dự báo giá cổ phiếu & tiền mã hóa sử dụng Machine Learning, phát triển theo quy trình Agile.
## Objectives
- Crawl dữ liệu từ các sàn, trang web (Binance,VNStock,...)
- Xây dựng pipeline xử lý dữ liệu
- Áp dụng ML/DL để dự báo giá
- Triển khai API phục vụ dự đoán

## Technologies
- Python
- ML:
- SQL: 
- Data:
- Backend:
- Agile:


# Rules + Workflow

## Chiến Lược Branch

### Các branch chính

```txt
main
develop
```

---

## Vai trò của từng branch

### `main`

* Chứa phiên bản ổn định của project
* Chỉ merge từ `develop`
* Không được commit trực tiếp

---

### `develop`

* Branch phát triển chính
* Tất cả feature sẽ merge vào đây trước
* Dùng để test tích hợp toàn hệ thống

---

### `feature/*`

Dùng để phát triển tính năng mới.

Ví dụ:

```txt
feature/binance-crawler
feature/data-cleaning
feature/xgboost-model
feature/lstm-model
feature/chart-dashboard
feature/backend-api
```

---

## Workflow làm việc

```txt
main
 ↑
develop
 ↑
feature/*
```

Luồng phát triển:

```txt
feature branch
↓
code tính năng
↓
pull request / merge request
↓
merge vào develop
↓
test
↓
merge develop → main
```

---

# Quy Tắc Làm Việc Nhóm

## 1. Không commit trực tiếp vào `main`

Không được commit trực tiếp vào:

```txt
main
```

Luôn tạo branch mới trước khi code.

---

## 2. Tạo feature branch trước khi làm việc

Ví dụ:

```bash
git checkout develop

git pull origin develop

git checkout -b feature/xgboost-model
```

---

## 3. Pull code mới nhất trước khi bắt đầu

```bash
git checkout develop

git pull origin develop
```

---

## 4. Commit thường xuyên

Commit sau khi hoàn thành một phần nhỏ.

Nên:

```txt
- thêm crawler
- sửa bug API
- update model train
```

Không nên:

```txt
- commit quá nhiều thay đổi không liên quan
```

---

## 5. Viết commit message rõ ràng

Sử dụng commit convention.

---

## 6. Test trước khi merge

Trước khi merge cần:

* đảm bảo code chạy ổn định
* không làm hỏng chức năng cũ
* không chứa file thừa

---

## 7. Không commit file nhạy cảm

Không được commit:

```txt
.env
API keys
secret tokens
dataset lớn
model đã train
```

---

# Quy Ước Commit

## Format

```txt
type(scope): message
```

---

## Các loại commit

| Type     | Ý nghĩa                 |
| -------- | ----------------------- |
| feat     | thêm tính năng mới      |
| fix      | sửa lỗi                 |
| refactor | cải thiện cấu trúc code |
| docs     | thay đổi tài liệu       |
| test     | thêm hoặc sửa test      |
| chore    | tác vụ bảo trì          |

---

## Ví dụ commit

### Thêm tính năng

```txt
feat(crawler): thêm crawler cho binance
```

```txt
feat(ml): xây dựng pipeline train xgboost
```

---

### Sửa lỗi

```txt
fix(api): sửa lỗi parse symbol
```

```txt
fix(crawler): sửa lỗi websocket reconnect
```

---

### Refactor

```txt
refactor(ml): tối ưu logic feature engineering
```

---

### Documentation

```txt
docs(readme): cập nhật hướng dẫn setup
```

---

### Test

```txt
test(api): thêm test cho prediction endpoint
```

---

# Quy Tắc Pull Request

Trước khi merge vào `develop`:

* tự review code
* xoá log debug
* đảm bảo project vẫn chạy
* viết tiêu đề PR rõ ràng

---

## Ví dụ tiêu đề PR tốt

```txt
Thêm realtime crawler cho Binance
```

```txt
Xây dựng model dự đoán XGBoost cơ bản
```

---

---

# Workflow Làm Việc Hằng Ngày

## Bắt đầu làm việc

```bash
git checkout develop

git pull origin develop

git checkout -b feature/new-feature
```

---

## Lưu thay đổi

```bash
git add .

git commit -m "feat(module): thêm chức năng mới"
```

---

## Push branch

```bash
git push origin feature/new-feature
```

---

## Merge branch

```txt
feature/*
→ develop
→ main
```


## Getting Started
```bash
pip install -r requirements.txt
