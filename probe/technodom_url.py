"""Разведка правильного URL карточки technodom: читаем реальную ссылку из DOM
страницы каталога (туда магазин ведёт сам по клику), затем проверяем её
статус в браузере.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from skidki.browser import open_context  # noqa: E402

CATALOG = "https://www.technodom.kz/catalog/smartfony-i-gadzhety"


async def main() -> None:
    async with open_context() as context:
        page = await context.new_page()
        try:
            await page.goto(CATALOG, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(3000)
            html = await page.content()
            for pattern in (r'href="(/product/[^"]+)"', r'href="(/catalog/[^"]+)"'):
                links = sorted(set(re.findall(pattern, html)))
                print(f"{pattern}: {len(links)}")
                for link in links[:6]:
                    print("  ", link[:110])
            # главная находка: ссылки вида /product/... должны быть в HTML карточек
            cards = re.findall(r'href="(/product/[^"]+\d{5,}[^"]*)"', html)
            print(f"карточек /product/ с числом: {len(cards)}")
            if cards:
                url = f"https://www.technodom.kz{cards[0]}"
                response = await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                print(f"проба: {response.status if response else 0} {url[:110]}")
        finally:
            await page.close()


if __name__ == "__main__":
    asyncio.run(main())
