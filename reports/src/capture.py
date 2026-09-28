"""Capture the evidence screenshots used by the report.

Repeatable on purpose: the figures in the report regenerate from a running
stack rather than being pasted in by hand.
"""

from __future__ import annotations

import os
import sys

from playwright.sync_api import sync_playwright

OUT = sys.argv[1] if len(sys.argv) > 1 else "shots"
FRONT = os.environ.get("FRONT", "http://localhost:3000")
API = os.environ.get("API", "http://localhost:8010")
MLFLOW = os.environ.get("MLFLOW", "http://localhost:5000")
os.makedirs(OUT, exist_ok=True)


def shot(page, name, full=False, clip=None):
    page.screenshot(path=f"{OUT}/{name}", full_page=full, clip=clip)
    print("shot", name)


with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 950})

    page.goto(FRONT, wait_until="networkidle", timeout=90_000)
    page.wait_for_timeout(2500)
    shot(page, "01_dashboard.png")

    page.goto(f"{FRONT}/symbols", wait_until="networkidle", timeout=90_000)
    page.wait_for_timeout(2000)
    shot(page, "02_symbols.png")

    page.goto(f"{FRONT}/forecast", wait_until="networkidle", timeout=90_000)
    page.wait_for_timeout(2000)
    selects = page.locator("select")
    if selects.count() >= 2:
        selects.nth(0).select_option("ACB")
        selects.nth(1).select_option("gru")
        page.wait_for_timeout(800)
    shot(page, "03_forecast_form.png")
    btn = page.get_by_role("button").last
    btn.click()
    page.wait_for_timeout(6000)
    shot(page, "04_forecast_chart.png")
    page.mouse.wheel(0, 1200)
    page.wait_for_timeout(1500)
    shot(page, "05_forecast_models.png")

    page.goto(f"{FRONT}/explainability", wait_until="networkidle", timeout=90_000)
    page.wait_for_timeout(4000)
    shot(page, "06_shap.png")

    page.goto(f"{API}/docs", wait_until="networkidle", timeout=90_000)
    page.wait_for_timeout(2500)
    shot(page, "07_swagger.png")

    try:
        page.goto(MLFLOW, wait_until="networkidle", timeout=60_000)
        page.wait_for_timeout(4000)
        shot(page, "08_mlflow_experiments.png")
        page.goto(f"{MLFLOW}/#/models", wait_until="networkidle", timeout=60_000)
        page.wait_for_timeout(4000)
        shot(page, "09_mlflow_registry.png")
    except Exception as exc:  # MLflow UI is optional evidence
        print("mlflow skipped:", exc)

    page.close()
print("done")
