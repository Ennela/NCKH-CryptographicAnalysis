# RULES.md — Quy tắc làm việc & dùng AI Agent cho dự án

> Mọi thành viên VÀ mọi AI agent (Cursor/Claude/Copilot...) PHẢI đọc và tuân thủ file này
> trước khi viết bất kỳ dòng code nào. Nếu một yêu cầu mâu thuẫn với file này, DỪNG LẠI và hỏi.

---

## 0. Bối cảnh dự án (đọc để có ngữ cảnh)
- Hệ thống thu thập, phân tích & DỰ BÁO giá cổ phiếu VN (vnstock) và crypto (Binance).
- Đồ án nghiên cứu khoa học, 6 tháng, nhóm 5 người, theo Agile + Machine Learning.
- Đây là dự án HỌC THUẬT: ưu tiên code DỄ HIỂU, GIẢI THÍCH ĐƯỢC, TÁI LẬP ĐƯỢC hơn là "code cho nhanh".

---

## 1. Quy tắc VÀNG khi dùng AI Agent
1. **Đọc trước, viết sau.** Trước khi sinh code, agent phải đọc: file này, `docs/api.md`,
   `docs/architecture.md`, và các file liên quan trong thư mục đang sửa. KHÔNG đoán cấu trúc.
2. **Lên kế hoạch trước khi code.** Với task lớn, agent phải trình bày kế hoạch (các file sẽ sửa,
   cách tiếp cận) và CHỜ người xác nhận, rồi mới code.
3. **Phạm vi nhỏ.** Mỗi lần chỉ làm 1 task ứng với 1 issue trên board. KHÔNG tự ý sửa file ngoài phạm vi.
4. **Người luôn review.** KHÔNG merge code do AI sinh mà chưa đọc hiểu. "Tôi không hiểu đoạn này"
   = chưa được merge. Người chịu trách nhiệm là người ký PR, không phải AI.
5. **Không tự ý đổi kiến trúc / stack / schema DB.** Mọi thay đổi lớn phải mở thảo luận với cả nhóm.
6. **Không tự cài thêm thư viện nặng** chỉ để giải quyết việc nhỏ. Hỏi trước khi thêm dependency.
7. **Không tạo "magic".** Code phải tường minh; tránh viết tắt khó hiểu, tránh trừu tượng hóa quá sớm.

## 2. Điều TUYỆT ĐỐI KHÔNG làm với agent
- ❌ Dán nguyên khối code rồi merge mà không test.
- ❌ Yêu cầu agent "sửa cho hết lỗi" một cách mù quáng đến khi chạy được mà không hiểu vì sao.
- ❌ Để agent xóa/sửa file của thành viên khác ngoài phạm vi task.
- ❌ Commit secret, API key, file `.env` thật, dữ liệu lớn vào repo.
- ❌ Copy code trực tiếp từ repo tham khảo (ML for Trading) — xem mục 7.

---

## 3. Stack công nghệ (CHỐT — không tự đổi)
- Backend: Python 3.11 + FastAPI (đa service: ingestion / training / inference).
- Deep learning: **CHỈ DÙNG PyTorch.** KHÔNG trộn TensorFlow/Keras vào repo.
- ML cổ điển: scikit-learn, statsmodels (ARIMA), XGBoost (baseline mạnh + SHAP).
- Tuning: Optuna. Theo dõi thí nghiệm: MLflow.
- DB: PostgreSQL + TimescaleDB (OHLCV là hypertable). ORM: SQLAlchemy 2.x + Alembic.
- Queue: Celery + Redis. Frontend: Next.js (TypeScript) + ECharts.
- Config: pydantic-settings đọc từ `.env`. DevOps: Docker + Docker Compose + GitHub Actions + Sentry.

> Lý do khóa 1 framework DL: thống nhất kỹ năng, dễ review, tránh trộn môi trường,
> và tránh copy code từ repo tham khảo (vốn dùng Keras).

---

## 4. Ai sở hữu thư mục nào (sửa đúng đất của mình)
- TV1 (Data/Lead/DevOps): `services/ingestion/`, `infra/`, `.github/workflows/`
- TV2 (Modeling):          `services/training/app/models/`
- TV3 (Feature/Inference): `services/training/app/features/`, `services/inference/`
- TV4 (Frontend):          `frontend/`
- TV5 (QA/Docs):           `tests/` (mọi service), `docs/`
Sửa code ngoài thư mục mình sở hữu → phải mở PR và tag người sở hữu review.

---

## 5. Quy tắc code (style & chất lượng)
- Format & lint: `ruff` (Python), `eslint + prettier` (frontend). PR không pass lint = không merge.
- Bắt buộc **type hint** cho mọi hàm Python; dùng `pydantic` cho dữ liệu vào/ra.
- Đặt tên rõ nghĩa, tiếng Anh; hàm < ~50 dòng; tách hàm khi quá dài.
- Mọi I/O ra ngoài (API, DB, file) phải có xử lý lỗi + log có cấu trúc.
- KHÔNG hardcode: symbol, đường dẫn, secret, hyperparameter → đưa vào config/`.env`.
- Mỗi hàm phức tạp có docstring ngắn nói RÕ: làm gì, input, output.

## 6. Quy tắc dành riêng cho phần ML (rất quan trọng cho điểm)
- **Không rò rỉ dữ liệu (no look-ahead):** chia dữ liệu theo THỜI GIAN, không xáo trộn.
- **Scaler/encoder chỉ fit trên tập train**, sau đó transform valid/test.
- **Cố định random seed** (numpy, torch, random) ở đầu mọi script train để tái lập.
- **Mọi thí nghiệm phải log vào MLflow**: params, metrics (MAE/RMSE/MAPE), artifact model.
- Mọi mô hình mới phải so với **baseline Naive** — không có baseline thì kết quả vô nghĩa.
- Lưu kết quả ra bảng/CSV để đưa vào báo cáo; không để kết quả "bay" trong notebook.

## 7. Chống đạo văn (học thuật)
- ĐƯỢC tham khảo Ý TƯỞNG & PHƯƠNG PHÁP từ repo ML for Trading và nguồn ngoài.
- KHÔNG copy code nguyên khối. Phải đọc hiểu → tự viết lại bằng PyTorch + dữ liệu của nhóm.
- Mọi ý tưởng/đoạn tham khảo phải GHI NGUỒN trong `docs/` và trong báo cáo (Chương 2 + Tham khảo).
- Code do AI sinh cũng phải được người hiểu và chịu trách nhiệm — không "đổ cho AI".

---

## 8. Quy tắc Git
- Nhánh: `main` (ổn định) ← `develop` (tích hợp) ← `feature/<ten-task>`.
- KHÔNG push thẳng vào `main` hoặc `develop`. Mọi thay đổi qua Pull Request.
- PR phải được **≥ 1 thành viên khác review & duyệt** mới merge.
- Commit theo Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.
- PR nhỏ, tập trung 1 task; mô tả PR nêu rõ: làm gì, vì sao, đã test thế nào.

## 9. Definition of Done (1 task chỉ "xong" khi đủ 4)
- [ ] Code chạy được, đã merge vào `develop`.
- [ ] Có test cơ bản (hoặc đã kiểm thử thủ công có ghi lại).
- [ ] Đã cập nhật tài liệu / `docs` nếu thay đổi hành vi hệ thống.
- [ ] Demo được trong sprint review.

## 10. Bảo mật
- API key/secret chỉ đặt trong `.env` (đã có trong `.gitignore`). `.env.example` chỉ chứa tên biến.
- API nội bộ phải có: API key, rate limit, validate input (whitelist symbol, kiểm kiểu dữ liệu).
- Không log secret. Không đẩy dữ liệu nhạy cảm / dataset lớn lên Git (dùng `scripts/` để tải lại).

---

## 11. Mẫu prompt CHUẨN khi nhờ agent (copy & điền vào)
  Ngữ cảnh: [task này thuộc service nào, liên quan file nào]
  Yêu cầu: [mô tả 1 việc cụ thể, nhỏ]
  Ràng buộc: tuân thủ RULES.md (PyTorch, không look-ahead, có type hint, log MLflow...)
  Trước khi code: đọc [các file liên quan] và trình bày kế hoạch ngắn, chờ tôi duyệt.
  Sau khi code: liệt kê file đã sửa + cách test.

> Nguyên tắc cuối: AI là TRỢ LÝ, không phải người chịu trách nhiệm. Người mở PR chịu trách nhiệm
> cho từng dòng code trong đó — kể cả dòng do AI viết.