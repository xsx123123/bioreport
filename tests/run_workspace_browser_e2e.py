"""Run the Workspace browser smoke flow against a running API and Vite app.

This is intentionally a standalone script because browser binaries are an
environment dependency. It does not create or mutate a production database.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:5174")
    parser.add_argument("--desktop", type=Path, default=Path("/tmp/bioreport-workspace-desktop.png"))
    parser.add_argument("--mobile", type=Path, default=Path("/tmp/bioreport-workspace-mobile.png"))
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise SystemExit("Install playwright to run this browser check") from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(args.base_url, wait_until="networkidle")
        page.get_by_text("Reports", exact=True).first.wait_for()
        report = page.locator("button.report-row").first
        report.wait_for()
        report.click()
        page.get_by_text("差异表达分析", exact=True).click()
        page.get_by_text("Evidence hash:", exact=False).wait_for()
        page.get_by_role("button", name="Generate interpretation").click()
        page.get_by_text("Deterministic evidence summary.", exact=False).wait_for()
        composer = page.get_by_label("Ask a scoped question")
        composer.fill("Which evidence snapshot is this conversation using?")
        composer.press("Enter")
        page.get_by_text("This conversation is scoped to", exact=False).wait_for()
        page.screenshot(path=str(args.desktop), full_page=True)

        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(args.mobile), full_page=True)
        assert not page.locator("text=Error").count(), "workspace rendered an Error state"
        browser.close()
    print(f"screenshots: {args.desktop} {args.mobile}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
