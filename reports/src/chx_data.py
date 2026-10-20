"""Chương X — Quy trình xử lý & phân tích dữ liệu → reports/src/chx.json.

Every number is read from the running Inference API (/stats, /data-quality),
so the chapter regenerates when the data changes. Figures are the evidence
screenshots in docs/evidence/screenshots/ui and diagrams in reports/figures.

Usage (stack running, from the repo root):
    python reports/src/chx_data.py
    node reports/src/build_chx.js
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime
from pathlib import Path

from PIL import Image

import diagrams  # noqa: E402 — sibling module in reports/src

ROOT = Path(__file__).resolve().parents[2]
API = os.environ.get("API", "http://localhost:8010")
KEY = os.environ.get("API_KEY", "generate_a_secure_long_random_string_here")
UI = "docs/evidence/screenshots/ui"
FIG = "reports/figures"

blocks: list[dict] = []
counters = {"fig": 0, "tab": 0, "code": 0}


def get(path: str):
    req = urllib.request.Request(f"{API}{path}", headers={"X-API-Key": KEY})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def num(x: float | None, d: int = 2) -> str:
    if x is None:
        return "—"
    s = f"{x:,.{d}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def day(iso: str) -> str:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d/%m/%Y")


def vol(x: float) -> str:
    if x >= 1e9:
        return num(x / 1e9, 2) + " tỷ"
    if x >= 1e6:
        return num(x / 1e6, 2) + " tr"
    if x >= 1e3:
        return num(x / 1e3, 1) + " N"
    return num(x, 1)


def h1(x):
    blocks.append({"t": "h1", "x": x})


def h2(x):
    blocks.append({"t": "h2", "x": x})


def h3(x):
    blocks.append({"t": "h3", "x": x})


def p(x, **o):
    blocks.append({"t": "p", "x": x, **o})


def bl(x, lvl=0):
    blocks.append({"t": "b", "x": x, "lvl": lvl})


def note(text, title=None, kind="info"):
    blocks.append({"t": "callout", "text": text, "title": title, "kind": kind})


def table(head, rows, widths, caption, **o):
    counters["tab"] += 1
    blocks.append(
        {
            "t": "table",
            "head": head,
            "rows": rows,
            "w": widths,
            "caption": f"Bảng X.{counters['tab']}. {caption}",
            **o,
        }
    )
    return f"Bảng X.{counters['tab']}"


def img(file, caption, width=630):
    counters["fig"] += 1
    w, h = Image.open(ROOT / file).size
    blocks.append(
        {
            "t": "img",
            "file": file,
            "ratio": h / w,
            "width": width,
            "caption": f"Hình X.{counters['fig']} — {caption}",
        }
    )
    return f"Hình X.{counters['fig']}"


def code(lines, caption):
    counters["code"] += 1
    blocks.append(
        {
            "t": "code",
            "lines": lines,
            "caption": f"Mã nguồn X.{counters['code']} — {caption}",
        }
    )


# ── data ─────────────────────────────────────────────────────────────
stats_1d, stats_1h = (
    get("/api/v1/stats?timeframe=1d"),
    get("/api/v1/stats?timeframe=1h"),
)
dq_1d, dq_1h = (
    get("/api/v1/data-quality?timeframe=1d"),
    get("/api/v1/data-quality?timeframe=1h"),
)
stocks = [s for s in stats_1d if s["asset_class"] == "stock"]
crypto_1d = [s for s in stats_1d if s["asset_class"] == "crypto"]
total_bars = sum(s["bars"] for s in stats_1d + stats_1h)

# ── chapter ──────────────────────────────────────────────────────────
h1("Chương X. Quy trình thu thập, xử lý và phân tích dữ liệu")
note(
    [
        "Chương này trả lời bốn câu hỏi của giảng viên: (1) dữ liệu được thu thập như thế nào; "
        "(2) được tổ chức, làm sạch và chuẩn hóa ra sao trước khi đưa vào mô hình; (3) các thông số "
        "thống kê của dữ liệu; (4) dashboard phân tích sự biến động của dữ liệu.",
        f"Mọi số liệu trong chương được đọc trực tiếp từ hệ thống đang chạy (API /stats và /data-quality) "
        f"ngày {datetime.now().strftime('%d/%m/%Y')} bằng reports/src/chx_data.py; chạy lại script sẽ cập nhật "
        "toàn bộ bảng. Ký hiệu “X” trong số chương, bảng, hình được thay bằng số chương thật khi ghép báo cáo.",
    ],
    "Mục tiêu và nguồn số liệu của chương",
)

# X.1 ──────────────────────────────────────────────────────────────────
h2("X.1. Thu thập dữ liệu cổ phiếu và tiền mã hóa")
h3("X.1.1. Nguồn dữ liệu")
p(
    "Hệ thống thu thập dữ liệu giá dạng OHLCV (giá mở cửa, cao nhất, thấp nhất, đóng cửa và khối lượng) "
    "cho 25 tài sản: 15 cổ phiếu niêm yết trên sàn HOSE và 10 cặp tiền mã hóa niêm yết bằng USDT trên Binance. "
    "Danh sách tài sản được khóa trong hợp đồng dữ liệu configs/group_dataset.json để mọi thí nghiệm dùng chung "
    "một tập dữ liệu."
)
table(
    ["Nguồn", "Thị trường", "Tài sản", "Khung thời gian", "Cách truy cập"],
    [
        [
            "vnstock (nguồn VCI)",
            "Cổ phiếu Việt Nam (HOSE)",
            ", ".join(s["ticker"] for s in stocks),
            "1 ngày",
            "Thư viện Python vnstock, gọi API lịch sử giá của CTCK VCI",
        ],
        [
            "Binance",
            "Tiền mã hóa (cặp USDT)",
            ", ".join(s["ticker"] for s in crypto_1d),
            "1 giờ, 1 ngày",
            "Thư viện ccxt gọi REST API công khai của Binance, bật giới hạn tần suất (enableRateLimit)",
        ],
    ],
    [16, 16, 34, 12, 22],
    "Nguồn dữ liệu và danh mục tài sản.",
)
p(
    "Mỗi nguồn có một adapter riêng trong services/ingestion/adapters/ và cùng trả về một kiểu dữ liệu chuẩn "
    "(OHLCVCreate). Phần còn lại của hệ thống không phụ thuộc dữ liệu đến từ nguồn nào: thêm một sàn mới chỉ là "
    "thêm một adapter."
)

h3("X.1.2. Thu thập tự động theo lịch")
p(
    "Việc thu thập chạy tự động bằng Celery: Celery Beat là bộ lập lịch theo crontab, Celery Worker thực thi tác vụ, "
    "Redis làm hàng đợi. Mỗi lần chạy, tác vụ lấy dữ liệu gần nhất (crypto khung giờ: 24 giờ; khung ngày: 30 ngày; "
    "cổ phiếu: 7 ngày), ghi đè an toàn (upsert) nên chạy lại nhiều lần không sinh bản ghi trùng, và ghi kết quả "
    "vào nhật ký ops.job_log."
)
table(
    ["Tác vụ", "Lịch chạy (UTC)", "Giờ Việt Nam", "Tài sản", "Khoảng dữ liệu mỗi lần"],
    [
        [
            "ingest-crypto-hourly",
            "Phút 5 mỗi giờ",
            "Phút 5 mỗi giờ",
            "10 cặp crypto, khung 1h",
            "24 giờ gần nhất",
        ],
        [
            "ingest-crypto-daily",
            "00:10 hằng ngày",
            "07:10",
            "10 cặp crypto, khung 1d",
            "30 ngày gần nhất",
        ],
        [
            "ingest-stocks-daily",
            "Thứ 2–6, 10:00",
            "17:00 (sau giờ đóng cửa)",
            "15 cổ phiếu, khung 1d",
            "7 ngày gần nhất",
        ],
        [
            "clean-store-*",
            "Crypto mỗi giờ; cổ phiếu thứ 2–6 từ 11:00",
            "18:00",
            "Từng mã, giãn cách 2 phút",
            "Dữ liệu thô chưa làm sạch",
        ],
    ],
    [20, 20, 16, 22, 22],
    "Lịch thu thập và làm sạch tự động (services/ingestion/celery_app.py, app/scheduler.py).",
)
code(
    [
        "celery_app.conf.beat_schedule = {",
        '    "ingest-crypto-hourly": {',
        '        "task": "tasks.ingest_crypto_task",',
        '        "schedule": crontab(minute=5),',
        '        "args": (scheduler_settings.INGEST_CRYPTO_SYMBOLS, "1h"),',
        "    },",
        '    "ingest-stocks-daily": {',
        '        "task": "tasks.ingest_stocks_task",',
        '        "schedule": crontab(day_of_week="1-5", hour=10, minute=0),',
        '        "args": (scheduler_settings.INGEST_STOCK_SYMBOLS, "1d"),',
        "    },",
        "    # ingest-crypto-daily: crontab(hour=0, minute=10), khung 1d",
        "}",
    ],
    "services/ingestion/celery_app.py: lịch thu thập; danh sách mã đọc từ cấu hình .env, không viết cứng.",
)
img(
    f"{UI}/ui_11_nguon_va_lich_thu_thap.png",
    "Màn hình “Thu thập & Làm sạch”: nguồn dữ liệu và lịch thu thập tự động.",
)

h3("X.1.3. Dữ liệu lịch sử và quy mô dữ liệu")
p(
    "Lịch tự động chỉ lấy dữ liệu mới. Dữ liệu lịch sử (khoảng 2 năm) được nạp một lần bằng script backfill "
    "(scripts/backfill_all.py) rồi xuất thành snapshot bất biến có dấu vân tay SHA-256 (group_dataset_v1). "
    "Khi có khoảng trống, scripts/backfill.py với tùy chọn --start và --skip-existing chỉ chèn những nến còn "
    "thiếu, không ghi đè dữ liệu đã có."
)
groups = [
    ("Cổ phiếu VN", "1 ngày", stocks),
    ("Tiền mã hóa", "1 ngày", crypto_1d),
    ("Tiền mã hóa", "1 giờ", stats_1h),
]
table(
    ["Nhóm", "Khung", "Số mã", "Từ ngày", "Đến ngày", "Số nến / mã", "Tổng số nến"],
    [
        [
            g,
            tf,
            str(len(rows)),
            day(min(r["first_ts"] for r in rows)),
            day(max(r["last_ts"] for r in rows)),
            f"{num(min(r['bars'] for r in rows), 0)} – {num(max(r['bars'] for r in rows), 0)}",
            num(sum(r["bars"] for r in rows), 0),
        ]
        for g, tf, rows in groups
    ]
    + [
        [
            [{"t": "Tổng", "b": True}],
            "",
            "25",
            "",
            "",
            "",
            [{"t": num(total_bars, 0), "b": True}],
        ]
    ],
    [18, 10, 9, 15, 15, 16, 17],
    "Quy mô dữ liệu đã làm sạch trong market.ohlcv.",
    right=[2, 5, 6],
)
img(
    f"{UI}/ui_15_nhat_ky_job.png",
    "Nhật ký tác vụ thu thập và làm sạch (ops.job_log) hiển thị trên giao diện.",
    430,
)

h3("X.1.4. Các vấn đề gặp phải khi thu thập và cách xử lý")
table(
    ["Vấn đề", "Nguyên nhân", "Cách xử lý"],
    [
        [
            "Nến Binance bị ghi muộn 7 giờ trong snapshot",
            "Adapter dùng datetime.fromtimestamp() không kèm múi giờ nên lấy giờ của máy chạy (UTC+7) rồi gắn nhãn UTC",
            "Sửa adapter tạo thời điểm UTC trực tiếp, có test mô phỏng máy UTC+7; snapshot đã khóa giữ nguyên và được ghi chú",
        ],
        [
            "Gói vnstock bị PyPI cách ly (09/2026)",
            "PyPI đưa dự án vào trạng thái quarantined và gỡ gói phụ thuộc vnai",
            "Tách vnstock thành phụ thuộc tùy chọn; khi thiếu gói, tác vụ cổ phiếu ghi trạng thái skipped kèm lý do",
        ],
        [
            "Dữ liệu hở từ 08/07 đến 11/09/2026",
            "Hệ thống tạm dừng; tác vụ định kỳ chỉ lấy 7 ngày/24 giờ gần nhất nên không tự lấp khoảng trống",
            "Backfill 10 mã crypto bằng --start --skip-existing (28/09/2026); FPT còn thiếu vì cần vnstock",
        ],
    ],
    [24, 38, 38],
    "Sự cố thực tế trong quá trình thu thập.",
)

# X.2 ──────────────────────────────────────────────────────────────────
h2("X.2. Tổ chức, làm sạch và chuẩn hóa dữ liệu")
h3("X.2.1. Tổ chức dữ liệu")
p(
    "Dữ liệu được lưu trong PostgreSQL với phần mở rộng TimescaleDB, chia theo trách nhiệm thành các schema "
    "market (dữ liệu thị trường), ml (vòng đời mô hình) và ops (vận hành). Dữ liệu thô và dữ liệu sạch nằm ở hai "
    "bảng khác nhau để luôn truy vết được bản gốc."
)
table(
    ["Bảng", "Vai trò", "Khóa / ràng buộc"],
    [
        [
            "market.symbol",
            "Danh mục tài sản (mã, loại tài sản, sàn, nguồn)",
            "id; ticker duy nhất theo sàn",
        ],
        [
            "market.ohlcv_raw",
            "Nến thô đúng như nguồn trả về, kèm raw_payload và ingested_at",
            "Giữ mọi lần thu thập để truy vết",
        ],
        [
            "market.ohlcv",
            "Nến đã làm sạch — nguồn cho phân tích, dashboard và huấn luyện",
            "Hypertable TimescaleDB; khóa chính (symbol_id, timeframe, ts); CHECK high ≥ low, giá ≥ 0, khối lượng ≥ 0",
        ],
        [
            "ops.job_log",
            "Nhật ký từng tác vụ thu thập/làm sạch",
            "Trạng thái pending/running/success/failed/skipped, thời gian chạy, số dòng",
        ],
        [
            "ops.data_quality_check",
            "Báo cáo chất lượng của mỗi lần làm sạch",
            "Chi tiết JSONB: số dòng vào/ra, trùng, điền, outlier",
        ],
    ],
    [22, 42, 36],
    "Các bảng tham gia quy trình dữ liệu.",
)
diagrams.OUT = str(ROOT / FIG)
diagrams.d2_pipeline(
    heading=None, ohlcv_rows=num(total_bars, 0), name="chx_duong_ong.png"
)
img(
    f"{FIG}/chx_duong_ong.png",
    "Đường ống dữ liệu từ API nguồn tới dashboard và mô hình; các khối viền xanh lá là ranh giới khóa dữ liệu trước khi mô hình nhìn thấy.",
)

h3("X.2.2. Làm sạch dữ liệu")
p(
    "Pipeline làm sạch (services/ingestion/app/cleaning.py) đọc dữ liệu từ market.ohlcv_raw, lần lượt thực hiện "
    "bốn bước dưới đây rồi ghi vào market.ohlcv. Mọi bước chỉ dùng dữ liệu quá khứ, không nhìn trước tương lai."
)
table(
    ["Bước", "Xử lý", "Chi tiết"],
    [
        [
            "1. Chuẩn hóa múi giờ",
            "Đưa mọi mốc thời gian về UTC",
            "Binance đã là UTC; vnstock khung ngày giữ nguyên ngày giao dịch; khung trong ngày trừ 7 giờ",
        ],
        [
            "2. Loại bản ghi trùng",
            "Khóa (symbol_id, timeframe, ts)",
            "Nếu trùng, giữ bản có ingested_at mới nhất",
        ],
        [
            "3. Xử lý dữ liệu khuyết",
            "Forward-fill phiên thiếu (chỉ cổ phiếu khung ngày)",
            "Dựng lịch thứ 2–6, điền tối đa 3 phiên liên tiếp (CLEANING_FFILL_LIMIT) bằng giá phiên trước, khối lượng = 0; "
            "khoảng trống dài hơn bị bỏ. Crypto giao dịch 24/7 nên không điền: nến thiếu là lỗi nguồn",
        ],
        [
            "4. Phát hiện nhiễu (outlier)",
            "Quy tắc IQR, k = 1,5",
            "Giá trị ngoài [Q1 − 1,5·IQR; Q3 + 1,5·IQR] của close/volume theo từng mã được gắn cờ is_outlier, không xóa",
        ],
    ],
    [20, 24, 56],
    "Bốn bước làm sạch.",
)
code(
    [
        'full_idx = pd.bdate_range(start=group.index.min(), end=group.index.max(), freq="B")',
        "group = group.reindex(full_idx)              # phiên thiếu -> NaN",
        'for col in ["open", "high", "low", "close"]:',
        "    group[col] = group[col].ffill(limit=ffill_limit)   # chỉ dùng quá khứ",
        'group.loc[group["volume"].isna(), "volume"] = 0     # đánh dấu phiên được điền',
        'group = group.dropna(subset=["close"])     # khoảng trống > limit bị bỏ',
        "",
        "q1, q3 = grp.transform(lambda x: x.quantile(0.25)), grp.transform(lambda x: x.quantile(0.75))",
        "outlier_mask = (values < q1 - k * (q3 - q1)) | (values > q3 + k * (q3 - q1))",
        'df.loc[outlier_mask, "is_outlier"] = True   # gắn cờ, không xóa',
    ],
    "services/ingestion/app/cleaning.py (rút gọn): điền phiên thiếu và phát hiện outlier.",
)
img(
    f"{UI}/ui_12_quy_trinh_lam_sach.png",
    "Quy trình làm sạch hiển thị trên giao diện.",
    420,
)

h3("X.2.3. Kết quả làm sạch trên dữ liệu thật")
p(
    "Dữ liệu lịch sử được nạp bằng snapshot/backfill nên chưa đi qua pipeline tự động. Để có số liệu thật, "
    "scripts/audit_cleaning.py chạy lại đúng bốn bước trên toàn bộ market.ohlcv_raw của 25 mã và ghi báo cáo vào "
    "ops.data_quality_check, không ghi đè market.ohlcv (ghi thật sẽ chèn thêm nến vào cửa sổ dữ liệu đã khóa cho "
    "thí nghiệm; kiểm tra hợp đồng dữ liệu vẫn PASS sau khi chạy)."
)


def audit_rows(dq, cls):
    out = []
    for r in dq:
        c = r.get("last_pipeline_check")
        if r["asset_class"] != cls or not c:
            continue
        out.append(c["detail"])
    return out


summary = []
for label, dq, cls in (
    ("Cổ phiếu 1d", dq_1d, "stock"),
    ("Crypto 1d", dq_1d, "crypto"),
    ("Crypto 1h", dq_1h, "crypto"),
):
    rows = audit_rows(dq, cls)
    if not rows:
        continue
    total_in = sum(d["input_rows"] for d in rows)
    total_out = sum(d["outliers_flagged"] for d in rows)
    summary.append(
        [
            label,
            str(len(rows)),
            num(total_in, 0),
            num(sum(d["duplicates_removed"] for d in rows), 0),
            num(sum(d["missing_filled"] for d in rows), 0),
            f"{num(total_out, 0)} ({num(100 * total_out / total_in, 1)}%)",
        ]
    )
table(
    ["Nhóm", "Số mã", "Nến thô", "Bản ghi trùng", "Phiên được điền", "Outlier gắn cờ"],
    summary,
    [20, 10, 18, 16, 16, 20],
    "Kết quả chạy lại pipeline làm sạch trên toàn bộ dữ liệu thô.",
    right=[1, 2, 3, 4, 5],
)
bl(
    "Không có bản ghi trùng: khóa chính (symbol_id, timeframe, ts) kết hợp upsert đã chặn trùng ngay tại khâu ghi."
)
bl(
    "Mỗi cổ phiếu thiếu 24 phiên so với lịch thứ 2–6 trong khoảng 24/05/2024 – 08/07/2026; pipeline điền 20 phiên, "
    "4 phiên còn lại thuộc các kỳ nghỉ dài hơn 3 ngày (ví dụ Tết Nguyên đán) nên được bỏ đúng thiết kế."
)
note(
    [
        "Bước 4 áp IQR lên mức giá của cả chuỗi. Với chuỗi có xu hướng mạnh, cách này gắn cờ cả những giai đoạn giá "
        "cao/thấp hoàn toàn bình thường (khoảng 7–12% nến crypto khung giờ). Vì vậy trang chất lượng dữ liệu đếm outlier "
        "trên lợi suất giữa hai nến liên tiếp thay vì trên mức giá. Hướng cải tiến: chuyển bước 4 sang lợi suất hoặc dùng "
        "cửa sổ trượt."
    ],
    "Hạn chế đã nhận diện",
    "warn",
)
img(
    f"{UI}/ui_14_chat_luong_du_lieu.png",
    "Bảng chất lượng dữ liệu: độ đầy đủ, nến lỗi, outlier và kết quả làm sạch của 25 mã.",
)

h3("X.2.4. Chuẩn hóa dữ liệu trước khi đưa vào mô hình")
p(
    "Chuẩn hóa là một bước trong pipeline huấn luyện của từng mô hình, không ghi đè dữ liệu gốc. Dữ liệu được chia "
    "theo thời gian, không xáo trộn: 70% đầu làm tập huấn luyện, 15% tiếp theo làm tập kiểm định, 15% cuối làm tập "
    "kiểm thử. Bộ chuẩn hóa chỉ học (fit) trên tập huấn luyện rồi áp dụng (transform) cho hai tập còn lại, để thông "
    "tin của tương lai không rò rỉ vào mô hình."
)
table(
    ["Mô hình", "Phương pháp", "Công thức", "Fit trên"],
    [
        [
            "XGBoost",
            "Z-score (StandardScaler) cho 19 đặc trưng",
            "x′ = (x − μ_train) / σ_train",
            "Tập huấn luyện",
        ],
        [
            "GRU",
            "Min-Max (MinMaxScaler) cho 8 đặc trưng và biến mục tiêu",
            "x′ = (x − min_train) / (max_train − min_train)",
            "Tập huấn luyện",
        ],
        [
            "ARIMA(1,1,1)",
            "Không co giãn; lấy sai phân bậc 1 để chuỗi dừng",
            "Δy_t = y_t − y_{t−1}",
            "—",
        ],
        [
            "Random Forest",
            "Không co giãn (cây quyết định bất biến với phép co giãn đơn điệu)",
            "—",
            "—",
        ],
    ],
    [16, 34, 32, 18],
    "Phương pháp chuẩn hóa theo từng mô hình.",
)
code(
    [
        "def _fit_train_scalers(featured: pd.DataFrame) -> tuple[MinMaxScaler, MinMaxScaler]:",
        '    """Fit feature and target scalers once, using training rows only."""',
        '    train_rows = featured["split"].eq("train")',
        "    feature_scaler, target_scaler = MinMaxScaler(), MinMaxScaler()",
        "    feature_scaler.fit(featured.loc[train_rows, FEATURE_LIST])",
        '    target_scaler.fit(featured.loc[train_rows, ["close"]].to_numpy())',
        "    return feature_scaler, target_scaler",
    ],
    "services/training/train_gru.py: bộ chuẩn hóa chỉ học trên tập huấn luyện.",
)
img(
    f"{UI}/ui_13_chuan_hoa_du_lieu.png",
    "Phương pháp chuẩn hóa và quy tắc chống rò rỉ dữ liệu trên giao diện.",
    420,
)

# X.3 ──────────────────────────────────────────────────────────────────
h2("X.3. Thống kê và trực quan hóa dữ liệu")
h3("X.3.1. Bảng thông số thống kê của dữ liệu")
p(
    "Màn hình “Dữ liệu & Phân tích” hiển thị bảng thống kê mô tả của toàn bộ dữ liệu đã làm sạch, tính trực tiếp "
    "bằng SQL trên market.ohlcv (API /api/v1/stats). RSI và MACD là giá trị tại nến gần nhất, cùng công thức và cùng "
    "lượng lịch sử với biểu đồ nên hai nơi luôn hiển thị cùng giá trị. Giá cổ phiếu tính theo nghìn đồng, giá crypto "
    "theo USDT."
)


def vol_range(rows) -> str:
    values = [r["return_std_pct"] for r in rows if r["return_std_pct"] is not None]
    return f"{num(min(values), 1)}–{num(max(values), 1)}%"


def stat_row(s):
    unit = "$" if s["asset_class"] == "crypto" else ""
    return [
        s["ticker"],
        num(s["bars"], 0),
        unit + num(s["lowest_low"]),
        unit + num(s["highest_high"]),
        f"{unit}{num(s['mean_close'])} ± {num(s['std_close'])}",
        unit + num(s["last_close"]),
        ("+" if (s["change_pct"] or 0) >= 0 else "") + num(s["change_pct"]) + "%",
        vol(s["mean_volume"]),
        num(s["return_std_pct"]) + "%",
        num(s["rsi_14"], 1),
        f"{num(s['macd'], 3)} / {num(s['macd_signal'], 3)}",
    ]


head = [
    "Mã",
    "Số nến",
    "Thấp nhất",
    "Cao nhất",
    "Trung bình ± σ",
    "Giá cuối",
    "Thay đổi",
    "KL TB",
    "Biến động",
    "RSI 14",
    "MACD / Signal",
]
w11 = [8, 6, 9, 9, 13, 9, 8, 8, 8, 6, 16]
table(
    head,
    [stat_row(s) for s in stocks],
    w11,
    f"Thống kê mô tả 15 cổ phiếu, khung 1 ngày ({day(stocks[0]['first_ts'])} – {day(max(s['last_ts'] for s in stocks))}).",
    size=15,
    right=list(range(1, 11)),
)
table(
    head,
    [stat_row(s) for s in crypto_1d],
    w11,
    f"Thống kê mô tả 10 cặp crypto, khung 1 ngày (tới {day(max(s['last_ts'] for s in crypto_1d))}).",
    size=15,
    right=list(range(1, 11)),
)
p(
    "Ý nghĩa các cột: Thay đổi là % chênh giữa giá đóng cửa nến cuối và nến đầu; Biến động là độ lệch chuẩn của lợi "
    "suất giữa hai nến liên tiếp — crypto ("
    + vol_range(crypto_1d)
    + ") biến động mạnh hơn cổ phiếu ("
    + vol_range(stocks)
    + "); RSI ≥ 70 là vùng quá mua, "
    "≤ 30 là vùng quá bán; MACD lớn hơn đường Signal cho thấy động lượng tăng."
)
img(
    f"{UI}/ui_03_bang_thong_so_du_lieu.png",
    "Bảng thông số dữ liệu trên giao diện (25 mã).",
)

h3("X.3.2. Chỉ báo kỹ thuật dùng để phân tích biến động")
indicator_table = table(
    ["Chỉ báo", "Công thức", "Cách đọc"],
    [
        [
            "SMA 20 / SMA 50",
            "Trung bình cộng giá đóng cửa 20 / 50 nến gần nhất",
            "Giá > SMA 20 > SMA 50: xu hướng tăng; ngược lại: xu hướng giảm",
        ],
        [
            "RSI 14",
            "RSI = 100 − 100 / (1 + RS), RS = trung bình mức tăng / trung bình mức giảm (trung bình lũy thừa 14 nến)",
            "≥ 70 quá mua, ≤ 30 quá bán",
        ],
        [
            "MACD (12, 26, 9)",
            "MACD = EMA12 − EMA26; Signal = EMA9 của MACD; Histogram = MACD − Signal",
            "MACD cắt lên Signal: động lượng tăng; cắt xuống: động lượng giảm",
        ],
    ],
    [16, 50, 34],
    "Chỉ báo kỹ thuật trên dashboard (services/inference/analytics.py, dùng chung công thức với pipeline huấn luyện).",
)

h3("X.3.3. Dashboard phân tích sự biến động của dữ liệu")
p(
    "Dashboard gồm bốn tầng dùng chung một trục thời gian và một thanh thu phóng: (1) biểu đồ nến OHLC kèm SMA 20 và "
    "SMA 50; (2) khối lượng giao dịch, tô xanh/đỏ theo phiên tăng/giảm; (3) RSI 14 với hai ngưỡng 30 và 70; "
    "(4) MACD, đường Signal và histogram. Khung bên phải hiển thị chỉ số tại nến gần nhất, thống kê trong cửa sổ đang "
    "xem và phần diễn giải tự động theo các quy tắc ở "
    + indicator_table
    + ". Người dùng chọn mã, khung thời gian (1 ngày / 1 giờ) "
    "và số nến hiển thị (120 – 1.000)."
)
img(
    f"{UI}/ui_04_dashboard_phan_tich_ACB.png",
    "Dashboard phân tích ACB, khung 1 ngày, 250 phiên gần nhất.",
)
img(
    f"{UI}/ui_05_dashboard_phan_tich_BTC_1h.png",
    "Dashboard phân tích BTCUSDT, khung 1 giờ.",
)
p(
    "Ví dụ đọc biểu đồ ACB: giá tăng mạnh từ cuối tháng 5/2026 kèm khối lượng tăng đột biến; giá đang nằm trên SMA 20 và "
    "SMA 20 nằm trên SMA 50 (xu hướng tăng ngắn hạn), RSI 14 ở vùng trung tính, còn MACD đã nằm dưới đường Signal "
    "cho thấy động lượng tăng đang yếu dần."
)

h3("X.3.4. Tóm tắt")
bl(
    "Thu thập: tự động theo lịch cho 25 mã từ hai nguồn, có nhật ký từng tác vụ; dữ liệu lịch sử nạp bằng backfill/snapshot."
)
bl(
    "Tổ chức: tách dữ liệu thô và dữ liệu sạch, khóa chính và ràng buộc ở tầng cơ sở dữ liệu, hypertable TimescaleDB."
)
bl(
    "Làm sạch: bốn bước chuẩn hóa UTC → loại trùng → điền phiên thiếu → gắn cờ outlier, có số liệu đo trên dữ liệu thật."
)
bl(
    "Chuẩn hóa: Z-score / Min-Max theo từng mô hình, chỉ học trên tập huấn luyện, chia dữ liệu theo thời gian."
)
bl(
    "Thống kê & dashboard: bảng thông số 25 mã và dashboard 4 tầng (nến, khối lượng, RSI, MACD) chạy trên dữ liệu thật."
)

out = ROOT / "reports" / "src" / "chx.json"
out.write_text(
    json.dumps({"blocks": blocks}, ensure_ascii=False, indent=1), encoding="utf-8"
)
print("written", out, len(blocks), "blocks;", counters)
