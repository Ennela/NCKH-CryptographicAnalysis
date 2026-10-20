// Build "Cap_nhat_bao_cao_2026-10-10.docx": every change the progress report
// needs after the V2 edition (22/09/2026), with replacement tables and figures.
// Numbers come from reports/TONG_HOP_SO_LIEU_CUOI_KY.md and reports/ch6_kiem_thu.md,
// which cite their sources. Run from the repo root:
//   node reports/src/build_update_docx.js
const fs = require("fs");
const path = require("path");
const {
  AlignmentType, BorderStyle, Document, Footer, HeadingLevel, ImageRun, LevelFormat,
  Packer, PageNumber, Paragraph, ShadingType, Table, TableCell, TableRow, TextRun, WidthType,
} = require("docx");

const ROOT = path.resolve(__dirname, "..", "..");
const OUT = path.join(ROOT, "reports", "Cap_nhat_bao_cao_2026-10-10.docx");
const F = "Calibri";
const NAVY = "1F3864";
const GREY = "595959";
const PAGE_W = 11906 - 2 * 1134; // A4 width minus 2 cm margins (DXA)
const border = { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" };
const borders = { top: border, bottom: border, left: border, right: border };

const body = [];

// "**bold**" and "`code`" inline markup -> TextRuns.
function runs(text, opts = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), font: F, size: opts.size || 22, ...opts.run }));
    const tok = m[0];
    if (tok.startsWith("**")) out.push(new TextRun({ text: tok.slice(2, -2), bold: true, font: F, size: opts.size || 22, ...opts.run }));
    else out.push(new TextRun({ text: tok.slice(1, -1), font: "Consolas", size: (opts.size || 22) - 2, ...opts.run }));
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), font: F, size: opts.size || 22, ...opts.run }));
  return out;
}

const h1 = (t) => body.push(new Paragraph({ heading: HeadingLevel.HEADING_1, keepNext: true, spacing: { before: 320, after: 140 }, children: [new TextRun({ text: t, font: F })] }));
const h2 = (t) => body.push(new Paragraph({ heading: HeadingLevel.HEADING_2, keepNext: true, spacing: { before: 220, after: 100 }, children: [new TextRun({ text: t, font: F })] }));
const p = (t) => body.push(new Paragraph({ spacing: { after: 100, line: 300 }, alignment: AlignmentType.LEFT, children: runs(t) }));
const bullets = (items) => items.forEach((t) => body.push(new Paragraph({ numbering: { reference: "bul", level: 0 }, spacing: { after: 60, line: 290 }, children: runs(t) })));
const caption = (t) => body.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 200 }, children: [new TextRun({ text: t, italics: true, size: 19, color: GREY, font: F })] }));

// Callout box used for "where in the report" instructions.
function where(t) {
  body.push(new Paragraph({
    spacing: { before: 80, after: 120 },
    shading: { type: ShadingType.CLEAR, fill: "EEF3FA" },
    border: { left: { style: BorderStyle.SINGLE, size: 18, color: "2E5597", space: 8 } },
    children: runs(t, { size: 21 }),
  }));
}

function table(head, rows, pct, cap) {
  const widths = pct.map((x) => Math.round((PAGE_W * x) / 100));
  widths[widths.length - 1] = PAGE_W - widths.slice(0, -1).reduce((a, b) => a + b, 0);
  const cell = (txt, i, isHead, fill) => new TableCell({
    borders,
    width: { size: widths[i], type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, fill: isHead ? NAVY : fill || "FFFFFF" },
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    children: [new Paragraph({ children: isHead ? [new TextRun({ text: txt, bold: true, color: "FFFFFF", font: F, size: 19 })] : runs(String(txt), { size: 19 }) })],
  });
  const trs = [new TableRow({ tableHeader: true, children: head.map((h, i) => cell(h, i, true)) })];
  rows.forEach((r) => {
    const fill = Array.isArray(r) ? undefined : r.fill;
    const cols = r.c || r;
    trs.push(new TableRow({ children: cols.map((c, i) => cell(c, i, false, fill)) }));
  });
  body.push(new Table({ width: { size: PAGE_W, type: WidthType.DXA }, columnWidths: widths, rows: trs }));
  if (cap) caption(cap);
  else body.push(new Paragraph({ spacing: { after: 120 }, children: [] }));
}

function img(rel, cap, widthPx = 640) {
  const file = path.join(ROOT, rel);
  const buf = fs.readFileSync(file);
  const w = buf.readUInt32BE(16);
  const h = buf.readUInt32BE(20);
  body.push(new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 120 },
    children: [new ImageRun({ type: "png", data: buf, transformation: { width: widthPx, height: Math.round((widthPx * h) / w) }, altText: { title: cap, description: cap, name: path.basename(rel) } })],
  }));
  caption(cap);
}

const CHANGED = { fill: "FDF3E3" };

// ── Cover ────────────────────────────────────────────────────────────
body.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 600, after: 120 }, children: [new TextRun({ text: "ĐỀ TÀI NGHIÊN CỨU KHOA HỌC SINH VIÊN", font: F, size: 22, color: GREY })] }));
body.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 }, children: [new TextRun({ text: "CẬP NHẬT BÁO CÁO TIẾN ĐỘ", bold: true, font: F, size: 40, color: NAVY })] }));
body.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 400 }, children: [new TextRun({ text: "Các thay đổi cần đưa vào báo cáo so với bản V2 (22/09/2026)", font: F, size: 26, color: NAVY })] }));
table(["Mục", "Nội dung"], [
  ["Đề tài", "Hệ thống thu thập, phân tích trực quan và dự báo giá cổ phiếu Việt Nam & tiền mã hóa"],
  ["Số liệu chốt ngày", "10/10/2026"],
  ["Phiên bản mã nguồn", "Nhánh `develop` commit `9e78554` (60 Pull Request đã hợp nhất) + PR #70 (sửa hình vẽ, biểu đồ lớp)"],
  ["Cách soạn", "Soạn với trợ giúp của AI agent. Mọi con số đã được đối chiếu trực tiếp với hệ thống đang chạy, MLflow, cơ sở dữ liệu và GitHub; chỗ nào chưa đo được thì ghi rõ là chưa đo."],
], [26, 74]);

// ── 1. How to use ────────────────────────────────────────────────────
h1("1. Cách dùng tài liệu này");
p("Tài liệu không thay bản báo cáo mà liệt kê **từng chỗ cần sửa** trong bản V2. Mỗi mục ghi vị trí trong bản V2, loại thay đổi (THAY, SỬA hoặc THÊM) và nội dung dùng được ngay. Số hình, số bảng theo bản V2; nếu bản đang chỉnh sửa đã đánh số lại thì đối chiếu theo tên hình, tên bảng. Các ô tô màu cam trong bảng là dòng có thay đổi.");
table(["#", "Vị trí trong bản V2", "Loại", "Tóm tắt thay đổi", "Mục"], [
  ["1", "Hình 2.1, 3.1, 3.2, 3.3, 3.4, 5.1, 6.1", "THAY", "Sửa chữ chồng/cắt và các chỗ ghi sai so với hệ thống hiện tại", "§2"],
  ["2", "Sau Hình 3.5 (mục Thiết kế)", "THÊM", "Hình 3.6, 3.7: biểu đồ lớp UML", "§2.3"],
  ["3", "Bảng 1.1", "THAY", "Quy mô hệ thống tại 10/10/2026", "§3.1"],
  ["4", "Bảng 2.1", "SỬA", "FR-01, FR-12, FR-13, FR-15", "§3.2"],
  ["5", "Bảng 2.2", "SỬA", "NFR-01, NFR-06, NFR-07, NFR-08", "§3.3"],
  ["6", "Bảng 3.5", "THAY", "Năm màn hình đã hoàn thành", "§3.4"],
  ["7", "Hình 4.3", "THAY + THÊM", "Trang giải thích cho cả 4 mô hình", "§4"],
  ["8", "Chương 8 (mục mới)", "THÊM", "Giải thích mô hình (XAI) cho 4 mô hình", "§4"],
  ["9", "Chương 6", "SỬA + THÊM", "Bảng 6.1, độ trễ API (p95), tỷ lệ job thành công (NFR-08), hai lỗi đã sửa", "§5"],
  ["10", "Chương 8", "SỬA + THÊM", "So sánh với Naive cập nhật; thí nghiệm ablation", "§6"],
  ["11", "Chương 7", "SỬA", "Số liệu sprint 9 (chốt) và sprint 10 (đang chạy)", "§7"],
  ["12", "Bảng 9.2, mục 9.3", "THAY", "Đối chiếu tiêu chí nghiệm thu; danh sách hạn chế", "§8"],
], [5, 27, 12, 46, 10]);

// ── 2. Figures ───────────────────────────────────────────────────────
h1("2. Hình vẽ thiết kế");
h2("2.1. Các lỗi đã sửa");
p("Bảy hình trong bản V2 có hai loại lỗi: chữ bị chồng hoặc bị cắt (khó đọc khi in), và nội dung không còn đúng với hệ thống hiện tại. Toàn bộ hình được sinh lại từ mã nguồn (`reports/src/diagrams.py`), không vẽ tay.");
table(["Hình", "Lỗi trong bản V2", "Đã sửa"], [
  ["2.1 Ca sử dụng", "Ca \"Xem log & trạng thái hệ thống\" vẽ nét đứt (chưa làm); ca giải thích chỉ ghi SHAP", "Ca nhật ký job đã hiện thực (màn hình Thu thập & Làm sạch); giải thích đủ 4 mô hình"],
  ["3.1 Kiến trúc", "Nhãn \"Docker Compose — mạng nội bộ\" đè lên ô Ingestion API; Inference ghi \"5 endpoint\"", "Chuyển nhãn xuống góc dưới; Inference có 10 endpoint"],
  ["3.2 Đường ống dữ liệu", "Số đặc trưng \"19 / 16 / 8\"; nhãn \"khóa dữ liệu\" lệch xa; chữ ô evaluator chạm mép", "XGBoost 19 · RF 18 · GRU 8 · ARIMA 1 biến (khớp tham số log trong MLflow); căn lại nhãn và chữ"],
  ["3.3 ERD", "Dòng cuối mỗi bảng bị viền cắt; ô ghi chú tràn khung; schema ops vẽ nét đứt", "Giãn dòng; ô ghi chú vừa chữ; ops.job_log và ops.data_quality_check vẽ viền liền vì đang được ghi"],
  ["3.4 Tuần tự /predict", "\"Đo khi demo 0,3–0,5 s\"; \"models:/ACB_1d_gru/1\"; rate limit mô tả theo cơ chế cũ", "Số đo ngày 07/10 (p95 ≤ 0,68 s); nạp phiên bản mới nhất; INCR theo từng phút"],
  ["5.1 Vòng đời mô hình", "Ghi \"hệ thống không bao giờ tự chọn bản mới nhất trong Registry\" — **sai**: `ModelLoader.latest_version` chọn version lớn nhất", "Ghi thành hạn chế: cổng kiểm định chưa tự động quyết định phiên bản được phục vụ; evaluator chỉ áp dụng ACB 1d"],
  ["6.1 Cổng chất lượng", "Nhãn GitHub Actions đè lên ô đầu và dòng phụ đề; ghi \"chỉ merge khi 4 job xanh + ≥ 1 review\"", "Căn lại bố cục; ghi rõ là **quy định**, vì nhánh develop chưa bật branch protection"],
], [20, 42, 38]);

h2("2.2. Các hình đã sinh lại");
where("**THAY** từng hình trong bản V2 bằng hình tương ứng dưới đây (cùng số hình).");
img("reports/figures/d5_use_case.png", "Hình 2.1 — Biểu đồ ca sử dụng (bản sửa).");
img("reports/figures/d1_kien_truc.png", "Hình 3.1 — Kiến trúc triển khai hệ thống (bản sửa).");
img("reports/figures/d2_duong_ong.png", "Hình 3.2 — Đường ống dữ liệu từ nguồn đến màn hình người dùng (bản sửa).");
img("reports/figures/d3_erd.png", "Hình 3.3 — Sơ đồ quan hệ thực thể (bản sửa).");
img("reports/figures/d4_tuan_tu.png", "Hình 3.4 — Biểu đồ tuần tự POST /api/v1/predict (bản sửa).");
img("reports/figures/d7_vong_doi_model.png", "Hình 5.1 — Vòng đời một mô hình trong hệ thống (bản sửa).");
img("reports/figures/d6_cicd.png", "Hình 6.1 — Cổng chất lượng từ máy lập trình viên tới nhánh develop (bản sửa).");

h2("2.3. Biểu đồ lớp (hình mới)");
where("**THÊM** vào chương Thiết kế, sau Hình 3.5 (tài liệu API Swagger). Đề xuất một tiểu mục \"Thiết kế lớp\" với đoạn văn dưới đây.");
p("Biểu đồ lớp được lập từ chính các lớp trong mã nguồn, chia thành hai hình để giữ cỡ chữ đọc được khi in. Hình 3.6 mô tả phần phục vụ và huấn luyện mô hình: `ModelLoader` tra phiên bản mới nhất của mô hình trong MLflow Registry, nạp artifact và lưu đệm các đối tượng `LoadedModel` trong RAM; mỗi `LoadedModel` giữ một predictor hiện thực giao diện `Predictor` (`predict_steps`) — `XGBoostPredictor`, `RandomForestPredictor`, `GRUPredictor`, `ArimaPredictor`. Ở phía huấn luyện, mỗi mô hình có một lớp bao (`XGBoostModelWrapper`, `RandomForestModelWrapper`, `ARIMABaseline`) hoặc mạng `GRUForecaster` (PyTorch) với cấu hình `GRUTrainingConfig`; hai phía chỉ liên hệ với nhau qua artifact lưu trong MLflow.");
p("Hình 3.7 mô tả phần thu thập dữ liệu và thành phần dùng chung: module `tasks.py` khai báo ba Celery task, dùng `BinanceAdapter` (ccxt) và `VNStockAdapter`, trả về `CleaningReport`; tham số làm sạch và lịch chạy đọc từ `CleaningConfig`, `SchedulerSettings` (pydantic-settings, không hardcode). Thư viện `shared` gồm cấu hình `Settings`, các lớp ORM kế thừa `Base` (SQLAlchemy 2.x) và các lược đồ pydantic của API như `PredictRequest` (kiểm tra mô hình, khung thời gian) và `ExplainResponse`.");
img("reports/figures/d8a_bieu_do_lop_mo_hinh.png", "Hình 3.6 — Biểu đồ lớp (a): phục vụ và huấn luyện mô hình.");
img("reports/figures/d8b_bieu_do_lop_du_lieu.png", "Hình 3.7 — Biểu đồ lớp (b): thu thập dữ liệu và thành phần dùng chung.");

// ── 3. Tables ────────────────────────────────────────────────────────
h1("3. Các bảng cần thay hoặc sửa");
h2("3.1. Bảng 1.1 — Quy mô hệ thống");
where("**THAY** toàn bộ Bảng 1.1. Tên bảng mới: \"Bảng 1.1. Quy mô hệ thống tại ngày 10/10/2026 (nhánh develop, commit 9e78554).\"");
table(["Hạng mục", "Giá trị", "Ghi chú / nguồn"], [
  ["Dịch vụ", "3 dịch vụ backend + 1 frontend", "ingestion, training, inference, Next.js"],
  ["Container khi chạy", "9", "postgres, redis, mlflow, ingestion, celery-worker, celery-beat, training, inference, frontend"],
  { c: ["API", "10 endpoint", "1 công khai (/health) + 9 yêu cầu API key"], ...CHANGED },
  { c: ["Giao diện", "5 màn hình", "Tổng quan, Dữ liệu & Phân tích, Dự báo AI, Giải thích mô hình, Thu thập & Làm sạch"], ...CHANGED },
  { c: ["Cơ sở dữ liệu", "3 schema / 14 bảng", "market.* (4 bảng) và ops.* (2 bảng) đang được ghi; ml.* (8 bảng) chưa có luồng ghi"], ...CHANGED },
  { c: ["Kiểm thử tự động", "22 tệp test, 342 test", "CI run 37951012615 trên develop, chạy cùng TimescaleDB thật"], ...CHANGED },
  { c: ["Pull Request đã hợp nhất", "60", "gh pr list --state merged"], ...CHANGED },
  ["Dữ liệu đã khóa", "192.740 dòng OHLCV / 25 mã", "15 cổ phiếu VN + 10 cặp crypto, ~2 năm (snapshot)"],
  { c: ["Dữ liệu trong CSDL", "213.164 dòng market.ohlcv", "Sau khi backfill crypto tới 28/09 và thu thập theo lịch"], ...CHANGED },
  { c: ["Thí nghiệm", "36 mô hình đăng ký; 149 MLflow run", "4 mô hình × 9 bộ dữ liệu; 149 run gồm cả 81 run ablation"], ...CHANGED },
], [24, 26, 50]);

h2("3.2. Bảng 2.1 — Yêu cầu chức năng (chỉ các dòng thay đổi)");
where("**SỬA** bốn dòng dưới đây; các dòng khác giữ nguyên.");
table(["Mã", "Yêu cầu chức năng", "Hiện thực tại", "Trạng thái"], [
  { c: ["FR-01", "Thu thập OHLCV cổ phiếu VN theo lịch", "services/ingestion/adapters/vnstock_adapter.py", "Xong; tạm dừng vì gói vnstock bị PyPI cách ly"], ...CHANGED },
  { c: ["FR-12", "API giải thích mô hình (SHAP, permutation importance, hệ số ARIMA)", "GET /api/v1/explain", "Xong — đủ 4 mô hình"], ...CHANGED },
  { c: ["FR-13", "Giao diện tổng quan, danh sách mã và phân tích dữ liệu", "frontend/app/page.tsx, analysis/page.tsx", "Xong"], ...CHANGED },
  { c: ["FR-15", "Giao diện nhật ký job và chất lượng dữ liệu", "frontend/app/pipeline/page.tsx", "Xong"], ...CHANGED },
], [8, 36, 34, 22]);

h2("3.3. Bảng 2.2 — Yêu cầu phi chức năng (chỉ các dòng thay đổi)");
where("**SỬA** bốn dòng dưới đây.");
table(["Mã", "Yêu cầu", "Tiêu chí đo", "Trạng thái"], [
  { c: ["NFR-01", "Hiệu năng API dự báo", "p95 ≤ 2 giây cho một yêu cầu đơn lẻ", "Đạt — p95 ≤ 0,68 s khi mô hình chạy, ≤ 0,04 s khi trúng cache (đo 07/10, xem §5.2)"], ...CHANGED },
  { c: ["NFR-06", "Chất lượng mã nguồn", "ruff check + ruff format + pytest xanh mới được hợp nhất", "CI chạy trên mọi PR; chưa bật branch protection nên chưa cưỡng chế"], ...CHANGED },
  { c: ["NFR-07", "Khả năng quan sát", "Log có cấu trúc, endpoint health, theo dõi lỗi bằng Sentry", "Một phần — ops.job_log ghi trạng thái mọi job; Sentry mới có biến cấu hình, chưa khởi tạo trong mã"], ...CHANGED },
  { c: ["NFR-08", "Độ tin cậy thu thập", "Tỷ lệ job thành công ≥ 95 % trong ≥ 24 giờ", "450/450 = 100 % trong 21 giờ 36 phút chạy liên tục — đạt về tỷ lệ, chưa đủ 24 giờ (xem §5.3)"], ...CHANGED },
], [8, 20, 32, 40]);

h2("3.4. Bảng 3.5 — Thiết kế giao diện");
where("**THAY** toàn bộ Bảng 3.5. Tên bảng mới: \"Bảng 3.5. Năm màn hình chức năng của ứng dụng web.\"");
table(["Màn hình", "Nội dung chính", "API sử dụng"], [
  ["Tổng quan", "Số liệu tổng hợp, mô hình đã đăng ký kèm chỉ số, các job gần nhất", "/stats, /models, /jobs"],
  ["Dữ liệu & Phân tích", "Bảng thông số dữ liệu của 25 mã (thống kê, RSI 14, MACD); biểu đồ nến kèm SMA/RSI/MACD", "/stats, /indicators"],
  ["Dự báo AI", "Chọn mã, mô hình, số bước; biểu đồ lịch sử + đường dự báo; so sánh chỉ số 4 mô hình", "/symbols, /indicators, /predict, /models"],
  ["Giải thích mô hình", "SHAP (XGBoost, Random Forest), permutation importance (GRU), bảng hệ số (ARIMA)", "/symbols, /explain"],
  ["Thu thập & Làm sạch", "Nguồn và lịch thu thập, quy trình làm sạch, chuẩn hóa, chất lượng dữ liệu, nhật ký job, trạng thái dịch vụ", "/data-quality, /jobs, /health"],
], [20, 56, 24]);

// ── 4. XAI ───────────────────────────────────────────────────────────
h1("4. Giải thích mô hình cho cả bốn mô hình");
where("**THAY** Hình 4.3 bằng Hình 4.3a và **THÊM** Hình 4.3b–d. **THÊM** vào Chương 8 một tiểu mục \"Giải thích mô hình\" gồm đoạn văn, bảng và phần hạn chế dưới đây.");
p("Ở bản V2 chỉ XGBoost có phần giải thích (SHAP); API đã nhận cả bốn mô hình nhưng trả lỗi 404 vì ba entrypoint còn lại không ghi artifact giải thích. Từ ngày 05/10, mỗi entrypoint huấn luyện ghi một tệp `explainability/feature_importance.json` vào MLflow run, bằng phương pháp phù hợp với loại mô hình. Các mô hình Random Forest, GRU, ARIMA được huấn luyện lại (27 run) để sinh artifact; RMSE trùng bản cũ (GRU và ARIMA lệch 0, Random Forest lệch ≤ 3,6e-12 do thứ tự cộng số thực khi chạy song song).");
table(["Mô hình", "Phương pháp", "Phát hiện chính trên 9 bộ dữ liệu"], [
  ["XGBoost", "SHAP TreeExplainer — trung bình |SHAP| trên tập kiểm tra", "Đứng đầu luôn là đặc trưng mức giá gần: close_lag_1, rolling_mean_5, close_lag_10, rolling_min_10"],
  ["Random Forest", "SHAP TreeExplainer", "close đứng đầu ở 9/9 bộ dữ liệu, tiếp theo là low / high / rolling_mean_20"],
  ["GRU", "Permutation importance — xáo trộn từng đặc trưng trên tập kiểm tra, 5 lần, seed cố định", "Xáo close làm RMSE tăng thêm 1,01–22,8 lần RMSE gốc; mọi đặc trưng khác làm RMSE tăng < 0,6 %. Khớp thiết kế residual (dự báo = giá gần nhất + hiệu chỉnh)"],
  ["ARIMA(1,1,1)", "Bảng hệ số, sai số chuẩn, p-value", "ar.L1 và ma.L1 cùng có ý nghĩa (p < 0,05) ở 4/9 bộ: ACB, ETHUSDT, VCB, VNM, và ở đó ar.L1 ≈ −ma.L1 (gần bước ngẫu nhiên). Không có ý nghĩa ở BTCUSDT 1d, FPT, HPG, SOLUSDT; BTCUSDT 1h ở ngưỡng (p = 0,052 / 0,069)"],
], [15, 30, 55], "Bảng đề xuất — Giải thích mô hình trên 9 bộ dữ liệu (nguồn: artifact trong MLflow, reports/validations/explainability_2026-10-09.txt).");
p("**Hạn chế phát hiện được:** ARIMA ở BTCUSDT 1d và HPG có hệ số ma.L1 = −7,87 và −6,73 với p ≈ 0,70–0,98, do bậc mô hình được cố định (1,1,1) và tắt ràng buộc khả nghịch (`enforce_invertibility=False`). Ước lượng ở hai bộ dữ liệu này không đáng tin.");
img("docs/evidence/screenshots/ui/ui_09_giai_thich_shap.png", "Hình 4.3a — Giải thích XGBoost (SHAP), ACB 1 ngày.", 560);
img("docs/evidence/screenshots/ui/ui_17_giai_thich_random_forest.png", "Hình 4.3b — Giải thích Random Forest (SHAP), ACB 1 ngày.", 560);
img("docs/evidence/screenshots/ui/ui_18_giai_thich_gru.png", "Hình 4.3c — Giải thích GRU (permutation importance), ACB 1 ngày.", 560);
img("docs/evidence/screenshots/ui/ui_19_giai_thich_arima.png", "Hình 4.3d — Giải thích ARIMA (bảng hệ số), ACB 1 ngày.", 560);

// ── 5. Chapter 6 ─────────────────────────────────────────────────────
h1("5. Chương 6 — Kiểm thử và vận hành");
h2("5.1. Bảng 6.1 — Phân bố tệp kiểm thử");
where("**THAY** Bảng 6.1. Tên bảng mới: \"Bảng 6.1. Phân bố 22 tệp kiểm thử tự động (342 test).\"");
table(["Vị trí", "Số tệp", "Nội dung chính"], [
  ["services/inference/tests", "4", "API (mã lỗi 401/422/429, giải thích, rate limit theo phút), API phân tích dữ liệu, đặc trưng, predictor"],
  ["services/ingestion/tests", "6", "Adapter Binance, Celery app (kết nối CSDL sau khi fork), làm sạch, pipeline, thứ tự lịch, Celery task"],
  ["services/training/tests", "7", "Bốn mô hình (kèm artifact giải thích), benchmark, tiện ích MLflow, ablation"],
  ["tests (gốc)", "5", "Hợp đồng snapshot dữ liệu, kết nối CSDL, mapper, repository dữ liệu thị trường, cấu hình"],
  ["Tổng", "22", "342 test passed trên CI (run 37951012615), có dịch vụ TimescaleDB thật"],
], [30, 12, 58]);
p("Frontend chưa có test tự động. Test ingestion cần CSDL test (`stock_crypto_db_test`): chạy xanh trên CI, nhưng sẽ báo lỗi nếu chạy trên máy không có Postgres.");

h2("5.2. Độ trễ API dự báo (NFR-01 / RQ5)");
where("**THAY** đoạn \"Chưa đo chính thức; quan sát khi demo 0,3–0,5 s\" bằng nội dung dưới đây.");
p("Đo ngày 07/10/2026 bằng `reports/src/measure_latency.py`: `POST /api/v1/predict`, ACB 1 ngày, 5 bước, đo đầu-cuối phía client trên stack Docker local, request giãn nhịp dưới ngưỡng rate limit. Ba kịch bản cho mỗi mô hình: lần gọi đầu sau khi khởi động (tải mô hình từ MLflow), mô hình chạy thật (xóa cache trước mỗi request, 10 lần) và trúng cache (30 lần). Cả 164/164 request trả HTTP 200.");
table(["Mô hình", "Lần gọi đầu", "Mô hình chạy thật p50 / p95", "Trúng cache p50 / p95"], [
  ["ARIMA", "4,66 s", "213 / 559 ms", "21 / 40 ms"],
  ["XGBoost", "1,23 s", "460 / 555 ms", "17 / 27 ms"],
  ["Random Forest", "0,84 s", "576 / 681 ms", "21 / 38 ms"],
  ["GRU", "4,10 s", "186 / 293 ms", "17 / 39 ms"],
], [22, 18, 30, 30], "Bảng đề xuất — Độ trễ POST /api/v1/predict (nguồn: reports/validations/api_latency_2026-10-07.csv).");
p("Kết luận: **đạt** tiêu chí p95 ≤ 2 giây với cả bốn mô hình khi hệ thống đang vận hành. Ngoại lệ là request đầu tiên sau khi khởi động dịch vụ (ARIMA, GRU mất hơn 4 giây để tải mô hình), chỉ xảy ra một lần. Hạn chế: đo tuần tự từ một client, chưa đo tải đồng thời.");

h2("5.3. Tỷ lệ job thành công của pipeline thu thập (NFR-08)");
where("**THAY** mục (d) của Chương 6. Số \"11 thành công, 0 thất bại, 100 %\" trong bản trước lấy từ log container trong khoảng ngắn, không khớp bảng `ops.job_log`.");
p("Số liệu đọc trực tiếp từ bảng `ops.job_log` (mỗi job ghi trạng thái vào bảng này).");
table(["Giai đoạn", "Loại job", "Thành công", "Thất bại", "Kẹt ở running"], [
  ["Vận hành 16/09 – 05/10 (trước khi sửa)", "ingest", "29", "0", "0"],
  { c: ["Vận hành 16/09 – 05/10 (trước khi sửa)", "clean", "31", "4", "11"], ...CHANGED },
  ["Đo lại 09/10 21:58 – 10/10 19:34 (sau khi sửa)", "ingest", "230 (ghi 5.580 dòng)", "0", "0"],
  ["Đo lại 09/10 21:58 – 10/10 19:34 (sau khi sửa)", "clean", "220", "0", "0"],
], [36, 12, 20, 14, 18], "Bảng đề xuất — Kết quả job thu thập và làm sạch (nguồn: ops.job_log).");
bullets([
  "Trước khi sửa: **60/75 = 80 %** (ingest 100 %, clean 67 %) — chưa đạt NFR-08.",
  "Nguyên nhân: Celery worker chạy chế độ prefork; các tiến trình con thừa hưởng và dùng chung kết nối Postgres của tiến trình cha, nên tác vụ làm sạch chạy đồng thời làm hỏng giao dịch của nhau.",
  "Sau khi sửa (PR #67): hệ thống chạy liên tục **21 giờ 36 phút** (09/10 21:58 → 10/10 19:34 giờ Việt Nam), không container nào khởi động lại, khung giờ nào cũng có job (22/22) — **450/450 = 100 %** job thành công.",
  "Phép đo dừng trước mốc 24 giờ theo quyết định của nhóm, nên NFR-08 được ghi là **đạt về tỷ lệ, chưa đủ điều kiện thời lượng 24 giờ**.",
  "Job làm sạch báo 0 dòng xử lý vì job thu thập crypto đã kiểm định và ghi thẳng vào bảng dữ liệu sạch, còn cổ phiếu không có dữ liệu mới (vnstock bị cách ly). Con số này đo độ tin cậy của job, không đo khối lượng dữ liệu được làm sạch.",
]);

h2("5.4. Hai lỗi phát hiện và đã sửa trong giai đoạn này");
where("**THÊM** vào Chương 6 (đề xuất một tiểu mục \"Lỗi phát hiện qua đo đạc\").");
table(["Lỗi", "Cách phát hiện", "Nguyên nhân", "Sửa và kiểm chứng"], [
  ["Rate limiter khóa client sau 60 request tính tổng, thay vì 60 request/phút", "Lần đo p95 đầu tiên chỉ có số liệu ARIMA; các mô hình đo sau nhận HTTP 429", "TTL 60 giây được làm mới sau mỗi request, nên bộ đếm chỉ về 0 khi client ngừng gọi trọn một phút", "PR #65: đếm theo từng phút cố định. Trước khi sửa: 52/164 request bị 429 dù gọi dưới ngưỡng. Sau khi sửa: 0/164; gửi dồn 65 request thì 60 được phục vụ, 5 bị chặn"],
  ["Job làm sạch lỗi hoặc kẹt ở trạng thái running", "Đọc ops.job_log khi đối chiếu số liệu Chương 6", "Tiến trình con của Celery dùng chung kết nối Postgres sau khi fork", "PR #67: reset pool kết nối ở mỗi tiến trình con. Tái hiện với 20 tác vụ đồng thời: 15/20 và 12/20 thành công trước khi sửa, 20/20 ở cả hai lần chạy sau khi sửa"],
], [22, 24, 24, 30]);

// ── 6. Chapter 8 ─────────────────────────────────────────────────────
h1("6. Chương 8 — Kết quả thực nghiệm");
h2("6.1. So sánh với baseline Naive");
where("**SỬA** phần nhận xét và Bảng 8.3 (nếu cần) theo số liệu dưới đây. Số liệu không đổi so với V2; bảng được tính lại từ 36 mô hình trong MLflow Registry ngày 09/10.");
table(["Bộ dữ liệu", "Mô hình tốt nhất", "Cải thiện RMSE so với Naive", "Các mô hình vượt Naive"], [
  ["ACB 1d", "GRU", "+0,72 %", "ARIMA, GRU"],
  ["BTCUSDT 1d", "ARIMA", "−0,23 %", "—"],
  ["BTCUSDT 1h", "ARIMA", "−0,02 %", "—"],
  ["ETHUSDT 1d", "GRU", "−2,71 %", "—"],
  ["FPT 1d", "GRU", "−0,44 %", "—"],
  ["HPG 1d", "Random Forest", "+6,40 %", "GRU, Random Forest"],
  ["SOLUSDT 1d", "ARIMA", "−0,24 %", "—"],
  ["VCB 1d", "GRU", "+1,07 %", "GRU"],
  ["VNM 1d", "ARIMA", "+3,31 %", "ARIMA, GRU"],
], [20, 22, 28, 30], "Bảng đề xuất — Mô hình tốt nhất và mức vượt Naive trên 9 bộ dữ liệu.");
bullets([
  "**4/9 bộ dữ liệu (44 %)** có ít nhất một mô hình vượt Naive, nên tiêu chí ≥ 70 % chưa đạt. Theo mô hình: GRU 4/9, ARIMA 2/9, Random Forest 1/9, XGBoost 0/9.",
  "Mức vượt đều nhỏ (0,7–6,4 %) và chưa được kiểm định ý nghĩa thống kê (ví dụ kiểm định Diebold–Mariano).",
]);

h2("6.2. Thí nghiệm ablation (mục mới)");
where("**THÊM** một tiểu mục \"Thí nghiệm ablation\" vào Chương 8.");
p("**Câu hỏi:** bảy đặc trưng kỹ thuật của GRU (trung bình trượt 7/14 phiên, lợi suất 1/3/7 phiên, độ lệch chuẩn cuộn 7/14 phiên) có giúp dự báo tốt hơn so với chỉ dùng giá đóng cửa không?");
p("**Thiết kế:** `services/training/ablation_gru.py` huấn luyện lại GRU với ba tập đặc trưng: đầy đủ (8), close + MA7 + MA14 (3), chỉ close (1). Mọi thứ khác giữ nguyên: cùng pipeline dữ liệu, scaler chỉ fit trên tập train, cùng kiến trúc, early stopping trên tập validation, đánh giá trên tập test. Thí nghiệm gồm 9 bộ dữ liệu × 3 biến thể × 3 seed (42, 43, 44) = 81 run, ghi vào MLflow experiment `ablation_gru_features`. **Kiểm tra tính đúng:** biến thể đầy đủ với seed 42 tái lập chính xác RMSE của 9 mô hình GRU đang đăng ký (chênh lệch 0).");
table(["Bộ dữ liệu", "Naive", "Đầy đủ (8)", "close + MA (3)", "Chỉ close (1)", "Chỉ close so với đầy đủ", "Vượt 2σ?"], [
  ["ACB 1d", "0,3902", "0,3873 ± 0,0004", "0,3898 ± 0,0006", "0,3895 ± <0,0001", "+0,55 % (kém hơn)", "Có"],
  ["BTCUSDT 1d", "1386,27", "1435,63 ± 3,06", "1421,37 ± 0,56", "1422,86 ± 2,81", "−0,89 %", "Có"],
  ["BTCUSDT 1h", "308,39", "378,18 ± 9,79", "411,37 ± 29,6", "345,36 ± 7,66", "−8,68 %", "Có"],
  ["ETHUSDT 1d", "56,48", "58,23 ± 0,24", "57,88 ± 0,03", "57,88 ± 0,01", "−0,60 %", "Không"],
  ["FPT 1d", "1,5785", "1,5828 ± 0,0070", "1,6123 ± 0,0055", "1,5825 ± 0,0042", "−0,02 %", "Không"],
  ["HPG 1d", "0,4141", "0,4137 ± 0,0003", "0,4127 ± 0,0001", "0,4126 ± 0,0003", "−0,27 %", "Có"],
  ["SOLUSDT 1d", "2,3431", "2,7049 ± 0,0876", "2,9140 ± 0,0547", "2,5519 ± 0,0598", "−5,66 %", "Không"],
  ["VCB 1d", "1,0317", "1,0214 ± 0,0015", "1,0222 ± 0,0002", "1,0197 ± 0,0001", "−0,17 %", "Không"],
  ["VNM 1d", "0,8614", "0,8373 ± 0,0175", "0,8557 ± 0,0032", "0,8548 ± 0,0017", "+2,10 % (kém hơn)", "Không"],
], [13, 10, 16, 16, 16, 17, 12], "Bảng đề xuất — RMSE trên tập test (trung bình ± độ lệch chuẩn qua 3 seed). Nguồn: reports/validations/ablation_gru_features_2026-10-09.csv.");
p("Cột \"Vượt 2σ?\" cho biết chênh lệch giữa \"chỉ close\" và \"đầy đủ\" có lớn hơn hai lần độ lệch chuẩn giữa các seed hay không. Đây là quy tắc thô với 3 seed, **không phải** kiểm định thống kê.");
bullets([
  "Chỉ dùng giá đóng cửa cho RMSE trung bình **thấp hơn hoặc bằng** bản đầy đủ ở 7/9 bộ dữ liệu. Chênh lệch vượt mức dao động giữa các seed ở 4/9 bộ: tốt hơn rõ ở BTCUSDT 1d, BTCUSDT 1h, HPG; kém hơn rõ ở ACB. Năm bộ còn lại nằm trong mức nhiễu.",
  "Trong cấu hình hiện tại, các đặc trưng kỹ thuật **không đem lại lợi ích ổn định** cho GRU. Kết quả này khớp với permutation importance (§4): GRU gần như chỉ dựa vào giá đóng cửa.",
  "Không biến thể nào thay đổi kết luận so với Naive: cả bản đầy đủ lẫn bản chỉ close đều vượt Naive (theo trung bình 3 seed) ở cùng 4 bộ ACB, HPG, VCB, VNM.",
  "Độ dao động giữa các seed đáng kể ở một số bộ (VNM, bản đầy đủ: 0,8373 ± 0,0175), nên kết quả benchmark một seed cần được đọc kèm cảnh báo này.",
]);

// ── 7. Chapter 7 ─────────────────────────────────────────────────────
h1("7. Chương 7 — Quy trình");
where("**SỬA** bảng số liệu sprint: Sprint 9 đã kết thúc (bản V2 ghi \"chưa kết thúc, số liệu tính đến 28/09\"); thêm Sprint 10.");
table(["Sprint", "Thời gian", "Commit", "Tác giả", "PR mở", "PR hợp nhất", "Trạng thái"], [
  ["9", "21/09 – 04/10", "22", "3", "14", "13", "Đã kết thúc (1 PR đóng không hợp nhất)"],
  ["10", "05/10 – 18/10", "9", "1", "7", "7", "Đang diễn ra — tính đến 09/10, trước các PR mở cùng ngày"],
], [10, 18, 10, 10, 10, 14, 28], "Nguồn: reports/agile_metrics.csv, sinh bằng reports/src/agile_metrics.py từ Git/GitHub.");
bullets([
  "Nhật ký: docs/sprint-logs/sprint-9.md (đã chốt) và sprint-10.md (đang diễn ra).",
  "Commit của tài khoản Ennela từ 22/09 đều có dòng \"Co-Authored-By: Claude\" (viết với trợ giúp AI agent).",
  "Hầu hết PR hợp nhất không có review của thành viên khác; nhánh develop vẫn chưa bật branch protection dù Chương 7 đã đề ra.",
]);

// ── 8. Chapter 9 ─────────────────────────────────────────────────────
h1("8. Chương 9 — Đối chiếu tiêu chí nghiệm thu và hạn chế");
h2("8.1. Bảng 9.2 — Mức độ đáp ứng tiêu chí nghiệm thu");
where("**THAY** toàn bộ Bảng 9.2.");
table(["Tiêu chí nghiệm thu", "Yêu cầu", "Hiện trạng (10/10/2026)", "Đánh giá"], [
  ["Thu thập tự động", "Chạy theo lịch, có log", "Celery Beat + Worker, log ở ops.job_log; cổ phiếu VN tạm dừng do vnstock bị PyPI cách ly", "Đạt (crypto)"],
  { c: ["Độ tin cậy thu thập (NFR-08)", "Job thành công ≥ 95 % trong ≥ 24 giờ", "Trước khi sửa 80 %; sau khi sửa 450/450 = 100 % trong 21 giờ 36 phút", "Đạt về tỷ lệ, chưa đủ 24 giờ"], ...CHANGED },
  { c: ["Web App", "≥ 5 màn hình chức năng", "5 màn hình", "Đạt"], ...CHANGED },
  { c: ["API dự báo", "p95 ≤ 2 giây", "p95 ≤ 0,68 s khi mô hình chạy; ≤ 0,04 s khi trúng cache", "Đạt"], ...CHANGED },
  ["Bảo mật tối thiểu", "API key, giới hạn tần suất, kiểm tra đầu vào", "Đủ ba lớp; rate limit đã sửa (PR #65); API key còn lộ qua biến NEXT_PUBLIC_*", "Đạt"],
  ["Số mô hình", "≥ 3 baseline + ≥ 1 mô hình học sâu", "Naive + ARIMA + XGBoost + Random Forest + GRU", "Đạt"],
  ["Bảng so sánh trên cùng tập test", "Bắt buộc", "Có, kèm cổng kiểm định độc lập (ACB 1d)", "Đạt"],
  { c: ["Ablation", "Ít nhất một thí nghiệm", "GRU bỏ nhóm đặc trưng: 9 bộ × 3 biến thể × 3 seed", "Đạt"], ...CHANGED },
  ["Vượt Naive ở ≥ 70 % số mã", "Tiêu chí chính", "4/9 bộ dữ liệu (44 %)", "Chưa đạt"],
  { c: ["Tài liệu", "Đủ chương, có trích dẫn, có nhật ký sprint", "Nhật ký sprint 1–10 (sprint 10 đang diễn ra; 11–12 chưa đến)", "Một phần"], ...CHANGED },
], [22, 22, 38, 18]);

h2("8.2. Mục 9.3 — Hạn chế");
where("**THAY** danh sách hạn chế bằng danh sách dưới đây.");
bullets([
  "Tiêu chí vượt Naive ở ≥ 70 % số mã chưa đạt (44 %); mức vượt nhỏ và chưa được kiểm định thống kê.",
  "Mô hình cây (XGBoost, Random Forest) không ngoại suy được ra ngoài vùng giá đã thấy khi huấn luyện, nên thua Naive nặng ở các chuỗi có xu hướng mạnh (SOLUSDT, BTCUSDT, ETHUSDT, FPT).",
  "ARIMA cố định bậc (1,1,1) và tắt ràng buộc khả nghịch, nên ước lượng không ổn định ở một số chuỗi (BTCUSDT 1d, HPG).",
  "Mọi kết quả dùng một lần chia train/validation/test cố định; độ dao động mới được ước lượng qua 3 seed trong thí nghiệm ablation.",
  "Inference luôn nạp phiên bản mới nhất trong Model Registry; cổng kiểm định khoa học chưa tự động quyết định phiên bản được phục vụ.",
  "Thu thập cổ phiếu VN tạm dừng do gói vnstock bị PyPI cách ly; dữ liệu FPT 1d còn khoảng trống 08/07 – 11/09.",
  "Nhóm bảng ml.* chưa có luồng ghi, nên /predict không lưu lịch sử dự báo vào cơ sở dữ liệu.",
  "Lần gọi đầu sau khi khởi động inference mất 4,1–4,7 giây với ARIMA và GRU (tải mô hình từ MLflow).",
  "API key nằm trong biến NEXT_PUBLIC_* nên lộ ra trình duyệt; hệ thống chưa có đăng nhập.",
  "Frontend chưa có test tự động; nhánh develop chưa bật branch protection.",
  "Phép đo NFR-08 sau khi sửa mới được 21 giờ 36 phút, chưa đủ 24 giờ.",
]);

// ── 9. Sources ───────────────────────────────────────────────────────
h1("9. Nguồn kiểm chứng");
p("Mọi số liệu trong tài liệu truy được tới các tệp sau trên nhánh develop (và PR #70):");
bullets([
  "Tổng hợp số liệu kèm nguồn: reports/TONG_HOP_SO_LIEU_CUOI_KY.md.",
  "Độ trễ API: reports/validations/api_latency_2026-10-07.md và .csv; script reports/src/measure_latency.py.",
  "Ablation: reports/validations/ablation_gru_features_2026-10-09.csv; tóm tắt bằng reports/src/ablation_summary.py.",
  "Giải thích mô hình: reports/validations/explainability_2026-10-09.txt (run ID từng mô hình).",
  "Tỷ lệ job: truy vấn ops.job_log ghi trong reports/ch6_kiem_thu.md, mục (d).",
  "Ảnh giao diện: docs/evidence/screenshots/ui/ (ui_09, ui_17 – ui_19 chụp ngày 09/10); hình thiết kế: reports/figures/, sinh bằng reports/src/diagrams.py.",
  "Quy trình: reports/agile_metrics.csv, docs/sprint-logs/.",
]);

const doc = new Document({
  creator: "Nhóm đề tài NCKH",
  title: "Cập nhật báo cáo tiến độ — 10/10/2026",
  styles: {
    default: { document: { run: { font: F, size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 30, bold: true, font: F, color: NAVY }, paragraph: { spacing: { before: 320, after: 140 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 25, bold: true, font: F, color: "2E5597" }, paragraph: { spacing: { before: 220, after: 100 }, outlineLevel: 1 } },
    ],
  },
  numbering: { config: [{ reference: "bul", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1134, right: 1134, bottom: 1134, left: 1134 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Cập nhật báo cáo tiến độ — trang ", font: F, size: 18, color: GREY }), new TextRun({ children: [PageNumber.CURRENT], font: F, size: 18, color: GREY })] })] }) },
    children: body,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUT, buf);
  console.log("saved", OUT, buf.length, "bytes");
});
