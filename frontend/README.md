# Forecast Frontend Dashboard

Giao diện trực quan hóa thông tin và dự báo giá cổ phiếu & tiền số của dự án.

## Công nghệ sử dụng
- **Core**: Next.js 14 (App Router) + TypeScript
- **Styling**: Tailwind CSS + PostCSS
- **Visualizations**: Apache ECharts (`echarts`, `echarts-for-react`)
- **Icons**: Lucide React

## Cấu trúc thư mục
- `/app`: Các trang của ứng dụng (layouts, styles, pages).
  - `/forecast`: Trang hiển thị dự báo giá.
  - `/explainability`: Trang phân tích mức độ ảnh hưởng của đặc trưng (SHAP/feature importance).
  - `/symbols`: Trang quản lý và xem thông tin chi tiết từng mã tài sản.
- `/components`: Các UI component dùng chung.
- `next.config.js`: Cấu hình Next.js (bao gồm cấu hình proxy API lên backend).

## Hướng dẫn cài đặt & chạy ứng dụng

### 1. Chuẩn bị biến môi trường
Sao chép file cấu hình mẫu:
```bash
cp .env.local.example .env.local
```
Sau đó chỉnh sửa `.env.local`:
- `NEXT_PUBLIC_API_URL`: base URL của Inference Service (mặc định `http://localhost:8000`, KHÔNG kèm hậu tố `/api/v1`).
- `NEXT_PUBLIC_API_KEY`: API key gửi qua header `X-API-Key`, phải khớp với key cấu hình ở inference service.

### 2. Cài đặt thư viện
Chạy lệnh sau tại thư mục `frontend/` để cài đặt dependencies:
```bash
npm install
```

### 3. Chạy môi trường phát triển (Dev)
```bash
npm run dev
```
Giao diện sẽ khởi chạy tại [http://localhost:3000](http://localhost:3000).

### 4. Build dự án sản xuất (Production Build)
```bash
npm run build
npm run start
```

### 5. Linting
Kiểm tra và sửa lỗi format/styles:
```bash
npm run lint
```
