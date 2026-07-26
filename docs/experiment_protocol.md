# Shared Model Benchmark Protocol

## 1. Mục đích và phạm vi

Tài liệu này là protocol bắt buộc để so sánh công bằng bốn mô hình `xgboost`,
`random_forest`, `gru` và `arima`. Mọi kết quả trước khi tuân thủ đầy đủ
protocol chỉ được xem là `preliminary` và không được dùng để xếp hạng chính
thức.

Issue #15 chỉ khóa tài liệu. Issue này không sửa model, database, dependency,
dataset contract, API hoặc training/inference pipeline. Việc hiện thực hóa
schema đầu ra và test tương ứng thuộc các issue model tiếp theo.

## 2. Dataset protocol bắt buộc

Các giá trị sau được khóa cho toàn bộ benchmark:

| Thuộc tính | Giá trị khóa |
|---|---|
| Dataset version | `group_dataset_v1` |
| Snapshot | `ohlcv_full_current` |
| Target | `next_close` |
| Horizon | `1` |
| Split | Theo thời gian: train 70%, validation 15%, test 15% |
| Shuffle | Không |
| Pilot đầu tiên | `ACB`, timeframe `1d`, seed `42` |
| Pilot tiếp theo | `BTCUSDT`, timeframe `1h`, chỉ chạy sau khi ACB 1d hợp lệ |

Các split phải giữ nguyên thứ tự thời gian và không được look-ahead. Train dùng
để fit model, scaler và encoder. Validation chỉ dùng cho tuning, chọn cấu hình
và early stopping. Test chỉ được dùng một lần để đánh giá cuối sau khi toàn bộ
cấu hình đã được khóa; không được dùng kết quả test để điều chỉnh model rồi báo
cáo lại trên cùng test như một đánh giá độc lập.

Scaler hoặc encoder chỉ được fit trên train. Validation và test chỉ được
transform bằng đối tượng đã fit trên train.

### 2.1. Nguồn dữ liệu duy nhất

Mọi model phải import loader chung đúng từ module sau:

```python
from shared.dataset.loader import assert_locked_dataset, load_full
```

Trước khi tạo feature, train hoặc đánh giá, model phải gọi:

```python
assert_locked_dataset()
full_df = load_full(ticker, timeframe)
```

Không model nào được:

- đọc CSV dataset riêng;
- dùng `data_loader.py` riêng làm nguồn dataset benchmark;
- thay đổi dataset config trên model branch;
- tự chia train/validation/test bằng logic riêng;
- dùng snapshot khác `ohlcv_full_current`;
- tạo target khác `next_close` hoặc horizon khác `1`.

## 3. Test manifest chung

Mỗi run phải tạo hoặc sử dụng cùng một test manifest cho cùng `symbol` và
`timeframe`. Manifest là nguồn sự thật duy nhất cho thứ tự target,
`current_close` và `actual_close`. Bốn model phải dùng cùng số target và cùng
thứ tự target.

Manifest có chính xác các cột theo thứ tự:

```csv
dataset_version,snapshot_name,symbol,timeframe,split,input_ts,target_ts,current_close,actual_close
```

### 3.1. Quy tắc tạo và kiểm tra manifest

- `dataset_version` phải bằng `group_dataset_v1`.
- `snapshot_name` phải bằng `ohlcv_full_current`.
- `split` phải bằng `test` ở mọi dòng.
- `input_ts < target_ts` ở mọi dòng.
- Với horizon 1, `target_ts` là timestamp của quan sát kế tiếp có thật trong
  chuỗi thời gian đã khóa, không phải timestamp được suy ra bằng cách cộng một
  khoảng thời gian lịch.
- `current_close` là giá `close` tại `input_ts`.
- `actual_close` là giá `close` tại `target_ts` và là target `next_close` của
  dòng input.
- Mỗi dòng tương ứng đúng một target. Không được để target vượt qua biên split.
- Không được có `input_ts` trùng trong cột `input_ts` hoặc `target_ts` trùng
  trong cột `target_ts`. Việc `target_ts` của một dòng bằng `input_ts` của dòng
  kế tiếp là quan hệ horizon 1 bình thường, không phải duplicate target.
- Các dòng phải được sắp xếp tăng dần theo `target_ts`.
- Tất cả timestamp phải được chuyển sang UTC và serialize bằng ISO-8601.
- Mọi trường bắt buộc phải có giá trị; dữ liệu số không được chứa `NaN`, `Inf`
  hoặc `-Inf`.
- Bốn model phải đối chiếu manifest trước khi predict; không được cắt manifest
  theo model có ít prediction nhất.

## 4. `test_manifest_sha256`

Mỗi manifest phải có một `test_manifest_sha256`. Hash được tính từ dữ liệu
canonical đã sắp xếp, không tính từ index Pandas và không phụ thuộc BOM, kiểu
xuống dòng của hệ điều hành hoặc tùy chọn mặc định của thư viện ghi CSV.

Các cột tham gia hash, theo đúng thứ tự, là:

```csv
dataset_version,snapshot_name,symbol,timeframe,input_ts,target_ts,current_close,actual_close
```

Quy trình canonical bắt buộc:

1. Chọn đúng tám cột trên và sắp xếp tăng dần theo `target_ts`.
2. Kiểm tra lại tính duy nhất, thứ tự timestamp và mọi số đều finite.
3. Chuẩn hóa timestamp về UTC dạng `YYYY-MM-DDTHH:MM:SSZ`.
4. Serialize số thực bằng biểu diễn round-trip ổn định
   `format(value, ".17g")`; chuẩn hóa `-0` thành `0`.
5. Tạo luồng CSV canonical UTF-8 không BOM: có một dòng header đúng như trên,
   dùng dấu phẩy, không có Pandas index, không có khoảng trắng thừa và chỉ dùng
   ký tự xuống dòng LF (`\n`). Dòng cuối cũng kết thúc bằng LF.
6. Tính SHA-256 trên chính chuỗi byte canonical đó và lưu digest chữ thường
   gồm 64 ký tự hex vào `test_manifest_sha256`.

Không được hash trực tiếp file CSV do một model tự xuất vì file đó có thể khác
index, BOM hoặc newline dù dữ liệu logic giống nhau. Mọi run trên cùng manifest
phải log và xuất cùng một hash.

## 5. Prediction-level CSV chung

Mỗi run phải xuất một prediction-level CSV với chính xác các cột theo thứ tự:

```csv
dataset_version,snapshot_name,test_manifest_sha256,symbol,timeframe,model,split,input_ts,target_ts,current_close,actual_close,predicted_close,run_id,seed
```

Tên model chuẩn chỉ nhận một trong bốn giá trị:

- `xgboost`
- `random_forest`
- `gru`
- `arima`

Quy tắc bắt buộc:

- Một dòng tương ứng đúng một target trong test manifest.
- `dataset_version`, `snapshot_name`, `test_manifest_sha256`, `symbol`,
  `timeframe`, `split`, `run_id` và `seed` phải nhất quán trong toàn file.
- `split` của benchmark cuối phải bằng `test`.
- Thứ tự dòng phải giống chính xác thứ tự target trong manifest.
- Không thêm index Pandas vào CSV.
- File dùng UTF-8 và timestamp UTC ISO-8601.
- `actual_close`, `predicted_close` và `current_close` phải là số thực finite.
- Không được có cột `MSE` trong prediction CSV.
- `run_id` phải là MLflow run ID có thật của run tạo file.
- Không được ghi đè file của run trước.

File phải nằm dưới đường dẫn khớp mẫu:

```text
artifacts/predictions/{model}/{symbol}*{timeframe}*{run_id}.csv
```

Tên file chuẩn được khuyến nghị là
`{symbol}_{timeframe}_{run_id}.csv`, nhờ đó đường dẫn chứa đủ model, symbol,
timeframe và run ID để không ghi đè run cũ.

Prediction CSV là artifact sinh khi chạy, không phải dữ liệu nguồn để commit.
Nếu repository không cho phép commit artifact, model implementation PR phải
đảm bảo `artifacts/predictions/` nằm trong `.gitignore` trước khi sinh file.
Các PR đó chỉ commit code tạo file, cấu hình ignore cần thiết và test schema;
không commit CSV của run. Issue #15 không sửa `.gitignore` vì chỉ được sửa tài
liệu.

## 6. Metrics summary CSV chung

Mỗi run phải tạo một dòng metrics summary với chính xác schema:

```csv
dataset_version,snapshot_name,test_manifest_sha256,symbol,timeframe,model,split,n_samples,mae,rmse,mape_pct,directional_accuracy,naive_mae,naive_rmse,naive_mape_pct,naive_directional_accuracy,improvement_vs_naive_rmse_pct,run_id,seed,status
```

Quy tắc bắt buộc:

- `split` của benchmark cuối phải bằng `test`.
- `n_samples` phải bằng số dòng prediction và số target trong manifest.
- `mape_pct` và `naive_mape_pct` lưu theo phần trăm. Ví dụ `1.25` nghĩa là
  `1.25%`; không dùng tên `mape` khi đơn vị không rõ và không ghi ký tự `%`
  trong ô CSV.
- `directional_accuracy` và `naive_directional_accuracy` là tỷ lệ trong đoạn
  `[0, 1]`, không phải phần trăm.
- Tất cả metric phải được tính từ các vector float một chiều, cùng shape, cùng
  thứ tự manifest và chỉ chứa giá trị finite.
- Phải thỏa `rmse + 1e-12 >= mae` và
  `naive_rmse + 1e-12 >= naive_mae`; tolerance `1e-12` chỉ dành cho sai số số
  thực rất nhỏ.

Các metric chính được tính trên cùng `n_samples` target theo manifest:

```text
mae = mean(abs(actual_close - predicted_close))
rmse = sqrt(mean((actual_close - predicted_close) ** 2))
mape_pct = mean(abs((actual_close - predicted_close) / actual_close)) * 100
```

Các Naive metric dùng cùng công thức, chỉ thay `predicted_close` bằng
`naive_predicted_close`. Không được loại riêng một số target khi tính một
metric; nếu có target làm metric không xác định thì toàn run là `invalid`.

Naive prediction cho horizon 1 được khóa là:

```text
naive_predicted_close = current_close
```

Direction của model được tính bằng cách so sánh:

```text
sign(predicted_close - current_close)
```

với:

```text
sign(actual_close - current_close)
```

Naive Directional Accuracy áp dụng cùng công thức với
`predicted_close = current_close`. Mọi model trên cùng manifest phải có các
naive metric giống nhau.

Mức cải thiện RMSE so với Naive được tính theo phần trăm:

```text
improvement_vs_naive_rmse_pct =
    (naive_rmse - rmse) / naive_rmse * 100
```

Nếu không thể tính metric hữu hạn, kể cả khi mẫu số MAPE hoặc Naive RMSE bằng
0, run phải là `invalid`; không được thay bằng `NaN`, `Inf` hoặc giá trị giả.

`status` chỉ nhận:

- `valid`: vượt qua toàn bộ quality gate và được phép xếp hạng;
- `invalid`: vi phạm ít nhất một quality gate;
- `preliminary`: run thử chưa được trình để đánh giá cuối, không được xếp hạng.

Run chỉ được đổi sang `valid` sau khi toàn bộ bằng chứng và quality gate đã
được kiểm tra.

## 7. Benchmark overview CSV

Benchmark overview dùng chính xác schema:

```csv
rank,dataset_version,snapshot_name,test_manifest_sha256,symbol,timeframe,model,n_samples,mae,rmse,mape_pct,directional_accuracy,naive_mae,naive_rmse,naive_mape_pct,improvement_vs_naive_rmse_pct,run_id,seed,status
```

Chỉ run `valid` mới có `rank`. Run `invalid` hoặc `preliminary`, nếu được giữ
trong overview để audit, phải để `rank` trống và không được xen vào bảng xếp
hạng chính thức.

Trong cùng dataset version, snapshot, manifest, symbol và timeframe, thứ tự
xếp hạng là:

1. RMSE tăng dần.
2. MAE tăng dần nếu RMSE bằng nhau.
3. Directional Accuracy giảm dần nếu RMSE và MAE vẫn bằng nhau.

## 8. Quality gates

Một model phải được đánh dấu `invalid` nếu xảy ra bất kỳ điều nào sau đây:

1. Không dùng locked dataset qua `assert_locked_dataset()` và `load_full()`.
2. Dataset version, snapshot, target, horizon hoặc split khác protocol.
3. Manifest hash khác model khác trên cùng benchmark.
4. Số prediction khác số target test.
5. Timestamp lệch, off-by-one hoặc không đúng target kế tiếp của horizon 1.
6. Có duplicate `target_ts` hoặc thứ tự target khác manifest.
7. Có giá trị thiếu, `NaN`, `Inf` hoặc `-Inf`.
8. `y_true` và `y_pred` khác shape, không phải vector một chiều hoặc bị
   broadcasting ngầm.
9. `RMSE < MAE` ngoài tolerance số thực đã khóa.
10. Test được dùng để tuning, early stopping, chọn hyperparameter hoặc lựa chọn
    model.
11. Scaler hoặc encoder được fit trên validation/test.
12. Inverse-transform sai hoặc được áp dụng nhiều hơn một lần.
13. Naive metrics không giống các model khác trên cùng manifest.
14. Thiếu MLflow run ID hợp lệ hoặc run ID không truy vết đúng artifact.
15. Không có command tái lập đầy đủ từ thư mục gốc repository.
16. Không có test output chứng minh schema, alignment và kiểm tra finite.
17. Prediction CSV hoặc metrics CSV sai schema, sai thứ tự cột hoặc ghi đè run
    trước.

Quality gate phải được kiểm tra trước khi tạo hoặc cập nhật rank. Không được
loại im lặng dòng lỗi để làm run hợp lệ.

## 9. Thứ tự benchmark

### Giai đoạn A — ACB 1d

1. Dùng `group_dataset_v1`, snapshot `ohlcv_full_current`, target `next_close`,
   horizon 1 và seed 42.
2. Khóa test manifest và `test_manifest_sha256`.
3. Chạy đủ `xgboost`, `random_forest`, `gru` và `arima` trên cùng manifest.
4. Kiểm tra toàn bộ quality gate, đặc biệt alignment timestamp, số target và
   Naive metrics.
5. Chỉ đánh dấu pilot ACB 1d hợp lệ khi cả bốn run đều `valid`.

### Giai đoạn B — BTCUSDT 1h

Chỉ bắt đầu `BTCUSDT 1h` sau khi pilot `ACB 1d` hợp lệ. Quy trình manifest,
hash, prediction, metric và quality gate phải được lặp lại không thay đổi.

## 10. Bằng chứng bắt buộc cho mỗi run

Mỗi chủ model phải cung cấp:

- command tái lập chạy từ thư mục gốc repository;
- dataset version, snapshot name và `test_manifest_sha256`;
- prediction CSV đúng schema;
- metrics summary CSV đúng schema;
- MLflow run ID;
- seed;
- test output liên quan;
- giải thích ngắn về scaler, inverse-transform và cách bảo đảm không
  look-ahead.

Ảnh chụp màn hình chỉ có giá trị minh họa, không thay thế CSV, MLflow run ID,
command hoặc test output.

## 11. Ownership, review và kiểm tra issue #15

Tài liệu và protocol dùng chung cần toàn bộ nhóm modeling review:

- Nguyễn Văn Kiên — XGBoost;
- Lê Hải Nam — Random Forest;
- Nguyễn Trọng Đại — GRU;
- Đỗ Quang Hà — ARIMA.

Trước khi bàn giao issue #15:

```bash
git diff --check
```

Sau đó review Markdown thủ công và xác nhận diff chỉ chứa tài liệu. Metadata PR
được khóa như sau:

- Commit: `docs: define shared model benchmark protocol`
- PR title: `docs: define shared model benchmark protocol`
- PR body phải có `Closes #15`.
- Tag toàn bộ nhóm modeling review.
