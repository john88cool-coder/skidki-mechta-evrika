"""Проверка ссылок карточек из среза панели: httpx + браузерный контекст.

    python probe/link_check.py [число ссылок на магазин]

httpx отдаёт то, что видит не-браузер (может попасть под антибот), браузер —
то, что увидит владелец по клику. Сверка показывает, где 404 реальные.
"""

from __future__ import annotations

import asyncio
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from skidki.browser import open_context  # noqa: E402

LIVE = "https://john88cool-coder.github.io/skidki-mechta-evrika/data/latest.json"
PER_SHOP = int(sys.argv[1]) if len(sys.argv) > 1 else 3

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def load_deals() -> list[dict]:
    with urllib.request.urlopen(LIVE, timeout=30) as response:
        return json.load(response)["deals"]


async def main() -> None:
    deals = load_deals()
    urls: list[tuple[str, str]] = []
    for deal in deals:
        shop = deal["product"]["shop"]
        if sum(1 for s, _ in urls if s == shop) >= PER_SHOP:
            continue
        urls.append((shop, deal["product"]["url"]))

    print("=== httpx (без браузера) ===")
    import httpx

    with httpx.Client(timeout=20, headers=UA, follow_redirects=True) as client:
        for shop, url in urls:
            try:
                response = client.get(url)
                print(f"  {response.status_code} {shop:<10} {url[:95]}")
            except Exception as exc:
                print(f"  {type(exc).__name__:<11} {shop:<10} {url[:95]}")

    print("=== браузер (как владелец) ===")
    async with open_context() as context:
        page = await context.new_page()
        for shop, url in urls:
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                status = response.status if response else 0
                print(f"  {status} {shop:<10} {url[:95]}")
            except Exception as exc:
                print(f"  {type(exc).__name__:<11} {shop:<10} {url[:95]}")
        await page.close()


if __name__ == "__main__":
    asyncio.run(main())
