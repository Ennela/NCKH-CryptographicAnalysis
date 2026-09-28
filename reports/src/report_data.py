"""Build report.json — the content of the V2 progress report.

Numbers come from all_results.csv and from the repository itself, so the
document regenerates rather than being retyped.
"""

from __future__ import annotations

import json
import os
import sys

import pandas as pd
from PIL import Image

import report_part2

S = sys.argv[1] if len(sys.argv) > 1 else "."
FIG = os.path.join(S, "fig")

NAME = {
    "arima": "ARIMA",
    "xgboost": "XGBoost",
    "random_forest": "Random Forest",
    "gru": "GRU v2",
}
ORDER = [
    "ACB 1d",
    "FPT 1d",
    "HPG 1d",
    "VCB 1d",
    "VNM 1d",
    "BTCUSDT 1d",
    "ETHUSDT 1d",
    "SOLUSDT 1d",
    "BTCUSDT 1h",
]

df = pd.read_csv(f"{S}/all_results.csv")
df["key"] = df["symbol"] + " " + df["timeframe"]


def num(x, d=4):
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(x):
    return f"{x:+.2f}".replace(".", ",") + " %"


B = []


def add(t, **kw):
    B.append({"t": t, **kw})


def h1(x):
    add("h1", x=x)


def h2(x):
    add("h2", x=x)


def h3(x):
    add("h3", x=x)


def p(x, **kw):
    add("p", x=x, **kw)


def bl(x, lvl=0):
    add("b", x=x, lvl=lvl)


def nb(x):
    add("n", x=x)


def note(text, title=None, kind="info"):
    add("callout", text=text, title=title, kind=kind)


def code(lines, caption=None):
    add("code", lines=lines, caption=caption)


def table(head, rows, w, caption=None, right=None, size=18):
    add(
        "table",
        head=head,
        rows=rows,
        w=w,
        caption=caption,
        right=right or [],
        size=size,
    )


def img(name, caption, width=640):
    path = os.path.join(FIG, name)
    with Image.open(path) as im:
        ratio = im.height / im.width
    add("img", file=f"fig/{name}", caption=caption, width=width, ratio=ratio)


def shot(name, caption, width=560):
    """Screenshot block — skipped silently when the capture is not on disk."""
    path = os.path.join(S, "shots", name)
    if not os.path.exists(path):
        return False
    with Image.open(path) as im:
        ratio = im.height / im.width
    add("img", file=f"shots/{name}", caption=caption, width=width, ratio=ratio)
    return True


# ═══════════════════════════════════════════════════════════════════
# Chương 1
# ═══════════════════════════════════════════════════════════════════
h1("Chương 1. Giới thiệu")

h2("1.1. Bối cảnh và định hướng của đề tài")
p(
    "Đề tài xây dựng một hệ thống thông tin thu thập, phân tích trực quan và dự báo giá cổ phiếu Việt Nam "
    "(nguồn vnstock) và tiền mã hóa (nguồn Binance). Có một điểm cần nói rõ ngay từ đầu vì nó chi phối toàn "
    "bộ cách tổ chức báo cáo này."
)
p(
    [
        {
            "t": "Trọng tâm của đề tài là kỹ thuật phần mềm, không phải nghiên cứu thuật toán học máy. ",
            "b": True,
        },
        {
            "t": "Mô hình dự báo ở đây đóng vai trò một thành phần được tích hợp vào hệ thống — nó phải được huấn "
            "luyện lại được, phiên bản hóa được, phục vụ được qua API với độ trễ chấp nhận được, và kết quả "
            "của nó phải kiểm chứng được. Phần lớn khối lượng công việc và phần lớn rủi ro của dự án nằm ở "
            "những yêu cầu đó, chứ không nằm ở việc chọn một kiến trúc mạng nơ-ron."
        },
    ]
)
p("Cách đặt vấn đề này dẫn tới ba nhóm câu hỏi kỹ thuật mà báo cáo sẽ trả lời:")
nb(
    "Làm thế nào để một đường ống dữ liệu thị trường chạy tự động, chịu được lỗi mạng và giới hạn tần suất "
    "của API bên thứ ba, mà vẫn cho ra dữ liệu nhất quán để huấn luyện?"
)
nb(
    "Làm thế nào để đưa một mô hình từ máy của người huấn luyện vào một dịch vụ đang chạy, sao cho phiên bản "
    "đang phục vụ luôn xác định được là phiên bản nào, huấn luyện từ dữ liệu nào, và tái lập lại được?"
)
nb(
    "Làm thế nào để quy trình phát triển (Agile + Git + CI) ngăn được lỗi trước khi lỗi vào nhánh chính, "
    "trong điều kiện nhóm sinh viên vừa học vừa làm và có sự hỗ trợ của công cụ AI?"
)

h2("1.2. Mục tiêu")
p(
    "Mục tiêu tổng quát: xây dựng và đánh giá thử nghiệm một hệ thống web hoàn chỉnh có khả năng thu thập tự "
    "động, phân tích trực quan và dự báo giá, đồng thời ghi nhận được hiệu quả của quy trình Agile khi quản "
    "lý một dự án phần mềm có thành phần học máy."
)
p(
    "Mục tiêu cụ thể được cụ thể hóa thành các yêu cầu chức năng và phi chức năng đo được ở Chương 2, và "
    "được đối chiếu lại ở Chương 9."
)

h2("1.3. Phạm vi và giới hạn")
table(
    ["Trong phạm vi", "Ngoài phạm vi (giai đoạn này)"],
    [
        [
            "Dữ liệu OHLCV khung 1 ngày (cổ phiếu VN) và 1 giờ + 1 ngày (crypto), thu thập theo lô có lịch",
            "Dữ liệu thời gian thực qua WebSocket; dữ liệu tin tức và phân tích cảm xúc",
        ],
        [
            "Dự báo giá đóng cửa kế tiếp (horizon = 1), suy rộng nhiều bước bằng cách lặp",
            "Dự báo khoảng tin cậy, phân loại xu hướng, backtesting chiến lược giao dịch",
        ],
        [
            "Bốn mô hình: ARIMA, XGBoost, Random Forest, GRU; baseline Naive bắt buộc",
            "Transformer / Temporal Fusion; LSTM đã được loại khỏi phạm vi",
        ],
        [
            "Web app: danh sách mã, biểu đồ lịch sử, dự báo, giải thích SHAP",
            "Tài khoản người dùng, danh mục theo dõi, cảnh báo giá",
        ],
        [
            "MLOps: theo dõi thí nghiệm, đăng ký mô hình, cổng kiểm định kết quả",
            "Huấn luyện lại tự động theo lịch, kiểm thử A/B mô hình trên môi trường thật",
        ],
    ],
    [50, 50],
)
note(
    [
        "Hệ thống là sản phẩm nghiên cứu, không phải công cụ khuyến nghị đầu tư. Mọi kết quả dự báo trong báo "
        "cáo được trình bày kèm baseline và kèm giới hạn; nhóm không đưa ra bất kỳ cam kết nào về khả năng "
        "sinh lợi."
    ],
    "Tuyên bố phạm vi",
    "warn",
)

h2("1.4. Phương pháp thực hiện")
p(
    "Dự án áp dụng Scrum với sprint hai tuần, nhánh Git ba tầng (main ← develop ← feature/*), mọi thay đổi "
    "đi qua Pull Request có kiểm thử tự động. Quy tắc làm việc — bao gồm cả quy tắc sử dụng công cụ AI — được "
    "khóa trong một tệp duy nhất ở gốc repo (AGENTS.md) và được cưỡng chế bằng pre-commit và CI thay vì bằng "
    "nhắc nhở. Chi tiết ở Chương 6 và Chương 7."
)

h2("1.5. Hiện trạng tại thời điểm báo cáo")
table(
    ["Chỉ số", "Giá trị", "Ghi chú"],
    [
        [
            "Mã nguồn",
            "≈ 22.600 dòng / 88 tệp",
            "Python (5 gói) + TypeScript (frontend)",
        ],
        [
            "Dịch vụ",
            "3 dịch vụ backend + 1 frontend",
            "ingestion, training, inference, Next.js",
        ],
        [
            "Container khi chạy",
            "9",
            "8 dịch vụ thường trực + 1 container huấn luyện theo tác vụ",
        ],
        [
            "Cơ sở dữ liệu",
            "3 schema / 14 bảng",
            "4 bảng đang được ghi/đọc, 10 bảng thuộc thiết kế mở rộng",
        ],
        ["API", "5 endpoint", "1 công khai (health) + 4 yêu cầu API key"],
        [
            "Kiểm thử tự động",
            "17 tệp test",
            "chạy trong CI cùng dịch vụ TimescaleDB thật",
        ],
        ["Pull Request đã hợp nhất", "45", "CI bốn công đoạn bắt buộc xanh"],
        [
            "Dữ liệu đã khóa",
            "192.740 dòng OHLCV / 25 mã",
            "15 cổ phiếu VN + 10 cặp crypto, ~2 năm",
        ],
        [
            "Thí nghiệm đã ghi nhận",
            "36 MLflow run / 9 bộ dữ liệu",
            "4 mô hình × 9 tổ hợp mã–khung thời gian",
        ],
    ],
    [24, 26, 50],
    "Bảng 1.1. Quy mô hệ thống tại ngày 22/09/2026 (nhánh develop, commit 55ee8f1).",
)

h2("1.6. Cấu trúc báo cáo")
p(
    "Chương 2 phân tích yêu cầu. Chương 3 trình bày thiết kế hệ thống — phần trọng tâm của báo cáo này. "
    "Chương 4 trình bày hiện thực hóa kèm mã nguồn. Chương 5 trình bày cách một mô hình học máy được tích hợp "
    "vào hệ thống như một thành phần phần mềm. Chương 6 và 7 nói về kiểm thử, CI/CD và quy trình Agile. "
    "Chương 8 trình bày kết quả thực nghiệm. Chương 9 đối chiếu với kế hoạch ban đầu và nêu công việc còn lại."
)

# ═══════════════════════════════════════════════════════════════════
# Chương 2
# ═══════════════════════════════════════════════════════════════════
h1("Chương 2. Phân tích yêu cầu")

h2("2.1. Tác nhân")
table(
    ["Tác nhân", "Mô tả", "Quyền"],
    [
        [
            "Người xem",
            "Nhà đầu tư cá nhân hoặc sinh viên quan tâm dữ liệu thị trường; dùng giao diện web",
            "Chỉ đọc: xem mã, biểu đồ, chạy dự báo, xem giải thích",
        ],
        [
            "Thành viên nhóm nghiên cứu",
            "Người vận hành hệ thống: nạp dữ liệu, huấn luyện, đăng ký mô hình, chạy benchmark",
            "Toàn quyền qua dòng lệnh trong container",
        ],
        [
            "Celery Beat (tác nhân hệ thống)",
            "Bộ lập lịch kích hoạt thu thập và làm sạch dữ liệu theo crontab",
            "Ghi vào lớp dữ liệu thô và dữ liệu sạch",
        ],
    ],
    [22, 44, 34],
)
img("d5_use_case.png", "Hình 2.1 — Biểu đồ ca sử dụng của hệ thống.", 660)

h2("2.2. Yêu cầu chức năng")
p(
    "Mỗi yêu cầu dưới đây gắn với vị trí hiện thực hóa trong mã nguồn, để việc nghiệm thu có thể kiểm chứng "
    "trực tiếp chứ không dựa trên mô tả."
)
table(
    ["Mã", "Yêu cầu chức năng", "Hiện thực tại", "Trạng thái"],
    [
        [
            "FR-01",
            "Thu thập OHLCV cổ phiếu VN theo lịch",
            "services/ingestion/adapters/vnstock_adapter.py",
            "Xong",
        ],
        [
            "FR-02",
            "Thu thập OHLCV crypto theo lịch",
            "services/ingestion/adapters/binance_adapter.py",
            "Xong",
        ],
        [
            "FR-03",
            "Làm sạch, chuẩn hóa UTC, khử trùng lặp",
            "services/ingestion/tasks.py",
            "Xong",
        ],
        [
            "FR-04",
            "Tách lưu trữ dữ liệu thô và dữ liệu sạch",
            "market.ohlcv_raw / market.ohlcv",
            "Xong",
        ],
        [
            "FR-05",
            "Xuất và nạp snapshot dữ liệu có fingerprint",
            "scripts/export_dataset_snapshot.py, import_dataset_snapshot.py",
            "Xong",
        ],
        [
            "FR-06",
            "Huấn luyện bốn mô hình qua entrypoint độc lập",
            "services/training/train_{arima,xgboost,random_forest,gru}.py",
            "Xong",
        ],
        [
            "FR-07",
            "Ghi nhận thí nghiệm: tham số, chỉ số, artifact",
            "services/training/mlflow_utils.py",
            "Xong",
        ],
        ["FR-08", "Đăng ký và phiên bản hóa mô hình", "MLflow Model Registry", "Xong"],
        [
            "FR-09",
            "So sánh bốn mô hình trên cùng một tập kiểm tra",
            "services/training/benchmark.py",
            "Xong (xem §5.5)",
        ],
        ["FR-10", "API dự báo nhiều bước cho một mã", "POST /api/v1/predict", "Xong"],
        [
            "FR-11",
            "API liệt kê mô hình đã đăng ký kèm chỉ số",
            "GET /api/v1/models",
            "Xong",
        ],
        [
            "FR-12",
            "API giải thích mức ảnh hưởng đặc trưng (SHAP)",
            "GET /api/v1/explain",
            "Xong",
        ],
        [
            "FR-13",
            "Giao diện danh sách mã và biểu đồ lịch sử",
            "frontend/app/page.tsx, symbols/page.tsx",
            "Xong",
        ],
        [
            "FR-14",
            "Giao diện dự báo và so sánh chỉ số mô hình",
            "frontend/app/forecast/page.tsx",
            "Xong",
        ],
        [
            {
                "c": [
                    "FR-15",
                    "Giao diện quản trị và nhật ký hệ thống",
                    "—",
                    "Chưa làm",
                ],
                "fill": "FDF3E3",
            }
        ][0],
        [
            {
                "c": [
                    "FR-16",
                    "Lưu vết mỗi dự báo vào cơ sở dữ liệu",
                    "services/inference/main.py::_persist_predictions",
                    "Một phần (xem §3.4)",
                ],
                "fill": "FDF3E3",
            }
        ][0],
    ],
    [8, 36, 38, 18],
    "Bảng 2.1. Yêu cầu chức năng và trạng thái hiện thực hóa.",
)

h2("2.3. Yêu cầu phi chức năng")
table(
    ["Mã", "Yêu cầu", "Tiêu chí đo", "Trạng thái"],
    [
        [
            "NFR-01",
            "Hiệu năng API dự báo",
            "p95 ≤ 2 giây cho một yêu cầu đơn lẻ",
            "Chưa đo chính thức; quan sát khi demo 0,3–0,5 s",
        ],
        [
            "NFR-02",
            "Bảo mật tối thiểu",
            "API key bắt buộc, giới hạn tần suất, kiểm tra đầu vào theo danh sách trắng",
            "Xong",
        ],
        [
            "NFR-03",
            "Không lộ bí mật trong mã nguồn",
            "gitleaks chạy ở pre-commit; chỉ commit .env.example",
            "Xong",
        ],
        [
            "NFR-04",
            "Khả năng tái lập thí nghiệm",
            "Seed cố định, chia dữ liệu theo thời gian, scaler chỉ fit trên train, kết quả có checksum",
            "Xong",
        ],
        [
            "NFR-05",
            "Khả chuyển môi trường",
            "Dựng toàn hệ thống bằng một lệnh trên máy sạch",
            "Xong",
        ],
        [
            "NFR-06",
            "Chất lượng mã nguồn",
            "ruff check + ruff format + pytest xanh mới được hợp nhất",
            "Xong (CI cưỡng chế)",
        ],
        [
            "NFR-07",
            "Khả năng quan sát",
            "Log có cấu trúc, endpoint health, theo dõi lỗi bằng Sentry",
            "Một phần — bảng ops.job_log chưa có luồng ghi",
        ],
        ["NFR-08", "Độ tin cậy thu thập", "Tỷ lệ job thành công ≥ 95 %", "Chưa đo"],
    ],
    [8, 22, 40, 30],
    "Bảng 2.2. Yêu cầu phi chức năng.",
)

h2("2.4. Đặc tả hai ca sử dụng trọng tâm")
h3("UC-03 — Chạy dự báo cho một mã")
table(
    ["Mục", "Nội dung"],
    [
        ["Tác nhân chính", "Người xem"],
        [
            "Tiền điều kiện",
            "Mã đã có dữ liệu OHLCV trong market.ohlcv; đã có ít nhất một phiên bản mô hình tương ứng trong MLflow Registry",
        ],
        [
            "Luồng chính",
            "1. Người xem chọn mã, mô hình và số bước dự báo trên trang Forecast.\n"
            "2. Frontend gửi POST /api/v1/predict kèm header X-API-Key.\n"
            "3. Dịch vụ inference xác thực khóa và kiểm tra giới hạn tần suất.\n"
            "4. Dịch vụ tra cache Redis; nếu trúng thì trả ngay kết quả.\n"
            "5. Nếu trượt cache: nạp lịch sử OHLCV gần nhất từ cơ sở dữ liệu.\n"
            "6. Nạp phiên bản mô hình mới nhất từ Registry (giữ lại trong RAM cho lần sau).\n"
            "7. Dựng đặc trưng đúng hợp đồng của mô hình và sinh dự báo cho từng bước.\n"
            "8. Ghi cache 300 giây và trả danh sách (thời điểm đích, giá trị dự báo).\n"
            "9. Frontend vẽ biểu đồ nến kèm đường dự báo.",
        ],
        [
            "Luồng thay thế",
            "3a. Thiếu hoặc sai API key → 401.  3b. Vượt giới hạn tần suất → 429.\n"
            "5a. Không đủ số nến tối thiểu cho mô hình → 400 kèm thông báo nêu rõ số nến cần.\n"
            "6a. Mô hình chưa được đăng ký → 503 kèm hướng dẫn chạy entrypoint huấn luyện.",
        ],
        [
            "Hậu điều kiện",
            "Kết quả được trả về và (khi có bản ghi phiên bản mô hình trong CSDL) được lưu vào ml.prediction",
        ],
    ],
    [18, 82],
    "Bảng 2.3. Đặc tả ca sử dụng UC-03.",
)

h3("UC-08 — Huấn luyện và đăng ký một mô hình")
table(
    ["Mục", "Nội dung"],
    [
        ["Tác nhân chính", "Thành viên nhóm nghiên cứu"],
        [
            "Tiền điều kiện",
            "Snapshot dữ liệu đã được nạp và vượt qua kiểm tra hợp đồng (fingerprint khớp)",
        ],
        [
            "Luồng chính",
            "1. Thành viên chạy entrypoint tương ứng với mô hình mình sở hữu, truyền mã và khung thời gian.\n"
            "2. Entrypoint gọi assert_locked_dataset() — dừng ngay nếu dữ liệu không khớp hợp đồng.\n"
            "3. Nạp chuỗi liên tục, chia theo thời gian 70/15/15, fit scaler chỉ trên phần train.\n"
            "4. Huấn luyện với seed cố định; dùng tập validation để dừng sớm hoặc chọn cấu hình.\n"
            "5. Đánh giá một lần duy nhất trên tập test; tính đồng thời baseline Naive.\n"
            "6. Ghi MLflow run: tham số, chỉ số, artifact mô hình, prediction CSV, mã băm manifest.\n"
            "7. Đăng ký vào Registry theo quy ước {SYMBOL}_{timeframe}_{model}.",
        ],
        [
            "Luồng thay thế",
            "2a. Fingerprint không khớp → dừng và báo lỗi, không tạo run rác trong MLflow.",
        ],
        [
            "Hậu điều kiện",
            "Có một phiên bản mô hình mới trong Registry, kèm đầy đủ dấu vết để tái lập",
        ],
    ],
    [18, 82],
    "Bảng 2.4. Đặc tả ca sử dụng UC-08.",
)

# ═══════════════════════════════════════════════════════════════════
# Chương 3
# ═══════════════════════════════════════════════════════════════════
h1("Chương 3. Thiết kế hệ thống")

h2("3.1. Quan điểm kiến trúc")
p(
    "Hệ thống được tách thành ba dịch vụ backend độc lập thay vì một ứng dụng đơn khối. Lý do không phải là "
    "để theo mốt microservices, mà xuất phát từ ba khác biệt cụ thể giữa các phần:"
)
table(
    ["Tiêu chí", "Ingestion", "Training", "Inference"],
    [
        [
            "Đặc tính tải",
            "Nghẽn ở I/O mạng, chạy theo lịch",
            "Nghẽn ở CPU, chạy theo đợt dài",
            "Độ trễ thấp, chạy thường trực",
        ],
        [
            "Phụ thuộc nặng",
            "ccxt, vnstock",
            "torch, xgboost, statsmodels, optuna, shap",
            "torch, xgboost, statsmodels (chỉ để nạp mô hình)",
        ],
        [
            "Ảnh hưởng khi lỗi",
            "Chậm dữ liệu, không ảnh hưởng người dùng đang xem",
            "Không ảnh hưởng hệ thống đang chạy",
            "Người dùng thấy lỗi ngay",
        ],
        ["Nhịp thay đổi mã", "Thấp", "Cao (bốn người cùng sửa)", "Trung bình"],
    ],
    [18, 26, 28, 28],
    "Bảng 3.1. Cơ sở của việc tách dịch vụ.",
)
p(
    "Hệ quả thực tế: một đợt huấn luyện nặng không làm chậm API dự báo; việc bốn thành viên cùng sửa mã "
    "huấn luyện không đụng tới dịch vụ đang phục vụ; và image phục vụ không phải mang theo Optuna hay SHAP."
)

h2("3.2. Kiến trúc triển khai")
img(
    "d1_kien_truc.png",
    "Hình 3.1 — Kiến trúc triển khai; mỗi khối trong khung đứt là một container.",
    665,
)
table(
    ["Container", "Vai trò", "Cổng", "Phụ thuộc khởi động"],
    [
        [
            "forecast_postgres",
            "PostgreSQL 16 + TimescaleDB, lưu toàn bộ dữ liệu thị trường",
            "5432",
            "—",
        ],
        ["forecast_redis", "Broker cho Celery và cache kết quả dự báo", "6379", "—"],
        [
            "forecast_mlflow",
            "Máy chủ theo dõi thí nghiệm và Model Registry",
            "5000",
            "—",
        ],
        [
            "forecast_ingestion",
            "FastAPI: health và kích hoạt thu thập thủ công",
            "8001",
            "postgres, redis",
        ],
        [
            "forecast_celery_worker",
            "Thực thi tác vụ thu thập và làm sạch",
            "—",
            "postgres, redis",
        ],
        ["forecast_celery_beat", "Bộ lập lịch theo crontab", "—", "postgres, redis"],
        [
            "forecast_training",
            "Chạy các entrypoint huấn luyện theo tác vụ",
            "—",
            "postgres, mlflow",
        ],
        [
            "forecast_inference",
            "FastAPI: API dự báo cho frontend",
            "8000",
            "postgres, redis, mlflow",
        ],
        ["forecast_frontend", "Ứng dụng Next.js", "3000", "inference"],
    ],
    [22, 44, 10, 24],
    "Bảng 3.2. Danh mục container và vai trò.",
)

h2("3.3. Đường ống dữ liệu")
img(
    "d2_duong_ong.png",
    "Hình 3.2 — Đường ống dữ liệu, từ API bên thứ ba tới biểu đồ trên trình duyệt.",
    665,
)
p(
    "Đường ống có một điểm đặc biệt so với thiết kế thông thường: giữa dữ liệu vận hành và dữ liệu dùng để "
    "nghiên cứu có một ranh giới cứng. Bước 5 xuất toàn bộ dữ liệu sạch ra một snapshot bất biến kèm "
    "fingerprint SHA-256; mọi entrypoint huấn luyện chỉ đọc snapshot đó, không đọc cơ sở dữ liệu đang chạy. "
    "Nhờ vậy việc thu thập tiếp dữ liệu mới không làm thay đổi tập huấn luyện phía sau lưng người làm thí "
    "nghiệm — một lỗi rất dễ mắc và rất khó phát hiện."
)

h2("3.4. Thiết kế cơ sở dữ liệu")
img(
    "d3_erd.png",
    "Hình 3.3 — Sơ đồ quan hệ thực thể; màu viền phân biệt phần đang dùng và phần thuộc thiết kế mở rộng.",
    665,
)
p(
    "Cơ sở dữ liệu được chia làm ba schema theo trách nhiệm: market (dữ liệu thị trường), ml (vòng đời mô "
    "hình) và ops (vận hành). Hai quyết định đáng chú ý:"
)
bl(
    [
        {"t": "Bảng market.ohlcv là hypertable của TimescaleDB", "b": True},
        {
            "t": ", phân mảnh theo thời gian, khóa chính (symbol_id, timeframe, ts) và được ghi bằng upsert. "
            "Chạy lại một job thu thập không bao giờ sinh bản ghi trùng — tính chất này là điều kiện cần để "
            "có thể retry an toàn khi API bên thứ ba lỗi."
        },
    ]
)
bl(
    [
        {
            "t": "Bảng ml.prediction có ràng buộc CHECK (feature_asof_ts < target_ts)",
            "b": True,
        },
        {
            "t": ". Đây là cách chặn look-ahead bias ở tầng thấp nhất: kể cả khi mã Python có lỗi logic, cơ sở dữ "
            "liệu vẫn từ chối một dự báo dùng thông tin của tương lai."
        },
    ]
)
note(
    [
        "Nhóm bảng ml.* hiện chưa có luồng ghi: vai trò lưu phiên bản mô hình, tham số và chỉ số đang do "
        "MLflow đảm nhiệm (xem ADR-03). Hệ quả cụ thể: đoạn mã ghi ml.prediction trong dịch vụ inference luôn "
        "bỏ qua vì không tìm thấy bản ghi ml.model_version tương ứng. Đây là nợ kỹ thuật đã được ghi nhận, "
        "không phải phần bị bỏ sót."
    ],
    "Ghi chú trung thực về phần chưa hoàn thiện",
    "warn",
)

h2("3.5. Thiết kế API")
table(
    ["Phương thức", "Đường dẫn", "Xác thực", "Chức năng"],
    [
        ["GET", "/health", "Không", "Kiểm tra sống, phục vụ healthcheck của Docker"],
        [
            "POST",
            "/api/v1/predict",
            "X-API-Key + giới hạn tần suất",
            "Dự báo 1–30 bước cho một mã và một mô hình",
        ],
        [
            "GET",
            "/api/v1/models",
            "X-API-Key",
            "Liệt kê mô hình đã đăng ký kèm MAE/RMSE/MAPE",
        ],
        [
            "GET",
            "/api/v1/explain",
            "X-API-Key",
            "Mức ảnh hưởng đặc trưng (SHAP) của mô hình cây",
        ],
        ["GET", "/api/v1/symbols", "X-API-Key", "Danh sách mã đang theo dõi"],
        ["GET", "/api/v1/ohlcv", "X-API-Key", "Lịch sử nến cho biểu đồ"],
    ],
    [14, 26, 26, 34],
    "Bảng 3.3. Hợp đồng API của dịch vụ inference.",
)
p(
    "Đầu vào được ràng buộc bằng pydantic ngay tại biên hệ thống, theo danh sách trắng chứ không theo kiểu "
    "dữ liệu chung chung — một tham số sai trả về 422 trước khi chạm tới cơ sở dữ liệu hay mô hình:"
)
code(
    [
        'ALLOWED_MODELS = ("arima", "xgboost", "random_forest", "gru")',
        'ALLOWED_TIMEFRAMES = ("1d", "1h")',
        "",
        "class PredictRequest(BaseModel):",
        '    ticker_id: str = Field(..., description="Mã tài sản, ví dụ: FPT hoặc BTCUSDT")',
        '    model_name: str = Field(..., description="arima, xgboost, random_forest, gru")',
        '    steps: int = Field(5, ge=1, le=30, description="Số bước dự báo")',
        "    timeframe: Optional[str] = Field(None, description=\"'1d' hoặc '1h'\")",
        "",
        '    @field_validator("model_name")',
        "    @classmethod",
        "    def validate_model_name(cls, v: str) -> str:",
        "        name = v.strip().lower()",
        "        if name not in ALLOWED_MODELS:",
        '            raise ValueError(f"Model name must be one of {ALLOWED_MODELS}")',
        "        return name",
    ],
    "Mã nguồn 3.1 — shared/schemas/predict.py: hợp đồng đầu vào dùng chung cho frontend và backend.",
)
shot(
    "07_swagger.png",
    "Hình 3.5 — Tài liệu API sinh tự động từ chính mã nguồn (OpenAPI/Swagger): hợp đồng luôn khớp với "
    "cài đặt, không phải cập nhật tay.",
    600,
)

h2("3.6. Luồng xử lý một yêu cầu dự báo")
img("d4_tuan_tu.png", "Hình 3.4 — Biểu đồ tuần tự của POST /api/v1/predict.", 665)

h2("3.7. Thiết kế bảo mật")
table(
    ["Lớp", "Cơ chế", "Hành vi khi vi phạm"],
    [
        [
            "Xác thực",
            "Header X-API-Key so khớp với biến môi trường API_KEY_SECRET",
            "401 Unauthorized, ghi log cảnh báo",
        ],
        [
            "Giới hạn tần suất",
            "Bộ đếm Redis theo (API key, địa chỉ IP), cửa sổ 60 giây",
            "429 Too Many Requests",
        ],
        [
            "Kiểm tra đầu vào",
            "pydantic + danh sách trắng mã mô hình và khung thời gian",
            "422 Unprocessable Entity",
        ],
        [
            "Quản lý bí mật",
            "Chỉ .env.example nằm trong Git; gitleaks quét ở pre-commit",
            "Chặn commit tại máy lập trình viên",
        ],
        [
            "Phạm vi mạng",
            "Chỉ frontend và inference mở cổng ra ngoài; CSDL và Redis nằm trong mạng nội bộ",
            "—",
        ],
    ],
    [18, 46, 36],
    "Bảng 3.4. Các lớp bảo vệ của dịch vụ inference.",
)
p(
    "Một quyết định cần nói rõ: bộ giới hạn tần suất được thiết kế fail-open — nếu Redis chết, yêu cầu vẫn "
    "được phục vụ thay vì bị chặn. Với một hệ thống tra cứu dữ liệu công khai, mất khả năng phục vụ được coi "
    "là thiệt hại lớn hơn việc tạm thời mất khả năng giới hạn tần suất. Nếu hệ thống mở rộng sang chức năng "
    "ghi dữ liệu người dùng, lựa chọn này cần được xem lại."
)

h2("3.8. Thiết kế giao diện")
table(
    ["Màn hình", "Nội dung chính", "API sử dụng"],
    [
        [
            "Dashboard",
            "Thống kê tổng quan, bảng mã đang theo dõi kèm giá gần nhất",
            "/symbols, /ohlcv, /models",
        ],
        ["Symbols", "Danh sách đầy đủ, lọc theo loại tài sản", "/symbols, /ohlcv"],
        [
            "Forecast Model",
            "Chọn mã, mô hình, số bước; biểu đồ nến + đường dự báo; bảng mô hình đã đăng ký",
            "/ohlcv, /predict, /models",
        ],
        ["SHAP Explain", "Biểu đồ mức ảnh hưởng đặc trưng của mô hình cây", "/explain"],
        [
            {
                "c": [
                    "Quản trị / Log",
                    "Trạng thái dịch vụ, nhật ký job thu thập",
                    "chưa có",
                ],
                "fill": "FDF3E3",
            }
        ][0],
    ],
    [20, 52, 28],
    "Bảng 3.5. Bốn màn hình đã hoàn thành và một màn hình còn thiếu so với tiêu chí nghiệm thu.",
)

h2("3.9. Các quyết định kiến trúc quan trọng")
p(
    "Mục này ghi lại năm quyết định có ảnh hưởng dài hạn, theo dạng rút gọn của Architecture Decision Record: "
    "bối cảnh, quyết định, và hệ quả — kể cả hệ quả bất lợi."
)
for code_, title_, ctx, dec, good, bad in [
    (
        "ADR-01",
        "Chỉ dùng một framework học sâu (PyTorch)",
        "Tài liệu tham khảo phổ biến nhất trong lĩnh vực dùng TensorFlow/Keras; thành viên có nền tảng khác nhau.",
        "Khóa PyTorch là framework học sâu duy nhất; cấm đưa TensorFlow vào repo.",
        "Thống nhất kỹ năng, review dễ, image nhẹ hơn, tránh sao chép mã nguyên khối từ repo tham khảo.",
        "Không tận dụng trực tiếp được mã mẫu của tài liệu tham khảo; phải đọc hiểu rồi viết lại.",
    ),
    (
        "ADR-02",
        "Dùng TimescaleDB hypertable cho OHLCV",
        "Dữ liệu chuỗi thời gian tăng đều; truy vấn chủ yếu theo khoảng thời gian của một mã.",
        "Bảng market.ohlcv là hypertable phân mảnh 7 ngày, kèm continuous aggregate 1 ngày từ dữ liệu 1 giờ.",
        "Truy vấn theo khoảng nhanh, vẫn là PostgreSQL nên không phải học hệ quản trị mới.",
        "Thêm một extension phải cài trong image cơ sở dữ liệu; một số thao tác DDL bị hạn chế trên hypertable.",
    ),
    (
        "ADR-03",
        "Dùng MLflow thay cho bảng quản lý mô hình tự xây",
        "Thiết kế ban đầu có nhóm bảng ml.model / ml.model_version / ml.model_metric để tự quản lý vòng đời mô hình.",
        "Chuyển toàn bộ việc lưu run, tham số, chỉ số, artifact và phiên bản sang MLflow; giữ lại thiết kế bảng nhưng chưa hiện thực hóa.",
        "Có ngay giao diện so sánh thí nghiệm, tải lại artifact và quản lý phiên bản mà không phải viết thêm mã.",
        "Hệ thống phụ thuộc một dịch vụ ngoài; phần ml.prediction trong CSDL trở thành nhánh mã không chạy (xem §3.4).",
    ),
    (
        "ADR-04",
        "Mỗi thành viên sở hữu trọn một mô hình",
        "Kế hoạch ban đầu chia việc theo tầng kỹ thuật (một người làm feature, một người làm mô hình, một người làm inference).",
        "Chuyển sang chia theo mô hình: mỗi người phụ trách trọn gói feature + mô hình + entrypoint + test của mình.",
        "Bốn người làm song song gần như không đụng file của nhau; trách nhiệm rõ ràng khi kết quả sai.",
        "Bốn pipeline có bộ đặc trưng khác nhau, nên benchmark so sánh 'pipeline hoàn chỉnh' chứ không so sánh thuật toán trên cùng đầu vào.",
    ),
    (
        "ADR-05",
        "Khóa dữ liệu nghiên cứu bằng snapshot có fingerprint",
        "Dữ liệu trong cơ sở dữ liệu thay đổi mỗi lần job thu thập chạy; kết quả thí nghiệm vì thế không tái lập được.",
        "Xuất snapshot bất biến kèm fingerprint SHA-256 và một tệp hợp đồng; mọi entrypoint huấn luyện phải gọi assert_locked_dataset() trước khi đọc dữ liệu.",
        "Kết quả tái lập được trên máy khác, thời điểm khác; phát hiện ngay nếu ai đó vô tình đổi dữ liệu.",
        "Phải chủ động cập nhật snapshot khi muốn dùng dữ liệu mới; thêm một bước trong quy trình.",
    ),
]:
    h3(f"{code_} — {title_}")
    table(
        ["Mục", "Nội dung"],
        [
            ["Bối cảnh", ctx],
            ["Quyết định", dec],
            ["Hệ quả tích cực", good],
            ["Hệ quả bất lợi", bad],
        ],
        [18, 82],
    )

# ═══════════════════════════════════════════════════════════════════
# Chương 4–9 và phụ lục
# ═══════════════════════════════════════════════════════════════════
report_part2.build(
    {
        "h1": h1,
        "h2": h2,
        "h3": h3,
        "p": p,
        "bl": bl,
        "nb": nb,
        "note": note,
        "code": code,
        "table": table,
        "img": img,
        "shot": shot,
        "add": add,
        "num": num,
        "pct": pct,
        "df": df,
        "NAME": NAME,
        "ORDER": ORDER,
    }
)

DOC = {
    "outfile": "Bao_cao_tien_do_NCKH_V2_2026-09-22.docx",
    "title": "Hệ thống thu thập, phân tích trực quan và dự báo giá cổ phiếu Việt Nam & tiền mã hóa",
    "runningHead": "Báo cáo tiến độ — Hệ thống dự báo giá cổ phiếu & tiền mã hóa",
    "org": "ĐỀ TÀI NGHIÊN CỨU KHOA HỌC SINH VIÊN",
    "cover": [
        [
            "Nhóm thực hiện",
            "Đỗ Quang Hà (chủ nhiệm), Nguyễn Văn Kiên, Khiếu Đình Trung Nguyên,",
        ],
        ["", "Nguyễn Trọng Đại, Lê Hải Nam, Nguyễn Trọng Hiếu"],
        ["Giai đoạn", "04/2026 – 10/2026"],
        ["Kỳ báo cáo", "Lần 2 — ngày 22/09/2026"],
        ["Mã nguồn", "github.com/Ennela/NCKH-CryptographicAnalysis"],
        [
            "Phiên bản được báo cáo",
            "nhánh develop, commit 55ee8f1 (45 Pull Request đã hợp nhất)",
        ],
    ],
    "blocks": B,
}
json.dump(DOC, open(f"{S}/report.json", "w", encoding="utf-8"), ensure_ascii=False)
print("blocks:", len(B))
