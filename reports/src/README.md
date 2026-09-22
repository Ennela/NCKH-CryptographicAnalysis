# Nguồn sinh báo cáo tiến độ

Toàn bộ hình vẽ, bảng số liệu và tệp DOCX trong `reports/` được **sinh ra từ mã**, không
soạn tay. Khi thiết kế hệ thống hoặc kết quả thí nghiệm thay đổi, chạy lại các lệnh dưới
đây là báo cáo tự cập nhật — không phải sửa từng hình, từng bảng.

## Thành phần

| Tệp | Sinh ra gì |
|---|---|
| `diagrams.py` | 7 sơ đồ thiết kế (kiến trúc, đường ống dữ liệu, ERD, tuần tự, ca sử dụng, CI/CD, vòng đời mô hình) |
| `make_chart.py` | Biểu đồ so sánh RMSE của bốn mô hình với baseline Naive |
| `capture.py` | Ảnh chụp giao diện web, Swagger và MLflow từ hệ thống đang chạy |
| `make_xlsx.py` | Bảng kết quả Excel 4 sheet (`reports/Ket_qua_benchmark_*.xlsx`) |
| `report_data.py` + `report_part2.py` | Nội dung báo cáo → `report.json` |
| `build_docx.js` | `report.json` + hình → tệp `.docx` |
| `all_results.csv` | Chỉ số của 36 MLflow run, tổng hợp từ `artifacts/metrics/` (thư mục này nằm trong `.gitignore`) |

## Yêu cầu

```bash
pip install pandas matplotlib openpyxl pillow playwright
npm install docx
```

## Quy trình sinh lại

```bash
cd reports/src
mkdir -p fig shots
python diagrams.py fig          # 7 sơ đồ
python make_chart.py .          # biểu đồ kết quả; cần all_results.csv
cp chart_rmse_ratio.png fig/
python make_xlsx.py .           # bảng Excel
python report_data.py .         # -> report.json
node build_docx.js              # -> .docx
```

### Chụp lại ảnh giao diện

Cần hệ thống đang chạy (`docker compose up -d`). `capture.py` điều khiển một trình duyệt
qua giao thức CDP thay vì tự tải trình duyệt riêng — cách này chạy được cả khi mạng
không tải nổi bản Chromium của Playwright:

```bash
# Mở một trình duyệt Chromium/Edge ở chế độ headless kèm cổng gỡ lỗi
"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" --headless=new \
    --remote-debugging-port=9222 --user-data-dir=/tmp/edgeprof about:blank &

python capture.py shots
```

Ảnh được dùng trong báo cáo cũng được lưu ở `docs/evidence/screenshots/` để làm minh
chứng độc lập với tệp DOCX.

## Cập nhật số liệu thí nghiệm

`all_results.csv` gộp từ các tệp `artifacts/metrics/<mô hình>/<mã>_<khung>_<run_id>.csv`
do bốn entrypoint huấn luyện sinh ra. Sau khi chạy thêm thí nghiệm, gộp lại rồi chạy lại
`report_data.py` — các bảng trong Chương 8 và Phụ lục A sẽ tự cập nhật theo.

## Lưu ý

- Mục lục trong DOCX là trường động. Mở bằng Word rồi cập nhật trường (hoặc dùng
  `TablesOfContents(1).Update()`) để hiện số trang.
- Phông chữ trong sơ đồ được phóng theo hệ số `FS` ở đầu `diagrams.py`, vì hình bị thu nhỏ
  khi đưa vào khổ A4.
