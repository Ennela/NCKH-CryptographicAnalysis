"""Capture the evidence screenshots used by the report.

Repeatable on purpose: the figures in the report regenerate from a running
stack rather than being pasted in by hand.

Usage (stack running, Chromium/Edge listening on CDP port 9222):
    python reports/src/capture.py docs/evidence/screenshots/ui

Each screen gets a full-page shot plus close-ups of the panels the report
discusses (statistics table, analysis chart, data quality, job log, ...).
"""

from __future__ import annotations

import os
import sys

from playwright.sync_api import Page, sync_playwright

OUT = sys.argv[1] if len(sys.argv) > 1 else "shots"
FRONT = os.environ.get("FRONT", "http://localhost:3000")
API = os.environ.get("API", "http://localhost:8010")
os.makedirs(OUT, exist_ok=True)


def shot(page: Page, name: str, full: bool = False) -> None:
    """Screenshot the viewport (or the whole page)."""
    page.screenshot(path=f"{OUT}/{name}", full_page=full)
    print("shot", name)


def element(page: Page, locator, name: str) -> None:
    """Screenshot the page region covered by an element.

    Clips a full-page shot instead of Locator.screenshot(): the latter waits
    for the element to be "stable", which ECharts canvases never report.
    """
    box = locator.evaluate(
        "el => { const r = el.getBoundingClientRect();"
        " return {x: r.left + window.scrollX, y: r.top + window.scrollY,"
        " width: r.width, height: r.height}; }"
    )
    page.screenshot(path=f"{OUT}/{name}", full_page=True, clip=box)
    print("shot", name)


def panel(page: Page, heading: str, name: str) -> None:
    """Screenshot the panel whose h2 heading contains `heading`."""
    element(
        page,
        page.locator("section", has=page.locator("h2", has_text=heading)).first,
        name,
    )


def open_page(page: Page, path: str, settle_ms: int = 3000) -> None:
    page.goto(f"{FRONT}{path}", wait_until="networkidle", timeout=90_000)
    page.wait_for_timeout(settle_ms)


def analysis_grid(page: Page):
    """Chart panel + indicator sidebar, laid out side by side."""
    return page.locator(
        "div.grid", has=page.locator("h2", has_text="Biểu đồ phân tích")
    ).first


def capture_overview(page: Page) -> None:
    open_page(page, "/")
    shot(page, "ui_01_tong_quan.png", full=True)


def capture_analysis(page: Page) -> None:
    open_page(page, "/analysis?ticker=ACB&timeframe=1d", settle_ms=4000)
    shot(page, "ui_02_phan_tich_toan_trang.png", full=True)
    panel(page, "Bảng thông số dữ liệu", "ui_03_bang_thong_so_du_lieu.png")
    element(page, analysis_grid(page), "ui_04_dashboard_phan_tich_ACB.png")
    open_page(page, "/analysis?ticker=BTCUSDT&timeframe=1h", settle_ms=4000)
    element(page, analysis_grid(page), "ui_05_dashboard_phan_tich_BTC_1h.png")


def capture_forecast(page: Page) -> None:
    open_page(page, "/forecast")
    selects = page.locator("select")
    selects.nth(0).select_option("ACB")
    selects.nth(1).select_option("gru")
    page.wait_for_timeout(2500)
    page.get_by_role("button", name="Tiến hành dự báo").click()
    # The first request after a restart loads the model from MLflow (slow).
    page.get_by_text("Kết quả dự báo chi tiết").wait_for(timeout=120_000)
    page.wait_for_timeout(1500)
    page.evaluate("window.scrollTo(0, 0)")
    shot(page, "ui_06_du_bao_GRU.png")
    panel(page, "So sánh 4 mô hình", "ui_07_so_sanh_4_mo_hinh.png")
    panel(page, "Kết quả dự báo chi tiết", "ui_08_ket_qua_du_bao.png")


def capture_explain(page: Page) -> None:
    open_page(page, "/explainability", settle_ms=4000)
    shot(page, "ui_09_giai_thich_shap.png")


def capture_pipeline(page: Page) -> None:
    open_page(page, "/pipeline", settle_ms=4000)
    shot(page, "ui_10_thu_thap_lam_sach_toan_trang.png", full=True)
    panel(page, "1. Nguồn dữ liệu", "ui_11_nguon_va_lich_thu_thap.png")
    panel(page, "2. Tổ chức & làm sạch", "ui_12_quy_trinh_lam_sach.png")
    panel(page, "3. Chuẩn hóa dữ liệu", "ui_13_chuan_hoa_du_lieu.png")
    panel(page, "4. Chất lượng dữ liệu", "ui_14_chat_luong_du_lieu.png")
    panel(page, "5. Vận hành", "ui_15_nhat_ky_job.png")


def capture_swagger(page: Page) -> None:
    page.goto(f"{API}/docs", wait_until="networkidle", timeout=90_000)
    page.wait_for_timeout(2500)
    shot(page, "ui_16_swagger_api.png", full=True)


with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.contexts[0]
    page = context.new_page()
    page.set_viewport_size({"width": 1440, "height": 950})
    for step in (
        capture_overview,
        capture_analysis,
        capture_forecast,
        capture_explain,
        capture_pipeline,
        capture_swagger,
    ):
        step(page)
    page.close()
print("done")
