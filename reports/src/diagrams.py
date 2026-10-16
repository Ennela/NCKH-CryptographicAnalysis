"""Render the system-design diagrams used by the V2 progress report.

Everything is drawn with matplotlib so the figures are deterministic, crisp at
print resolution, and regenerate from source when the design changes.
"""

from __future__ import annotations

import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Ellipse, Rectangle

OUT = sys.argv[1] if len(sys.argv) > 1 else "."

plt.rcParams["font.family"] = ["Arial", "DejaVu Sans"]

# Figures are scaled down to A4 text width in the report; enlarge every
# label so the printed result stays legible.
FS = 1.22

INK = "#1a1a19"
MUTED = "#5b5b55"
LINE = "#8a8a82"
BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN = (
    "#2a78d6",
    "#eb6834",
    "#1baf7a",
    "#eda100",
    "#e87ba4",
    "#008300",
)
TINT = {
    BLUE: "#e8f1fc",
    ORANGE: "#fdeee7",
    AQUA: "#e5f6ef",
    YELLOW: "#fcf3de",
    MAGENTA: "#fdeef3",
    GREEN: "#e6f2e6",
    LINE: "#f2f2ef",
}


def canvas(w, h, xlim, ylim):
    fig, ax = plt.subplots(figsize=(w, h), dpi=200)
    fig.patch.set_facecolor("white")
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.axis("off")
    return fig, ax


def box(
    ax, x, y, w, h, title, sub=None, color=BLUE, fs=9 * FS, radius=0.08, dashed=False
):
    """Rounded node with a bold title and optional muted subtitle."""
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle=f"round,pad=0,rounding_size={radius}",
            facecolor=TINT[color],
            edgecolor=color,
            linewidth=1.3,
            linestyle="--" if dashed else "-",
            zorder=2,
        )
    )
    cx = x + w / 2
    if sub:
        ax.text(
            cx,
            y + h - 0.30,
            title,
            ha="center",
            va="center",
            fontsize=fs,
            fontweight="bold",
            color=INK,
            zorder=3,
            linespacing=1.3,
        )
        ax.text(
            cx,
            y + (h - 0.52) / 2,
            sub,
            ha="center",
            va="center",
            fontsize=fs - 1.9,
            color=MUTED,
            zorder=3,
            linespacing=1.4,
        )
    else:
        ax.text(
            cx,
            y + h / 2,
            title,
            ha="center",
            va="center",
            fontsize=fs,
            fontweight="bold",
            color=INK,
            zorder=3,
            linespacing=1.35,
        )


def band(ax, x, y, w, h, label, color=LINE, label_at="top"):
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0,rounding_size=0.12",
            facecolor="#fafaf8",
            edgecolor=color,
            linewidth=1.0,
            linestyle=(0, (4, 3)),
            zorder=1,
        )
    )
    ax.text(
        x + 0.16,
        y + h - 0.34 if label_at == "top" else y + 0.16,
        label,
        ha="left",
        va="top" if label_at == "top" else "bottom",
        fontsize=8.5 * FS,
        fontweight="bold",
        color=MUTED,
        zorder=3,
    )


def arrow(
    ax,
    p1,
    p2,
    label=None,
    color=LINE,
    style="-|>",
    rad=0.0,
    fs=7.4 * FS,
    lab_off=(0, 0.14),
    dashed=False,
    lw=1.3,
):
    ax.add_patch(
        FancyArrowPatch(
            p1,
            p2,
            arrowstyle=style,
            mutation_scale=11,
            connectionstyle=f"arc3,rad={rad}",
            color=color,
            linewidth=lw,
            linestyle="--" if dashed else "-",
            zorder=4,
            shrinkA=1,
            shrinkB=1,
        )
    )
    if label:
        mx, my = (p1[0] + p2[0]) / 2 + lab_off[0], (p1[1] + p2[1]) / 2 + lab_off[1]
        ax.text(
            mx,
            my,
            label,
            ha="center",
            va="center",
            fontsize=fs,
            color=MUTED,
            zorder=5,
            linespacing=1.3,
            bbox=dict(
                boxstyle="round,pad=0.18",
                facecolor="white",
                edgecolor="none",
                alpha=0.92,
            ),
        )


def elbow(
    ax,
    pts,
    label=None,
    label_at=None,
    color=LINE,
    dashed=False,
    fs=7.4 * FS,
    ha="center",
):
    """Orthogonal polyline with an arrowhead on the last segment."""
    for i in range(len(pts) - 2):
        ax.add_patch(
            FancyArrowPatch(
                pts[i],
                pts[i + 1],
                arrowstyle="-",
                color=color,
                linewidth=1.3,
                linestyle="--" if dashed else "-",
                zorder=4,
            )
        )
    ax.add_patch(
        FancyArrowPatch(
            pts[-2],
            pts[-1],
            arrowstyle="-|>",
            mutation_scale=11,
            color=color,
            linewidth=1.3,
            linestyle="--" if dashed else "-",
            zorder=4,
            shrinkB=1,
        )
    )
    if label:
        lx, ly = label_at
        ax.text(
            lx,
            ly,
            label,
            ha=ha,
            va="center",
            fontsize=fs,
            color=MUTED,
            zorder=5,
            linespacing=1.3,
            bbox=dict(
                boxstyle="round,pad=0.18",
                facecolor="white",
                edgecolor="none",
                alpha=0.95,
            ),
        )


def title(ax, text, sub=None, x=0.0, y=None):
    ylim = ax.get_ylim()[1]
    ax.text(
        x,
        y if y is not None else ylim - 0.18,
        text,
        ha="left",
        va="top",
        fontsize=12.5 * FS,
        fontweight="bold",
        color=INK,
    )
    if sub:
        ax.text(
            x,
            (y if y is not None else ylim - 0.18) - 0.32,
            sub,
            ha="left",
            va="top",
            fontsize=8.6 * FS,
            color=MUTED,
        )


def save(fig, name):
    fig.savefig(
        f"{OUT}/{name}", bbox_inches="tight", pad_inches=0.12, facecolor="white"
    )
    plt.close(fig)
    print("saved", name)


# ── D1: deployment / container architecture ──────────────────────────
def d1_architecture():
    fig, ax = canvas(15, 8.4, (0, 16.4), (0, 8.7))
    title(
        ax,
        "Hình 3.1 — Kiến trúc triển khai hệ thống (9 container Docker Compose)",
        "Mũi tên chỉ chiều gọi hoặc ghi dữ liệu; số cổng kèm theo là cổng mở ra máy phát triển",
    )
    band(
        ax,
        3.15,
        2.55,
        13.05,
        4.95,
        "Docker Compose — mạng nội bộ forecast",
        label_at="bottom",
    )

    box(
        ax,
        0.25,
        5.90,
        2.55,
        0.95,
        "Vnstock API",
        "15 mã VN30\n(thư viện vnstock)",
        GREEN,
    )
    box(ax, 0.25, 4.40, 2.55, 0.95, "Binance API", "10 cặp crypto\n(ccxt REST)", GREEN)

    box(
        ax,
        3.45,
        6.30,
        2.60,
        0.95,
        "Ingestion API",
        "FastAPI :8001\nhealth + trigger tay",
        ORANGE,
    )
    box(ax, 3.45, 4.95, 2.60, 0.95, "Celery Beat", "lịch crontab\n1h / 1d", ORANGE)
    box(
        ax,
        3.45,
        3.50,
        2.60,
        0.95,
        "Celery Worker",
        "adapters + làm sạch\nretry, idempotent",
        ORANGE,
    )

    box(
        ax,
        6.75,
        5.50,
        2.70,
        1.55,
        "PostgreSQL 16\n+ TimescaleDB",
        "schema market / ml / ops\nohlcv là hypertable\n:5432",
        BLUE,
    )
    box(
        ax,
        6.75,
        3.50,
        2.70,
        1.05,
        "Redis",
        "broker Celery +\ncache dự báo  :6379",
        BLUE,
    )

    box(
        ax,
        10.15,
        5.90,
        2.60,
        1.15,
        "Training Service",
        "4 entrypoint train_*.py\nchạy theo tác vụ",
        MAGENTA,
    )
    box(
        ax,
        10.15,
        3.90,
        2.60,
        1.15,
        "MLflow Server",
        "tracking + Registry\n:5000",
        MAGENTA,
    )

    box(
        ax,
        13.45,
        5.50,
        2.60,
        1.15,
        "Inference API",
        "FastAPI :8000\n10 endpoint, API key",
        AQUA,
    )
    box(ax, 13.45, 1.35, 2.60, 1.05, "Frontend", "Next.js + ECharts\n:3000", AQUA)
    box(
        ax,
        13.45,
        0.05,
        2.60,
        0.85,
        "Người dùng — trình duyệt",
        color=YELLOW,
        fs=8.4 * FS,
    )

    elbow(
        ax,
        [(2.80, 6.20), (3.15, 6.20), (3.15, 4.10), (3.45, 4.10)],
        "OHLCV",
        (2.98, 5.62),
    )
    elbow(ax, [(2.80, 4.70), (3.15, 4.70), (3.15, 3.90), (3.45, 3.90)])
    elbow(ax, [(4.75, 4.95), (4.75, 4.45)], "kích hoạt task", (5.62, 4.70))
    elbow(ax, [(6.05, 6.75), (6.75, 6.75)], "ghi", (6.40, 6.98))
    elbow(
        ax,
        [(6.05, 4.10), (6.40, 4.10), (6.40, 6.10), (6.75, 6.10)],
        "upsert",
        (6.40, 5.30),
    )
    elbow(ax, [(6.05, 3.75), (6.75, 3.75)], "broker", (6.40, 3.26))
    elbow(ax, [(9.45, 6.40), (10.15, 6.40)], "đọc OHLCV\n+ snapshot", (9.80, 6.72))
    elbow(
        ax,
        [(11.45, 5.90), (11.45, 5.05)],
        "log params / metrics\n+ register model",
        (11.45, 5.48),
    )
    elbow(
        ax,
        [(12.75, 4.60), (13.10, 4.60), (13.10, 5.95), (13.45, 5.95)],
        "models:/…",
        (13.10, 4.90),
    )
    elbow(
        ax,
        [(8.10, 7.05), (8.10, 7.45), (14.75, 7.45), (14.75, 6.65)],
        "lịch sử OHLCV cho dự báo",
        (12.55, 7.45),
    )
    elbow(
        ax,
        [(8.10, 3.50), (8.10, 3.05), (14.20, 3.05), (14.20, 5.50)],
        "cache 300 s + rate limit",
        (11.00, 3.05),
    )
    elbow(ax, [(15.50, 2.40), (15.50, 5.50)], "REST\n+ X-API-Key", (15.50, 4.05))
    elbow(ax, [(14.20, 0.90), (14.20, 1.35)])
    save(fig, "d1_kien_truc.png")


# ── D2: data & processing pipeline ───────────────────────────────────
def d2_pipeline(
    heading: str
    | None = "Hình 3.2 — Đường ống dữ liệu từ nguồn đến màn hình người dùng",
    ohlcv_rows: str = "192.740",
    name: str = "d2_duong_ong.png",
):
    """Pipeline diagram. The V2 report uses the defaults; Chương X passes the
    live row count and no in-image heading (the Word caption carries it)."""
    fig, ax = canvas(15, 7.2, (0, 16.2), (0, 7.4))
    if heading:
        title(
            ax,
            heading,
            "Các khối viền xanh lá là ranh giới khoa học: dữ liệu bị khóa trước khi mô hình nhìn thấy, và mọi kết quả phải đi qua evaluator",
        )

    y1, y2, h, w = 5.05, 2.75, 1.15, 2.85
    xs = [0.25, 3.45, 6.65, 9.85, 13.05]
    top = [
        ("1. Thu thập", "adapter vnstock / ccxt\nchuẩn hóa 1 schema", ORANGE),
        (
            "2. market.ohlcv_raw",
            "JSONB thô, idempotent\nUNIQUE(symbol,tf,ts,source)",
            BLUE,
        ),
        ("3. Làm sạch & kiểm định", "missing / outlier\nchuẩn UTC", ORANGE),
        ("4. market.ohlcv", f"hypertable TimescaleDB\n{ohlcv_rows} dòng", BLUE),
        ("5. Snapshot khóa", "group_dataset_v1\nfingerprint SHA-256", GREEN),
    ]
    bottom = [
        ("10. Dashboard", "Next.js + ECharts\nnến + đường dự báo", AQUA),
        ("9. Inference API", "POST /predict\ncache Redis 300 s", AQUA),
        ("8. MLflow Registry", "{SYMBOL}_{tf}_{model}\nversion + artifact", MAGENTA),
        ("7. Huấn luyện", "seed 42, chia theo thời gian\n70 / 15 / 15", MAGENTA),
        ("6. Feature engineering", "XGBoost 19 · RF 18\nGRU 8 · ARIMA 1 biến", MAGENTA),
    ]
    for x, (t, s, c) in zip(xs, top):
        box(ax, x, y1, w, h, t, s, c)
    for x, (t, s, c) in zip(xs, bottom):
        box(ax, x, y2, w, h, t, s, c)

    for i in range(4):
        arrow(ax, (xs[i] + w, y1 + h / 2), (xs[i + 1], y1 + h / 2))
    arrow(
        ax,
        (xs[4] + w / 2, y1),
        (xs[4] + w / 2, y2 + h),
        "khóa dữ liệu",
        lab_off=(0.80, 0),
    )
    for i in range(4, 0, -1):
        arrow(ax, (xs[i], y2 + h / 2), (xs[i - 1] + w, y2 + h / 2))

    box(
        ax,
        6.65,
        0.35,
        6.05,
        1.35,
        "Benchmark evaluator (services.training.benchmark)",
        "dựng lại manifest chung • đối chiếu SHA-256\n"
        "nạp lại artifact • tính lại metric\n"
        "→ bằng chứng có checksum trong docs/evidence/",
        GREEN,
    )
    arrow(ax, (11.27, 2.75), (11.0, 1.7), "4 run_id", rad=-0.12, lab_off=(0.55, 0.1))
    arrow(
        ax,
        (8.07, 2.75),
        (8.4, 1.7),
        "artifact +\nprediction CSV",
        rad=0.12,
        lab_off=(-0.75, 0.05),
    )
    save(fig, name)


# ── D3: ERD ──────────────────────────────────────────────────────────
def d3_erd():
    fig, ax = canvas(15, 10.2, (0, 16.4), (0, 11.2))
    title(
        ax,
        "Hình 3.3 — Sơ đồ quan hệ thực thể (14 bảng trên 3 schema)",
        "Viền liền = đang được mã nguồn ghi/đọc (market.*, ops.*) · "
        "Viền đứt = đã thiết kế, chưa có luồng ghi (ml.*)",
    )

    placed = {}
    header, pitch, pad = 0.44, 0.29, 0.14

    def tbl(x, ytop, name, cols, color, used=True):
        """Entity box sized from its column count; returns the next free y."""
        h = header + pitch * len(cols) + pad
        w, y = 3.05, ytop - h
        ls = "-" if used else (0, (4, 3))
        lw = 1.5 if used else 1.1
        ax.add_patch(
            FancyBboxPatch(
                (x, y),
                w,
                h,
                boxstyle="round,pad=0,rounding_size=0.05",
                facecolor="white",
                edgecolor=color,
                linewidth=lw,
                linestyle=ls,
                zorder=2,
            )
        )
        ax.add_patch(
            Rectangle(
                (x, ytop - header),
                w,
                header,
                facecolor=TINT[color],
                edgecolor=color,
                linewidth=lw,
                linestyle=ls,
                zorder=3,
            )
        )
        ax.text(
            x + w / 2,
            ytop - header / 2,
            name,
            ha="center",
            va="center",
            fontsize=8.4 * FS,
            fontweight="bold",
            color=INK,
            zorder=4,
        )
        for i, c in enumerate(cols):
            ax.text(
                x + 0.12,
                ytop - header - pitch * (i + 0.5) - 0.03,
                c,
                ha="left",
                va="center",
                fontsize=7.0 * FS,
                color=INK if used else MUTED,
                zorder=4,
            )
        placed[name] = (x, y, w, h)
        return y - 0.42

    band(ax, 0.20, 1.85, 3.85, 8.05, "schema market", BLUE)
    y = 9.30
    y = tbl(0.40, y, "exchange", ["PK id", "code, name", "asset_class"], BLUE)
    y = tbl(
        0.40,
        y,
        "symbol",
        ["PK id", "FK exchange_id", "ticker, source", "asset_class, status"],
        BLUE,
    )
    y = tbl(
        0.40, y, "ohlcv_raw", ["PK id", "FK symbol_id", "ts, raw_payload JSONB"], BLUE
    )
    tbl(
        0.40,
        y,
        "ohlcv   [hypertable]",
        ["PK (symbol_id, tf, ts)", "open/high/low/close", "volume, vwap"],
        BLUE,
    )

    band(ax, 4.30, 0.45, 7.30, 9.45, "schema ml")
    y = 9.30
    y = tbl(
        4.50,
        y,
        "feature_set",
        ["PK id", "name, version", "feature_list JSONB"],
        MAGENTA,
        False,
    )
    y = tbl(
        4.50,
        y,
        "feature_value  [ht]",
        ["PK (set, symbol, tf, ts)", "features JSONB", "label"],
        MAGENTA,
        False,
    )
    y = tbl(
        4.50,
        y,
        "model_metric",
        ["PK id", "FK model_version_id", "split, metric_name, value"],
        MAGENTA,
        False,
    )
    y = tbl(
        4.50,
        y,
        "backtest_run",
        ["PK id", "FK model_version_id", "period TSTZRANGE"],
        MAGENTA,
        False,
    )
    tbl(
        4.50,
        y,
        "backtest_result",
        ["FK backtest_run_id", "metric_name, value"],
        MAGENTA,
        False,
    )
    y = 9.30
    y = tbl(
        8.35,
        y,
        "model",
        ["PK id", "name, family", "FK symbol_id, timeframe"],
        MAGENTA,
        False,
    )
    y = tbl(
        8.35,
        y,
        "model_version",
        [
            "PK id",
            "FK model_id",
            "mlflow_run_id",
            "random_seed, git_commit",
            "stage, is_active",
        ],
        MAGENTA,
        False,
    )
    tbl(
        8.35,
        y,
        "prediction  [ht]",
        ["FK model_version_id", "feature_asof_ts < target_ts", "y_pred, y_true"],
        MAGENTA,
        False,
    )

    band(ax, 11.85, 5.55, 4.35, 4.35, "schema ops", ORANGE)
    y = 9.30
    y = tbl(
        12.50,
        y,
        "job_log  [hypertable]",
        ["job_type, status", "FK symbol_id", "duration_ms, error_message"],
        ORANGE,
    )
    tbl(12.50, y, "data_quality_check", ["FK symbol_id", "check_name, passed"], ORANGE)

    def mid_bottom(name):
        x, y0, w, _ = placed[name]
        return (x + w / 2, y0)

    def mid_top(name):
        x, y0, w, h = placed[name]
        return (x + w / 2, y0 + h)

    for a, b, dashed in (
        ("exchange", "symbol", False),
        ("symbol", "ohlcv_raw", False),
        ("ohlcv_raw", "ohlcv   [hypertable]", False),
        ("feature_set", "feature_value  [ht]", True),
        ("model", "model_version", True),
        ("model_version", "prediction  [ht]", True),
        ("backtest_run", "backtest_result", True),
    ):
        ax.add_patch(
            FancyArrowPatch(
                mid_bottom(a),
                mid_top(b),
                arrowstyle="-",
                color=LINE,
                linewidth=1.1,
                linestyle="--" if dashed else "-",
                zorder=1,
            )
        )

    def side(name, right):
        x, y0, w, h = placed[name]
        return (x + w if right else x, y0 + h / 2)

    for a, b in (("symbol", "feature_value  [ht]"),):
        ax.add_patch(
            FancyArrowPatch(
                side(a, True),
                side(b, False),
                arrowstyle="-",
                color=LINE,
                linewidth=1.1,
                linestyle="--",
                zorder=1,
            )
        )
    for target in ("model_metric", "backtest_run"):
        ax.add_patch(
            FancyArrowPatch(
                side("model_version", False),
                side(target, True),
                arrowstyle="-",
                connectionstyle="arc3,rad=0.15",
                color=LINE,
                linewidth=1.1,
                linestyle="--",
                zorder=1,
            )
        )

    nx, ny, nw, nh = 11.85, 1.25, 4.35, 3.95
    ax.add_patch(
        FancyBboxPatch(
            (nx, ny),
            nw,
            nh,
            boxstyle="round,pad=0,rounding_size=0.08",
            facecolor=TINT[GREEN],
            edgecolor=GREEN,
            linewidth=1.3,
            zorder=2,
        )
    )
    ax.text(
        nx + nw / 2,
        ny + nh - 0.30,
        "Ba điểm cần đọc kỹ trên sơ đồ",
        ha="center",
        va="center",
        fontsize=8.8 * FS,
        fontweight="bold",
        color=INK,
        zorder=3,
    )
    ax.text(
        nx + 0.18,
        ny + nh - 0.62,
        "(1) Chống trùng lặp: market.ohlcv có PRIMARY\n"
        "KEY (symbol_id, timeframe, ts) và được ghi bằng\n"
        "upsert — chạy lại job thu thập không sinh thêm\n"
        "bản ghi.\n\n"
        "(2) Chống nhìn trước tương lai: ml.prediction có\n"
        "CHECK (feature_asof_ts < target_ts) ở tầng cơ\n"
        "sở dữ liệu.\n\n"
        "(3) Nhóm ml.* còn nét đứt: run, tham số, chỉ số\n"
        "và phiên bản mô hình hiện do MLflow đảm nhiệm,\n"
        "nên /predict chưa lưu được vào ml.prediction.\n"
        "Ghi nhận là nợ kỹ thuật.",
        ha="left",
        va="top",
        fontsize=7.3 * FS,
        color=MUTED,
        zorder=3,
        linespacing=1.35,
    )
    save(fig, "d3_erd.png")


# ── D4: sequence diagram for POST /predict ───────────────────────────
def d4_sequence():
    fig, ax = canvas(15, 8.6, (0, 16.2), (0, 8.8))
    title(
        ax,
        "Hình 3.4 — Biểu đồ tuần tự: một yêu cầu dự báo (POST /api/v1/predict)",
        "Đường đứt là vòng đời đối tượng; số thứ tự khớp với mã nguồn services/inference/main.py",
    )

    actors = [
        ("Người dùng", 1.15, YELLOW),
        ("Frontend\nNext.js", 3.6, AQUA),
        ("Inference API\nFastAPI", 6.5, AQUA),
        ("Redis", 9.3, BLUE),
        ("PostgreSQL", 11.6, BLUE),
        ("MLflow\nRegistry", 14.3, MAGENTA),
    ]
    top, bottom = 7.35, 1.30
    for name, x, c in actors:
        box(ax, x - 1.0, top, 2.0, 0.62, name, color=c, fs=8.4 * FS)
        ax.plot(
            [x, x],
            [bottom, top],
            color=LINE,
            linewidth=1.0,
            linestyle=(0, (3, 3)),
            zorder=1,
        )

    steps = [
        (1.15, 3.6, 6.95, "(1) chọn mã, mô hình, số bước"),
        (3.6, 6.5, 6.55, "(2) POST /predict + header X-API-Key"),
        (6.5, 9.3, 6.15, "(3) verify_api_key → INCR rate_limit:<phút> (429 nếu vượt)"),
        (6.5, 9.3, 5.75, "(4) GET cache dự báo"),
        (9.3, 6.5, 5.35, "(5) cache miss"),
        (6.5, 11.6, 4.95, "(6) SELECT 400 nến gần nhất (symbol_id, timeframe)"),
        (6.5, 14.3, 4.55, "(7) search_model_versions → phiên bản mới nhất"),
        (14.3, 6.5, 4.15, "(8) state_dict + 2 scaler + tham số kiến trúc"),
        (6.5, 6.5, 3.55, "(9) dựng 8 đặc trưng × 7 bước, dự báo lặp nhiều bước"),
        (6.5, 11.6, 2.95, "(10) ghi ml.prediction (bỏ qua nếu thiếu model_version)"),
        (6.5, 9.3, 2.55, "(11) SETEX cache 300 giây"),
        (6.5, 3.6, 2.15, "(12) 200 OK — JSON danh sách (target_time, predicted_value)"),
        (3.6, 1.15, 1.75, "(13) vẽ nến OHLC + đường dự báo bằng ECharts"),
    ]
    for x1, x2, y, label in steps:
        if x1 == x2:
            ax.add_patch(
                FancyArrowPatch(
                    (x1, y + 0.22),
                    (x1 + 0.95, y + 0.22),
                    arrowstyle="-",
                    color=LINE,
                    linewidth=1.2,
                    zorder=4,
                )
            )
            ax.add_patch(
                FancyArrowPatch(
                    (x1 + 0.95, y + 0.22),
                    (x1 + 0.95, y),
                    arrowstyle="-",
                    color=LINE,
                    linewidth=1.2,
                    zorder=4,
                )
            )
            ax.add_patch(
                FancyArrowPatch(
                    (x1 + 0.95, y),
                    (x1 + 0.06, y),
                    arrowstyle="-|>",
                    mutation_scale=11,
                    color=LINE,
                    linewidth=1.2,
                    zorder=4,
                )
            )
            ax.text(
                x1 + 1.15,
                y + 0.1,
                label,
                ha="left",
                va="center",
                fontsize=7.8 * FS,
                color=INK,
                zorder=5,
            )
        else:
            back = x2 < x1
            ax.add_patch(
                FancyArrowPatch(
                    (x1, y),
                    (x2, y),
                    arrowstyle="-|>",
                    mutation_scale=11,
                    color=LINE,
                    linewidth=1.2,
                    linestyle="--" if back else "-",
                    zorder=4,
                )
            )
            ax.text(
                (x1 + x2) / 2,
                y + 0.16,
                label,
                ha="center",
                va="bottom",
                fontsize=7.8 * FS,
                color=INK if not back else MUTED,
                zorder=5,
                bbox=dict(
                    boxstyle="round,pad=0.15",
                    facecolor="white",
                    edgecolor="none",
                    alpha=0.95,
                ),
            )

    box(
        ax,
        0.25,
        0.05,
        7.1,
        0.75,
        "Đo 07/10: p95 ≤ 0,68 s khi model chạy · ≤ 0,04 s khi trúng cache",
        color=GREEN,
        fs=8.2 * FS,
    )
    box(
        ax,
        7.75,
        0.05,
        8.25,
        0.75,
        "Lần gọi đầu của mỗi model phải tải artifact từ Registry rồi mới cache vào RAM",
        color=YELLOW,
        fs=8.2 * FS,
    )
    save(fig, "d4_tuan_tu.png")


# ── D5: use case ─────────────────────────────────────────────────────
def d5_usecase():
    fig, ax = canvas(14.6, 8.6, (0, 15.6), (0, 8.8))
    title(
        ax,
        "Hình 2.1 — Biểu đồ ca sử dụng",
        "Ba tác nhân: người xem, tác nhân hệ thống (Celery Beat) và thành viên nhóm",
    )

    ax.add_patch(
        FancyBboxPatch(
            (3.5, 0.5),
            8.7,
            7.1,
            boxstyle="round,pad=0,rounding_size=0.12",
            facecolor="#fafaf8",
            edgecolor=LINE,
            linewidth=1.2,
            zorder=1,
        )
    )
    ax.text(
        7.85,
        7.38,
        "Hệ thống thu thập, phân tích & dự báo giá",
        ha="center",
        va="center",
        fontsize=9.5 * FS,
        fontweight="bold",
        color=MUTED,
        zorder=3,
    )

    def actor(x, y, name, note):
        ax.add_patch(
            Ellipse(
                (x, y + 0.62),
                0.34,
                0.34,
                facecolor="white",
                edgecolor=INK,
                linewidth=1.3,
                zorder=3,
            )
        )
        ax.plot([x, x], [y + 0.45, y - 0.05], color=INK, linewidth=1.3, zorder=3)
        ax.plot(
            [x - 0.28, x + 0.28], [y + 0.3, y + 0.3], color=INK, linewidth=1.3, zorder=3
        )
        ax.plot([x, x - 0.24], [y - 0.05, y - 0.5], color=INK, linewidth=1.3, zorder=3)
        ax.plot([x, x + 0.24], [y - 0.05, y - 0.5], color=INK, linewidth=1.3, zorder=3)
        ax.text(
            x,
            y - 0.75,
            name,
            ha="center",
            va="top",
            fontsize=8.6 * FS,
            fontweight="bold",
            color=INK,
            zorder=3,
        )
        ax.text(
            x,
            y - 1.12,
            note,
            ha="center",
            va="top",
            fontsize=7.4 * FS,
            color=MUTED,
            zorder=3,
            linespacing=1.3,
        )

    def uc(x, y, label, color=BLUE, dashed=False, w=3.55, h=0.74):
        ax.add_patch(
            Ellipse(
                (x, y),
                w,
                h,
                facecolor=TINT[color],
                edgecolor=color,
                linewidth=1.3,
                linestyle="--" if dashed else "-",
                zorder=2,
            )
        )
        ax.text(
            x,
            y,
            label,
            ha="center",
            va="center",
            fontsize=7.9 * FS,
            color=INK,
            zorder=3,
            linespacing=1.25,
        )
        return (x, y, w, h)

    actor(1.55, 5.6, "Người xem", "nhà đầu tư,\nsinh viên")
    actor(1.55, 2.2, "Celery Beat", "tác nhân hệ thống\n(lịch crontab)")
    actor(13.45, 4.0, "Thành viên nhóm", "vai trò nghiên cứu")

    u1 = uc(5.55, 6.75, "Xem danh sách mã & giá gần nhất")
    u2 = uc(5.55, 5.85, "Xem biểu đồ lịch sử OHLC")
    u3 = uc(5.55, 4.95, "Chạy dự báo cho một mã", AQUA)
    u4 = uc(5.55, 4.05, "Xem giải thích mô hình (4 mô hình)", AQUA)
    u5 = uc(5.55, 3.15, "So sánh chỉ số các mô hình", AQUA)
    u6 = uc(5.55, 2.25, "Thu thập dữ liệu theo lịch", ORANGE)
    u7 = uc(5.55, 1.35, "Làm sạch & kiểm định dữ liệu", ORANGE)
    u8 = uc(9.95, 6.3, "Nạp snapshot & kiểm tra hợp đồng", GREEN)
    u9 = uc(9.95, 5.4, "Huấn luyện mô hình (4 entrypoint)", MAGENTA)
    u10 = uc(9.95, 4.5, "Đăng ký mô hình lên Registry", MAGENTA)
    u11 = uc(9.95, 3.6, "Chạy benchmark 4 mô hình", GREEN)
    u12 = uc(9.95, 2.7, "Xuất bằng chứng có checksum", GREEN)
    u13 = uc(9.95, 1.5, "Xem nhật ký job & chất lượng dữ liệu", YELLOW)

    for u in (u1, u2, u3, u4, u5):
        ax.plot(
            [1.95, u[0] - u[2] / 2], [5.6, u[1]], color=LINE, linewidth=1.0, zorder=1
        )
    for u in (u6, u7):
        ax.plot(
            [1.95, u[0] - u[2] / 2], [2.2, u[1]], color=LINE, linewidth=1.0, zorder=1
        )
    for u in (u8, u9, u10, u11, u12):
        ax.plot(
            [12.95, u[0] + u[2] / 2], [4.0, u[1]], color=LINE, linewidth=1.0, zorder=1
        )
    ax.plot(
        [12.95, u13[0] + u13[2] / 2],
        [4.0, u13[1]],
        color=LINE,
        linewidth=1.0,
        zorder=1,
    )
    ax.plot(
        [u9[0] - u9[2] / 2, u10[0] - u10[2] / 2],
        [u9[1], u10[1]],
        color=LINE,
        linewidth=1.0,
        linestyle=(0, (2, 2)),
        zorder=1,
    )
    ax.text(
        8.30, 4.95, "«include»", fontsize=6.8 * FS, color=MUTED, ha="right", zorder=3
    )
    save(fig, "d5_use_case.png")


# ── D6: CI/CD and quality gates ──────────────────────────────────────
def d6_cicd():
    fig, ax = canvas(15, 6.6, (0, 16.4), (0, 7.0))
    title(
        ax,
        "Hình 6.1 — Cổng chất lượng: từ máy lập trình viên tới nhánh develop",
        "Nguyên tắc: không dựa vào việc con người (hay AI) có nhớ quy tắc hay không — để Git và CI chặn",
    )

    box(ax, 0.25, 3.35, 2.30, 1.25, "Lập trình viên", "nhánh feature/*", YELLOW)
    box(
        ax,
        2.95,
        3.35,
        2.75,
        1.25,
        "pre-commit",
        "ruff format\nruff check\ngitleaks",
        ORANGE,
    )
    box(ax, 6.10, 3.35, 2.40, 1.25, "Pull Request", "mẫu PR +\nCODEOWNERS", BLUE)
    band(ax, 8.85, 1.20, 3.35, 4.80, "GitHub Actions — 4 job song song", MAGENTA)
    for i, (name, sub) in enumerate(
        [
            ("Lint & Format", "ruff check + format"),
            ("Python Tests", "pytest + TimescaleDB"),
            ("Docker Compose", "kiểm tra cú pháp"),
            ("Frontend Build", "next build"),
        ]
    ):
        box(
            ax,
            8.98,
            4.60 - i * 0.92,
            3.10,
            0.78,
            name,
            sub,
            MAGENTA,
            fs=8.2 * FS,
            radius=0.06,
        )
    box(
        ax,
        12.60,
        3.35,
        3.45,
        1.25,
        "Merge vào develop",
        "quy định: 4 job xanh + ≥ 1 review\n(branch protection chưa bật)",
        GREEN,
    )
    box(
        ax,
        12.60,
        1.35,
        3.45,
        1.25,
        "Deploy workflow",
        "build & push ghcr.io\n(bước SSH còn tắt)",
        LINE,
        dashed=True,
    )

    elbow(ax, [(2.55, 3.97), (2.95, 3.97)])
    elbow(ax, [(5.70, 3.97), (6.10, 3.97)])
    elbow(ax, [(8.50, 3.97), (8.85, 3.97)])
    elbow(ax, [(12.20, 3.97), (12.60, 3.97)])
    elbow(
        ax,
        [(14.32, 3.35), (14.32, 2.60)],
        "khi merge vào main",
        (15.25, 2.98),
        dashed=True,
    )
    elbow(
        ax,
        [(4.32, 3.35), (4.32, 2.75), (1.40, 2.75), (1.40, 3.35)],
        "trả về máy lập trình viên nếu lộ secret hoặc sai style",
        (4.60, 2.50),
        color=ORANGE,
    )
    save(fig, "d6_cicd.png")


# ── D7: model lifecycle (MLOps) ──────────────────────────────────────
def d7_mlops():
    fig, ax = canvas(15, 6.4, (0, 16.4), (0, 6.9))
    title(
        ax,
        "Hình 5.1 — Vòng đời một mô hình trong hệ thống",
        "Điểm cốt lõi của đề tài: mô hình là một thành phần phần mềm được quản lý phiên bản, không phải một notebook rời",
    )

    y, h, w = 4.15, 1.45, 2.90
    xs = [0.25, 3.50, 6.75, 10.00, 13.20]
    nodes = [
        ("(1) Hợp đồng dữ liệu", "group_dataset_v1\nsnapshot + fingerprint", GREEN),
        (
            "(2) Huấn luyện",
            "train_*.py --ticker --timeframe\nseed 42, chia theo thời gian",
            MAGENTA,
        ),
        (
            "(3) MLflow Run",
            "params, metrics, artifact\nprediction CSV + manifest hash",
            MAGENTA,
        ),
        ("(4) Model Registry", "{SYMBOL}_{timeframe}_{model}\nversion, stage", MAGENTA),
        ("(5) Phục vụ", "ModelLoader nạp & cache RAM\nPOST /api/v1/predict", AQUA),
    ]
    for x, (t, s, c) in zip(xs, nodes):
        box(ax, x, y, w, h, t, s, c)
    for i in range(4):
        elbow(ax, [(xs[i] + w, y + h / 2), (xs[i + 1], y + h / 2)])

    box(
        ax,
        3.50,
        1.75,
        6.15,
        1.60,
        "(6) Cổng kiểm định khoa học — benchmark evaluator",
        "ACB 1d: cùng test manifest cho 4 mô hình • đối chiếu SHA-256\n"
        "nạp lại artifact • tính lại metric (dung sai 1e-12) • so với Naive",
        GREEN,
    )
    box(
        ax,
        10.00,
        1.75,
        6.10,
        1.60,
        "(7) Bằng chứng nghiên cứu",
        "artifacts/benchmarks/<mã>_<khung>/ • docs/evidence/ kèm checksum\n"
        "bảng kết quả trong báo cáo • tái lập được bằng một lệnh",
        BLUE,
    )

    elbow(ax, [(8.20, 4.15), (8.20, 3.35)], "4 run_id + artifact", (8.20, 3.72))
    elbow(ax, [(9.65, 2.55), (10.00, 2.55)])
    elbow(
        ax,
        [(1.70, 4.15), (1.70, 2.55), (3.50, 2.55)],
        "dữ liệu đã khóa",
        (1.70, 3.60),
        color=GREEN,
        dashed=True,
    )
    box(
        ax,
        0.25,
        0.10,
        15.85,
        1.15,
        "Hạn chế: Inference nạp phiên bản mới nhất trong Registry;\n"
        "cổng (6) là bước kiểm định nghiên cứu, chưa tự động quyết định phiên bản được phục vụ",
        color=YELLOW,
        fs=8.6 * FS,
    )
    save(fig, "d7_vong_doi_model.png")


# ── D8: class diagrams (UML) ─────────────────────────────────────────
def uml_class(ax, x, ytop, w, name, attrs=(), methods=(), color=BLUE, stereo=None):
    """UML class box (name / attributes / operations); returns its geometry."""
    pitch = 0.27
    head = 0.62 if stereo else 0.42
    body_a = pitch * len(attrs) + 0.10 if attrs else 0.14
    body_m = pitch * len(methods) + 0.10 if methods else 0.0
    h = head + body_a + body_m
    y = ytop - h
    ax.add_patch(
        Rectangle(
            (x, y), w, h, facecolor="white", edgecolor=color, linewidth=1.3, zorder=2
        )
    )
    ax.add_patch(
        Rectangle(
            (x, ytop - head),
            w,
            head,
            facecolor=TINT[color],
            edgecolor=color,
            linewidth=1.3,
            zorder=3,
        )
    )
    if stereo:
        ax.text(
            x + w / 2,
            ytop - 0.18,
            f"«{stereo}»",
            ha="center",
            va="center",
            fontsize=6.8 * FS,
            color=MUTED,
            style="italic",
            zorder=4,
        )
    ax.text(
        x + w / 2,
        ytop - head + 0.21,
        name,
        ha="center",
        va="center",
        fontsize=(8.2 if len(name) <= 18 else 7.2) * FS,
        fontweight="bold",
        color=INK,
        zorder=4,
    )
    yy = ytop - head - 0.05
    for a in attrs:
        ax.text(
            x + 0.10,
            yy - pitch / 2,
            a,
            ha="left",
            va="center",
            fontsize=6.9 * FS,
            color=INK,
            zorder=4,
        )
        yy -= pitch
    yy = ytop - head - body_a
    if methods:
        ax.plot([x, x + w], [yy, yy], color=color, linewidth=1.0, zorder=4)
        yy -= 0.05
        for m in methods:
            ax.text(
                x + 0.10,
                yy - pitch / 2,
                m,
                ha="left",
                va="center",
                fontsize=6.9 * FS,
                color=INK,
                zorder=4,
            )
            yy -= pitch
    return (x, y, w, h)


def _edge(geom, where):
    x, y, w, h = geom
    return {
        "top": (x + w / 2, y + h),
        "bottom": (x + w / 2, y),
        "left": (x, y + h / 2),
        "right": (x + w, y + h / 2),
    }[where]


def uml_link(ax, p1, p2, kind="assoc", label=None, lab_at=None, rad=0.0):
    """kind: assoc (-->), realize (..|>), inherit (--|>), compose (◆--), depend (..>)."""
    style = {
        "assoc": "-|>",
        "realize": "-|>",
        "inherit": "-|>",
        "compose": "-",
        "depend": "-|>",
    }[kind]
    dashed = kind in ("realize", "depend")
    hollow = kind in ("realize", "inherit")
    patch = FancyArrowPatch(
        p1,
        p2,
        arrowstyle=style,
        mutation_scale=14 if hollow else 11,
        connectionstyle=f"arc3,rad={rad}",
        color=LINE,
        linewidth=1.2,
        linestyle="--" if dashed else "-",
        zorder=1,
        shrinkA=0,
        shrinkB=0,
    )
    if hollow:
        patch.set_facecolor("white")
        patch.set_arrowstyle("-|>,head_length=0.55,head_width=0.35")
    ax.add_patch(patch)
    if kind == "compose":
        ax.plot(*p1, marker="D", markersize=7, color=LINE, zorder=5)
    if label:
        lx, ly = lab_at if lab_at else ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
        ax.text(
            lx,
            ly,
            label,
            ha="center",
            va="center",
            fontsize=6.8 * FS,
            color=MUTED,
            zorder=6,
            bbox=dict(
                boxstyle="round,pad=0.12",
                facecolor="white",
                edgecolor="none",
                alpha=0.95,
            ),
        )


def d8a_class_models():
    fig, ax = canvas(15, 9.6, (0, 16.4), (0, 10.4))
    title(
        ax,
        "Hình 3.6 — Biểu đồ lớp (a): phục vụ và huấn luyện mô hình",
        "Lớp và quan hệ lấy từ mã nguồn services/inference và services/training "
        "· ◆ = sở hữu · tam giác rỗng nét đứt = hiện thực giao diện",
    )
    band(ax, 0.20, 0.05, 9.55, 9.15, "services/inference", AQUA, label_at="bottom")
    band(ax, 9.95, 0.05, 6.25, 9.15, "services/training", MAGENTA, label_at="bottom")

    loader = uml_class(
        ax,
        0.40,
        8.65,
        4.45,
        "ModelLoader",
        ["- _cache: dict[(tên, version), LoadedModel]"],
        [
            "+ load(ticker, timeframe, model_name): LoadedModel",
            "+ latest_version(registry_name): (version, run_id)",
        ],
        AQUA,
    )
    loaded = uml_class(
        ax,
        5.15,
        8.65,
        4.40,
        "LoadedModel",
        [
            "+ predictor: Predictor",
            "+ registry_name: str",
            "+ version: int",
            "+ run_id: str",
        ],
        (),
        AQUA,
        "dataclass",
    )
    uml_class(
        ax,
        0.40,
        6.40,
        4.45,
        "RedisCache",
        ["- client: Redis | None"],
        ["+ get(key): Any | None", "+ set(key, value, ttl_seconds=300): bool"],
        BLUE,
    )
    proto = uml_class(
        ax,
        5.15,
        6.05,
        4.40,
        "Predictor",
        (),
        ["+ predict_steps(history, steps): list[float]"],
        AQUA,
        "Protocol",
    )
    xs, w = [0.40, 2.70, 5.00, 7.30], 2.20
    preds = [
        uml_class(
            ax,
            xs[0],
            3.95,
            w,
            "XGBoostPredictor",
            ["- model", "- scaler"],
            ["+ predict_steps()"],
            AQUA,
        ),
        uml_class(
            ax,
            xs[1],
            3.95,
            w,
            "RandomForestPredictor",
            ["- model"],
            ["+ predict_steps()"],
            AQUA,
        ),
        uml_class(
            ax,
            xs[2],
            3.95,
            w,
            "GRUPredictor",
            [
                "- model: GRUForecaster",
                "- feature_scaler",
                "- target_scaler",
                "- sequence_length",
            ],
            ["+ min_history_rows()", "+ predict_steps()"],
            AQUA,
        ),
        uml_class(
            ax,
            xs[3],
            3.95,
            w,
            "ArimaPredictor",
            ["- results", "- history_end_ts"],
            ["+ predict_steps()"],
            AQUA,
        ),
    ]
    gru_inf = uml_class(
        ax,
        5.00,
        1.40,
        2.20,
        "GRUForecaster",
        (),
        ["+ forward(inputs)"],
        AQUA,
        "nn.Module",
    )

    uml_link(
        ax,
        _edge(loader, "right"),
        _edge(loaded, "left"),
        "compose",
        "0..*",
        lab_at=(4.97, 7.62),
    )
    uml_link(ax, _edge(loaded, "bottom"), _edge(proto, "top"), "assoc", "1")
    px, _, pw, _ = proto
    for i, g in enumerate(preds):
        target = (px + pw * (0.2 + 0.2 * i), proto[1])
        uml_link(ax, _edge(g, "top"), target, "realize")
    uml_link(ax, _edge(preds[2], "bottom"), _edge(gru_inf, "top"), "assoc")

    uml_class(
        ax,
        10.15,
        8.65,
        2.90,
        "XGBoostModelWrapper",
        ["- model: XGBRegressor", "- explainer"],
        [
            "+ fit()",
            "+ predict(X)",
            "+ calculate_shap_values(X)",
            "+ get_feature_importances()",
        ],
        MAGENTA,
    )
    uml_class(
        ax,
        13.15,
        8.65,
        2.90,
        "RandomForestModelWrapper",
        ["- model: RandomForestRegressor", "- explainer"],
        [
            "+ fit(X, y)",
            "+ predict(X)",
            "+ calculate_shap_values(X)",
            "+ get_feature_importances()",
        ],
        MAGENTA,
    )
    uml_class(
        ax,
        10.15,
        5.30,
        2.90,
        "ARIMABaseline",
        ["- order: (p, d, q)"],
        [
            "+ fit(prices)",
            "+ forecast_one()",
            "+ update(actual_close)",
            "+ snapshot()",
            "+ coefficient_table()",
        ],
        MAGENTA,
    )
    gru = uml_class(
        ax,
        13.15,
        5.30,
        2.90,
        "GRUForecaster",
        ["+ input_size, hidden_size", "+ num_layers, dropout"],
        ["+ forward(inputs)", "+ get_config()"],
        MAGENTA,
        "nn.Module",
    )
    cfg = uml_class(
        ax,
        13.15,
        2.60,
        2.90,
        "GRUTrainingConfig",
        [
            "sequence_length = 7",
            "hidden_size = 64",
            "batch_size = 16",
            "max_epochs = 100, patience = 20",
        ],
        (),
        MAGENTA,
        "dataclass",
    )
    uml_link(ax, _edge(cfg, "top"), _edge(gru, "bottom"), "depend", "cấu hình")
    ax.text(
        10.15,
        1.95,
        "Mỗi wrapper được một entrypoint\ntrain_*.py dùng; artifact và\n"
        "artifact giải thích được ghi vào\nMLflow, rồi ModelLoader nạp lại\n"
        "phiên bản mới nhất để phục vụ.",
        ha="left",
        va="top",
        fontsize=6.9 * FS,
        color=MUTED,
        linespacing=1.35,
    )
    elbow(
        ax,
        [(11.60, 8.65), (11.60, 9.00), (2.62, 9.00), (2.62, 8.65)],
        "artifact + kết quả giải thích qua MLflow Registry",
        (7.10, 9.00),
        dashed=True,
    )
    save(fig, "d8a_bieu_do_lop_mo_hinh.png")


def d8b_class_data():
    fig, ax = canvas(15, 9.6, (0, 16.4), (0, 10.4))
    title(
        ax,
        "Hình 3.7 — Biểu đồ lớp (b): thu thập dữ liệu và thành phần dùng chung",
        "Lớp và quan hệ lấy từ mã nguồn services/ingestion và shared "
        "· tam giác rỗng = kế thừa · nét đứt = phụ thuộc",
    )
    band(ax, 0.20, 0.25, 6.70, 9.15, "services/ingestion", ORANGE)
    band(ax, 7.10, 0.25, 9.10, 9.15, "shared", BLUE)

    tasks = uml_class(
        ax,
        0.40,
        8.65,
        6.30,
        "tasks.py",
        (),
        [
            "+ ingest_crypto_task(symbols, resolution='1h'): int",
            "+ ingest_stocks_task(symbols, resolution='1d'): int",
            "+ clean_and_store_task(symbol_id, timeframe): dict",
        ],
        ORANGE,
        "module — Celery task",
    )
    binance = uml_class(
        ax,
        0.40,
        6.35,
        3.05,
        "BinanceAdapter",
        ["- exchange: ccxt.binance"],
        ["+ fetch_historical_ohlcv()", "+ close()"],
        ORANGE,
    )
    vn = uml_class(
        ax,
        3.65,
        6.35,
        3.05,
        "VNStockAdapter",
        ["- _vnstock (tùy chọn)"],
        ["+ available(): bool", "+ fetch_historical_ohlcv()"],
        ORANGE,
    )
    uml_class(
        ax,
        0.40,
        4.70,
        3.05,
        "CleaningReport",
        [
            "+ input_rows, output_rows",
            "+ duplicates_removed",
            "+ missing_filled",
            "+ outliers_flagged",
        ],
        ["+ to_dict()"],
        ORANGE,
        "dataclass",
    )
    uml_class(
        ax,
        3.65,
        4.70,
        3.05,
        "CleaningConfig",
        ["CLEANING_FFILL_LIMIT", "CLEANING_IQR_MULTIPLIER"],
        (),
        ORANGE,
        "BaseSettings",
    )
    uml_class(
        ax,
        0.40,
        2.30,
        6.30,
        "SchedulerSettings",
        [
            "INGEST_CRYPTO_SYMBOLS, INGEST_STOCK_SYMBOLS",
            "CLEAN_STOCK_HOUR_UTC, CLEAN_STAGGER_INTERVAL_MINS",
        ],
        (),
        ORANGE,
        "BaseSettings",
    )
    uml_link(ax, (1.90, tasks[1]), _edge(binance, "top"), "depend")
    uml_link(ax, (5.20, tasks[1]), _edge(vn, "top"), "depend")
    elbow(
        ax,
        [(0.40, 7.20), (0.30, 7.20), (0.30, 3.90), (0.40, 3.90)],
        dashed=True,
    )
    ax.text(
        0.34,
        5.30,
        "trả về",
        rotation=90,
        ha="left",
        va="center",
        fontsize=6.6 * FS,
        color=MUTED,
    )

    uml_class(
        ax,
        7.30,
        8.65,
        4.20,
        "Settings",
        [
            "DATABASE_URL, REDIS_URL",
            "MLFLOW_TRACKING_URI",
            "API_KEY_SECRET",
            "RATE_LIMIT_PER_MINUTE = 60",
            "/database_url_sync: str",
        ],
        (),
        BLUE,
        "BaseSettings",
    )
    base = uml_class(ax, 12.10, 8.65, 3.90, "Base", (), (), BLUE, "DeclarativeBase")
    exch = uml_class(ax, 11.70, 6.80, 2.10, "Exchange", ["id, code, name"], (), BLUE)
    sym = uml_class(
        ax, 14.05, 6.80, 2.00, "Symbol", ["id, ticker", "asset_class"], (), BLUE
    )
    mlm = uml_class(ax, 11.70, 5.30, 2.10, "MLModel", ["id, name, family"], (), BLUE)
    mv = uml_class(
        ax, 14.05, 5.30, 2.00, "ModelVersion", ["mlflow_run_id", "stage"], (), BLUE
    )
    uml_class(
        ax,
        11.70,
        3.95,
        4.35,
        "DataQualityCheck",
        ["symbol_id, check_name, passed, detail"],
        (),
        BLUE,
    )
    for g in (exch,):
        uml_link(ax, _edge(g, "top"), _edge(base, "bottom"), "inherit")
    uml_link(ax, _edge(exch, "right"), _edge(sym, "left"), "assoc", "1 — *")
    uml_link(ax, _edge(mlm, "right"), _edge(mv, "left"), "assoc", "1 — *")
    ax.text(
        16.00,
        2.98,
        "Mọi lớp ORM (Symbol, MLModel, …) đều kế thừa Base;\nmột số lớp ml.* được lược bớt",
        ha="right",
        va="top",
        fontsize=6.6 * FS,
        color=MUTED,
    )

    uml_class(
        ax,
        7.30,
        5.70,
        4.20,
        "PredictRequest",
        [
            "ticker_id: str",
            "model_name: arima|xgboost|…",
            "steps: 1..30",
            "timeframe: 1d | 1h | None",
        ],
        ["+ validate_model_name()", "+ validate_timeframe()"],
        BLUE,
        "pydantic",
    )
    resp = uml_class(
        ax,
        7.30,
        2.25,
        2.00,
        "PredictResponse",
        ["ticker_id, model_name", "predictions"],
        (),
        BLUE,
        "pydantic",
    )
    item = uml_class(
        ax,
        9.50,
        2.25,
        2.00,
        "PredictionItem",
        ["target_time", "predicted_value"],
        (),
        BLUE,
        "pydantic",
    )
    exr = uml_class(
        ax,
        11.70,
        2.25,
        2.10,
        "ExplainResponse",
        ["method, features", "baseline_rmse, order"],
        (),
        BLUE,
        "pydantic",
    )
    exf = uml_class(
        ax,
        14.05,
        2.25,
        2.00,
        "ExplainFeature",
        ["feature, importance", "p_value, …"],
        (),
        BLUE,
        "pydantic",
    )
    uml_link(ax, _edge(resp, "right"), _edge(item, "left"), "compose", "1..*")
    uml_link(ax, _edge(exr, "right"), _edge(exf, "left"), "compose", "1..*")
    uml_link(
        ax,
        (tasks[0] + tasks[2], 8.20),
        (7.30, 8.20),
        "depend",
        "cấu hình",
        lab_at=(7.00, 8.42),
    )
    save(fig, "d8b_bieu_do_lop_du_lieu.png")


if __name__ == "__main__":
    d1_architecture()
    d2_pipeline()
    d3_erd()
    d4_sequence()
    d5_usecase()
    d6_cicd()
    d7_mlops()
    d8a_class_models()
    d8b_class_data()
