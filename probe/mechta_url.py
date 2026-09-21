"""Проверка URL карточки mechta в браузерном контексте (Cloudflare пропускает)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from skidki.browser import open_context  # noqa: E402

URL = "https://www.mechta.kz/product/smartfon-apple-iphone-17-pro-256gb-silver/"


async def main() -> None:
    async with open_context() as context:
        page = await context.new_page()
        try:
            response = await page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
            print("mechta браузер:", response.status if response else 0, page.url)
        finally:
            await page.close()


if __name__ == "__main__":
    asyncio.run(main())
