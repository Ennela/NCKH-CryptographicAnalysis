# Báo cáo thí nghiệm Issue #20: benchmark bốn mô hình trên ACB 1d

## 1. Phạm vi và mục tiêu

Báo cáo này ghi nhận benchmark chính thức giữa XGBoost, Random Forest, GRU và
ARIMA cho bài toán dự báo giá đóng cửa kế tiếp của cổ phiếu ACB. Mục tiêu là
so sánh bốn run trên cùng một holdout đã khóa, không phải chứng minh ưu thế
thống kê tổng quát của một mô hình.

Quy trình được thực hiện theo workflow `single-contributor`: cùng một người
triển khai evaluator, chạy pilot, kiểm tra artifact và ghi nhận bằng chứng.
Completion gate dựa trên test tự động, provenance của commit, manifest, artifact
reload, metric được tính lại độc lập và output xác định.

## 2. Benchmark contract

| Thuộc tính | Giá trị |
|---|---|
| Dataset version | `group_dataset_v1` |
| Snapshot | `ohlcv_full_current` |
| Symbol / timeframe | `ACB` / `1d` |
| Target / horizon | `next_close` / `1` |
| Split / seed | `test` / `42` |
| Số prediction | `78` |
| Canonical test manifest SHA-256 | `62d82e13b48f337623235e20c2412d435395fef46fea5a24776ea895d1c8b828` |
| Thời điểm evaluator | `2026-07-23T14:30:15Z` |
| Môi trường | Python 3.11.15, MLflow 2.11.3, NumPy 1.26.4, Pandas 2.3.3 |

Evaluator tải lại locked dataset bằng shared loader, tự tạo manifest và so sánh
đủ 78 dòng theo `input_ts`, `target_ts`, `current_close` và `actual_close`.
Không run nào được chọn theo “latest”, filesystem order hoặc registry stage.

## 3. Official runs và eligibility

| Model | MLflow run ID | Source commit | Artifact reload | Eligibility |
|---|---|---|---|---|
| XGBoost | `55ea7a8c7e3a49ed813ac6294fb26a80` | `e826aea5a06f4a2adb57f7aa3967cf03f3ce5471` | PASS | `valid` |
| Random Forest | `db37627439134d56a250c8b898969d77` | `e826aea5a06f4a2adb57f7aa3967cf03f3ce5471` | PASS | `valid` |
| GRU | `65f56eab440e4fa9a5192bfaddbcc96e` | `8a0d2dd3ec7a749aec2fedd8516e835390a9243d` | PASS | `valid` |
| ARIMA | `f1ef301caa064c858da753982f1564dc` | `ab1cf9af355211192c923c55aa042ff0413fdf6a` | PASS | `valid` |

XGBoost và Random Forest được chạy lại từ commit đã ghi nhận sau khi worktree
sạch. GRU và ARIMA được tái sử dụng vì live verification vẫn pass. ARIMA
registry version 3 vẫn ở `Production`, trạng thái `READY`; evaluator không thay
đổi registry.

Các candidate cũ không được dùng làm official evidence:

| Model | Run ID cũ | Kết quả |
|---|---|---|
| XGBoost | `ce44fb8c42f2440abc113d68f85ffeca` | Excluded: thiếu MLflow params `model` và `horizon` |
| Random Forest | `fc380e6d985e441684288738e5f277bb` | Excluded: live MLflow artifact tree không đầy đủ |

## 4. Validation liên mô hình

| Gate | Kết quả |
|---|---|
| Bốn run có trạng thái `FINISHED` | PASS |
| Required params và metrics | PASS |
| Prediction/summary exact schema | PASS |
| 78 prediction mỗi model | PASS |
| Canonical manifest hash | PASS |
| Cross-model row identity | PASS |
| Model-specific artifact reload | PASS |
| Metric recomputation với tolerance `1e-12` | PASS |
| Naive baseline identity | PASS |
| NaN / `+Inf` / `-Inf` | Không phát hiện |
| Exclusion trong bốn official run | Không có |

XGBoost được reload cùng StandardScaler và feature order. Random Forest được
reload cùng feature metadata. GRU được strict-load state dict, hai scaler và
architecture metadata. ARIMA được reload từ pre-test state có `nobs == 444`,
endogenous history dài 444 và không chứa test history.

## 5. Quy tắc xếp hạng

Thứ tự chính thức là:

1. RMSE tăng dần.
2. Nếu RMSE bằng nhau, MAE tăng dần.
3. Nếu RMSE và MAE bằng nhau, Directional Accuracy giảm dần.
4. Tên model tăng dần chỉ là fallback để output xác định khi mọi metric bằng
   nhau; đây không phải lợi thế thống kê.

Metric không được làm tròn trước validation hoặc ranking.

## 6. Kết quả chính thức

| Rank | Model | MAE | RMSE | MAPE % | Directional accuracy | Improvement vs Naive RMSE % |
|---:|---|---:|---:|---:|---:|---:|
| 1 | ARIMA | 0.27234869637307557 | 0.3882019113976774 | 1.3135850175231933 | 0.5128205128205128 | 0.5163771224311596 |
| 2 | Random Forest | 0.5256917774782239 | 0.6368350104288949 | 2.5733422799615013 | 0.38461538461538464 | -63.20026293698421 |
| 3 | XGBoost | 0.48262003678541876 | 0.6483500635961559 | 2.282851875973909 | 0.48717948717948717 | -66.15119948075981 |
| 4 | GRU | 0.5393094254762704 | 0.7360494889815756 | 2.534783277033477 | 0.47435897435897434 | -88.62573220578025 |

Canonical Naive baseline dùng `predicted_close = current_close`:

| Naive MAE | Naive RMSE | Naive MAPE % | Naive directional accuracy |
|---:|---:|---:|---:|
| 0.2669230769230771 | 0.3902169022085419 | 1.2888783803605892 | 0.10256410256410256 |

> **Lưu ý về Naive directional accuracy.** Naive dự báo
> `predicted_close = current_close`, nên `sign(predicted − current) = 0` theo
> định nghĩa; chỉ số này chỉ được tính "đúng" ở các phiên giá đóng cửa không
> đổi (8/78 phiên của holdout này). Giá trị `0.1026` vì vậy là hằng số tham
> chiếu sinh ra từ công thức đã khóa trong protocol, không mang cùng cách diễn
> giải "khả năng đoán hướng" như directional accuracy của model, và không nên
> được so sánh trực tiếp với DA của bốn model.

Theo primary metric RMSE, ARIMA đứng đầu và chỉ cải thiện
`0.5163771224311596%` so với Naive. Random Forest, XGBoost và GRU không vượt
Naive trên manifest này; improvement RMSE của cả ba đều âm. ARIMA cũng không
tốt hơn Naive theo MAE hoặc MAPE, vì vậy kết quả không nên được diễn giải rộng
hơn tiêu chí ranking và holdout đã định trước.

## 7. Bằng chứng và khả năng tái lập

Ba output được tạo atomically tại:

- `artifacts/benchmarks/ACB_1d/benchmark_overview.csv`
- `artifacts/benchmarks/ACB_1d/benchmark_report.md`
- `artifacts/benchmarks/ACB_1d/benchmark_audit.json`

Các output này được giữ trong local artifact store và MLflow, không force-add
vào Git. MLflow evaluator run cuối là
`f082a0252d7042f2a599b9554b2e68e0`; đây là evidence run, không phải prediction
model, không được register hoặc promote.

Lệnh tái lập:

```bash
python -m services.training.benchmark \
  --xgboost-run-id 55ea7a8c7e3a49ed813ac6294fb26a80 \
  --random-forest-run-id db37627439134d56a250c8b898969d77 \
  --gru-run-id 65f56eab440e4fa9a5192bfaddbcc96e \
  --arima-run-id f1ef301caa064c858da753982f1564dc \
  --output-dir artifacts/benchmarks/ACB_1d
```

Evaluator được chạy hai lần trên cùng source commit. Checksum của
`benchmark_overview.csv` giống hoàn toàn; checksum của Markdown và JSON cũng
giống sau khi chuẩn hóa duy nhất trường `generated_at`. Metric, eligibility,
ranking và toàn bộ nội dung cốt lõi không thay đổi.

## 8. Threats to validity

Mục này liệt kê các giới hạn ảnh hưởng trực tiếp đến cách diễn giải bảng xếp
hạng ở mục 6. Không mục nào dưới đây vi phạm quality gate của protocol; đây là
các ràng buộc phạm vi mà người đọc cần biết trước khi trích dẫn kết quả.

1. **XGBoost chỉ dùng một Optuna trial cố định theo seed.** Giá trị mặc định
   `--n-trials` là `1` (`services/training/train_xgboost.py`), nên bộ
   hyperparameters chính thức là một cấu hình được TPE sampler (seed 42) lấy
   mẫu duy nhất từ search space — không phải giá trị mặc định của thư viện,
   cũng không phải kết quả tuning đã hội tụ. Kết quả của XGBoost phản ánh
   "một cấu hình XGBoost cụ thể", không phản ánh năng lực tối đa của thuật
   toán.
2. **Random Forest không dùng validation để tuning.** Model dùng bộ
   hyperparameters cố định (`DEFAULT_RANDOM_FOREST_PARAMS`) và chỉ fit trên
   train; validation split được nạp nhưng không tham gia bất kỳ quyết định
   nào của pipeline.
3. **ARIMA dùng order cố định `(1, 1, 1)`,** không chọn order bằng AIC/BIC
   hoặc validation. Validation chỉ được dùng để lăn trạng thái (rolling
   state) tới biên test. ARIMA(1,1,1) trên chuỗi giá có hành vi gần
   random walk, nên kết quả bám sát Naive baseline là điều dự kiến được.
4. **Bốn model không dùng cùng feature representation.** XGBoost dùng 19
   feature kỹ thuật, Random Forest dùng 16 feature (gồm OHLCV thô), GRU chỉ
   dùng 2 feature (`close`, `moving_average_7`) dưới dạng sequence 30 bước,
   ARIMA là univariate trên `close`. Đây là lựa chọn chủ đích theo mô hình
   "mỗi thành viên sở hữu trọn một pipeline"; do đó benchmark so sánh các
   **pipeline hoàn chỉnh**, không so sánh các thuật toán trên cùng một input.
5. **ARIMA cập nhật trạng thái tuần tự trong test, khác cơ chế với ba model
   còn lại nhưng vẫn tuân thủ cùng giới hạn thông tin theo thời gian.** Sau
   mỗi bước dự báo, ARIMA append quan sát thực tế với `refit=False` (tham số
   giữ nguyên, chỉ trạng thái tiến lên). Ba model còn lại đóng băng tham số
   sau train/validation, nhưng feature và sequence tại mỗi thời điểm `t`
   cũng được tính từ giá thực tế `≤ t` của chuỗi liên tục. Mọi dự báo tại
   `t` của cả bốn model đều chỉ dùng thông tin có tại `t`; không model nào
   nhìn thấy tương lai. Khác biệt nằm ở cơ chế tiêu thụ lịch sử, không phải
   ở lượng thông tin.
6. **Kết quả chỉ dựa trên 78 mẫu test của một mã (ACB 1d) trong một giai
   đoạn thị trường.** Không có repeated sampling, không có kiểm định ý nghĩa
   thống kê. Chênh lệch nhỏ giữa các hạng liền kề (ví dụ RMSE 0.6368 của
   Random Forest so với 0.6484 của XGBoost) không nên được diễn giải thành
   ưu thế tổng quát của model này so với model kia; thứ hạng 2–4 nên được
   đọc là "không phân biệt được về mặt thống kê trên holdout này".

## 9. Hạn chế và kết luận

- Đây là một holdout duy nhất cho ACB 1d, không bao phủ asset, timeframe hoặc
  giai đoạn thị trường khác.
- Không có repeated sampling hay kiểm định ý nghĩa thống kê.
- Kết quả không chứng minh mô hình đứng đầu sẽ tốt nhất trong production.
- Source commit của hai run mới và evaluator đang ở feature branch; cần
  post-merge verification trên `develop` trước khi đóng Issue #20.

Tại thời điểm ghi báo cáo, bốn official run đều hợp lệ và benchmark sẵn sàng
cho PR review. Issue #20 vẫn để mở cho đến khi hoàn tất CI và post-merge
verification.
