# Dataset Snapshot

Dữ liệu chính của project nằm trong PostgreSQL/TimescaleDB. Các bảng dữ liệu thí
nghiệm đang được dùng cho training là:

- `market.exchange`
- `market.symbol`
- `market.ohlcv_raw`
- `market.ohlcv`

Thư mục `data/snapshots/` chỉ dùng để lưu snapshot local dạng `CSV.gz` khi cần
chia sẻ hoặc tái lập thí nghiệm. Các file snapshot thật không được commit vào
Git.

## Export Snapshot

Chạy khi Docker/Postgres đang hoạt động:

```bash
docker compose run --rm training python /app/scripts/export_dataset_snapshot.py --output-dir /app/data/snapshots
```

Export với tên cố định:

```bash
docker compose run --rm training python /app/scripts/export_dataset_snapshot.py --output-dir /app/data/snapshots --snapshot-name ohlcv_full_current
```

Mỗi snapshot có dạng:

```text
data/snapshots/ohlcv_full_current/
  manifest.json
  market_exchange.csv.gz
  market_symbol.csv.gz
  market_ohlcv.csv.gz
  market_ohlcv_raw.csv.gz
```

`manifest.json` ghi lại thời điểm export, số dòng từng bảng, khoảng thời gian
OHLCV, số symbol theo asset class, các timeframe có trong dataset, checksum
từng file snapshot, và snapshot fingerprint.

## Import Snapshot

Import mặc định dùng upsert, không xóa dữ liệu cũ:

```bash
docker compose run --rm training python /app/scripts/import_dataset_snapshot.py --snapshot-dir /app/data/snapshots/ohlcv_full_current
```

Nếu cần thay toàn bộ dữ liệu market trong DB dev/local, dùng `--replace`:

```bash
docker compose run --rm training python /app/scripts/import_dataset_snapshot.py --snapshot-dir /app/data/snapshots/ohlcv_full_current --replace
```

Cẩn thận với `--replace`: lệnh này truncate các bảng market dataset và cascade
tới các bảng phụ thuộc. Chỉ dùng trên database dev/local, không dùng trên DB
chung của nhóm nếu chưa thông báo.

## Git Policy

Repo chỉ commit script và tài liệu. Snapshot thật trong `data/snapshots/` bị
ignore bởi `.gitignore`. Nếu cần chia data cho thành viên khác, upload folder
snapshot lên Drive/OneDrive hoặc kênh chia sẻ ngoài Git.

## Shared Group Dataset

Cả nhóm dùng chung contract tại:

```text
configs/group_dataset.json
```

Contract này khóa:

- dataset version
- snapshot source name
- snapshot fingerprint (đã được nhóm trưởng khóa, xem mục "Checksum và
  Fingerprint" bên dưới)
- danh sách symbol stock/crypto
- timeframe được phép dùng
- start/end timestamp
- target mode và horizon
- train/validation/test split

## Quy tắc bắt buộc (từ 2026-07-08)

1. Mọi kết quả dùng để báo cáo PHẢI chạy qua `make train-official` hoặc
   `train.py` với contract mặc định. Không truyền `--dataset-config none`.
2. Kết quả chạy với `--allow-custom-data` KHÔNG được đưa vào bảng kết quả
   chính thức. Chỉ dùng cho debug hoặc explore.
3. Trước khi train, PHẢI chạy `make check-dataset`.
4. MLflow run hợp lệ phải có `dataset_version=group_dataset_v1` và
   `source_snapshot_name=ohlcv_full_current`.

Khi training, `train.py` mặc định đọc contract này:

```bash
docker compose run --rm training python train.py --ticker BTCUSDT --model xgboost --resolution 1d
```

Nếu DB của thành viên không khớp contract, training sẽ fail sớm thay vì âm thầm
dùng sai data.

Hiện có hai cách đọc dữ liệu training cần phân biệt:

- **Cách A — `train.py` (legacy, đọc DB):** đọc contract theo luồng đã mô tả ở
  trên và sử dụng dữ liệu trong DB local. Đường này được giữ lại cho tương
  thích; các entrypoint benchmark chính thức KHÔNG dùng đường này.
- **Cách B — entrypoint snapshot riêng của từng model (chuẩn benchmark):** cả
  bốn model đều đã có entrypoint độc lập đọc locked snapshot —
  `train_xgboost.py`, `train_random_forest.py`, `train_gru.py`,
  `train_arima.py` (thư mục `services/training/`). Mỗi entrypoint gọi
  `assert_locked_dataset()` rồi `load_full()` qua `shared/dataset/loader.py` để
  đọc trực tiếp locked snapshot tại
  `data/snapshots/<source_snapshot_name>/*.csv.gz`, không đọc dữ liệu training từ
  DB local. Chạy từ thư mục gốc của repo bằng lệnh (thay `train_xgboost` bằng
  entrypoint tương ứng):

  ```bash
  python -m services.training.train_xgboost --ticker <ticker> --timeframe <tf>
  python -m services.training.train_random_forest --ticker <ticker> --timeframe <tf>
  python -m services.training.train_gru --ticker <ticker> --timeframe <tf>
  python -m services.training.train_arima --ticker <ticker> --timeframe <tf>
  ```

Sau khi import snapshot, mỗi thành viên nên kiểm tra:

```bash
make check-dataset
```

Quy trình để cả nhóm dùng cùng data:

1. Nhóm trưởng export snapshot với tên trong contract:
   ```bash
   make export-snapshot SNAPSHOT_NAME=ohlcv_full_current
   ```
2. Upload folder `data/snapshots/ohlcv_full_current/` lên Drive/OneDrive.
3. Mỗi thành viên tải folder snapshot về đúng đường dẫn `data/snapshots/`.
4. Mỗi thành viên import vào DB local:
   ```bash
   docker compose run --rm training python /app/scripts/import_dataset_snapshot.py --snapshot-dir /app/data/snapshots/ohlcv_full_current --replace
   ```
5. Mỗi thành viên chạy check:
   ```bash
   make check-dataset
   ```

Chỉ bắt đầu training/report khi bước check pass.

## Checksum và Fingerprint

Mỗi snapshot export ra sẽ có:

- SHA256 checksum cho từng file `.csv.gz` trong `manifest.json`. Checksum này
  dùng để verify snapshot không bị sửa hoặc hỏng khi chia sẻ qua Drive/OneDrive.
- Snapshot fingerprint là SHA256 của canonical JSON manifest. Fingerprint này
  bỏ qua chính trường `snapshot_fingerprint`, sort key, và dùng compact
  separators để cùng nội dung manifest tạo cùng hash.

Lưu ý: checksum được tính trên file `.csv.gz` đã nén. Nếu export lại từ cùng DB,
file gzip có thể khác do metadata nén, nên checksum có thể khác. Mục đích
checksum là verify tính toàn vẹn của file snapshot đã chia sẻ, không phải verify
re-export deterministic.

`snapshot_fingerprint` trong `configs/group_dataset.json` **đã được khóa**
(trạng thái Phase 2). Giá trị hiện tại:

```text
381cd2ee9054a5728a694f6f1df7b952f70c2f40d8e0664c59e6414ff9c2d6d2
```

Trước đây (Phase 1) trường này để `null` trong khi chờ nhóm trưởng export
snapshot `ohlcv_full_current` chính thức. Từ khi contract được khóa (commit
`4b660b7`, 09/07/2026), mọi lần load qua `assert_locked_dataset()` sẽ so khớp
fingerprint của snapshot local với giá trị trên và fail sớm nếu lệch. KHÔNG tự
sửa giá trị này; nếu snapshot chính thức đổi, nhóm trưởng là người cập nhật
contract kèm thông báo cho cả nhóm.
