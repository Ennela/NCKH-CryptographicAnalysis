"""Grouped bar chart: RMSE ratio (model / Naive) per symbol, log scale."""

import sys
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

S = sys.argv[1]
df = pd.read_csv(f"{S}/all_results.csv")
df["key"] = df["symbol"] + " " + df["timeframe"]
df["ratio"] = df["rmse"] / df["naive_rmse"]

MODELS = ["arima", "xgboost", "random_forest", "gru"]  # fixed order = fixed hue
LABELS = {
    "arima": "ARIMA",
    "xgboost": "XGBoost",
    "random_forest": "Random Forest",
    "gru": "GRU v2",
}
COLORS = {
    "arima": "#2a78d6",
    "xgboost": "#eb6834",
    "random_forest": "#1baf7a",
    "gru": "#eda100",
}

order = [
    k
    for k in [
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
    if k in set(df["key"])
]
piv = df.pivot_table(index="key", columns="model", values="ratio").reindex(order)

fig, ax = plt.subplots(figsize=(10, 4.6), dpi=150)
fig.patch.set_facecolor("white")
w = 0.2
x = range(len(order))
for i, m in enumerate(MODELS):
    vals = piv[m].values if m in piv else [float("nan")] * len(order)
    ax.bar(
        [xi + (i - 1.5) * w for xi in x],
        vals,
        width=w * 0.92,
        color=COLORS[m],
        label=LABELS[m],
        bottom=0,
        zorder=3,
    )
ax.axhline(1.0, color="#555555", lw=1.2, ls="--", zorder=2)
ax.text(
    -0.45, 1.03, "Naive (= 1,0)", ha="left", va="bottom", fontsize=8, color="#555555"
)
ax.set_yscale("log")
ax.set_ylim(0.5, 30)
ax.set_yticks([0.5, 1, 2, 5, 10, 20])
ax.set_yticklabels(["0,5×", "1×", "2×", "5×", "10×", "20×"])
ax.set_xticks(list(x))
ax.set_xticklabels(order, fontsize=9)
ax.set_ylabel("RMSE / RMSE Naive (log)", fontsize=9)
ax.set_title(
    "Sai số RMSE của từng mô hình so với baseline Naive (thấp hơn 1× là tốt hơn Naive)",
    fontsize=10,
    loc="left",
)
ax.grid(axis="y", color="#e5e5e5", zorder=0)
for s in ["top", "right"]:
    ax.spines[s].set_visible(False)
ax.spines["left"].set_color("#bbbbbb")
ax.spines["bottom"].set_color("#bbbbbb")
ax.tick_params(colors="#333333", labelsize=8)
ax.legend(ncol=4, fontsize=8, frameon=False, loc="upper left")
fig.tight_layout()
fig.savefig(f"{S}/chart_rmse_ratio.png")
print("saved")
