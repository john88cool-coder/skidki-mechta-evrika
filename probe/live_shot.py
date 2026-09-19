"""Разовая проверка живого сайта: сколько <img> отрендерилось на главной."""

from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

URL = "https://john88cool-coder.github.io/skidki-mechta-evrika/"


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else "screenshots/live-thumbs.png"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chromium")
        page = browser.new_page(viewport={"width": 1366, "height": 900})
        try:
            page.goto(URL, wait_until="networkidle")
            page.wait_for_timeout(1500)
            count = page.evaluate("document.querySelectorAll('main img').length")
            print(f"img в карточках главной: {count}")
            page.screenshot(path=target)
            print(f"скриншот: {target}")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
