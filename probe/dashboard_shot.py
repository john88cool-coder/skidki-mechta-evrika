"""Скриншоты веб-панели: визуальная проверка рендера страниц.

Временная утилита разработки, не часть пайплайна:

    python probe/dashboard_shot.py http://localhost:4173
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

PAGES = {
    "dashboard": "/",
    "deals": "/deals",
    "shops": "/shops",
}


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:4173"
    out = Path("screenshots")
    out.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chromium")
        page = browser.new_page(viewport={"width": 1366, "height": 1000})
        for name, path in PAGES.items():
            page.goto(f"{base}{path}", wait_until="networkidle")
            page.wait_for_timeout(1200)  # ждём отрисовку графиков
            target = out / f"{name}.png"
            page.screenshot(path=str(target), full_page=True)
            text = page.inner_text("body")[:400].replace("\n", " | ")
            print(f"{name}: {target} — {text[:180]}")
        browser.close()


if __name__ == "__main__":
    main()
