"""Полный fetch() evrika по одной корневой категории — проверка конвейера."""
import asyncio
import sys
import time

sys.path.insert(0, "src")

from skidki.browser import open_context
from skidki.config import settings
from skidki.parsers import evrika

evrika.EVRIKA_ROOTS = ((171, "smartfony-i-gadzhety"),)  # только «Смартфоны и гаджеты»


async def main() -> None:
    started = time.monotonic()
    async with open_context() as context:
        products = await evrika.fetch(context, settings)
    print(f"позиций: {len(products)} за {time.monotonic() - started:.0f} с")
    shops = {p.group for p in products}
    print("группы:", sorted(g for g in shops if g))
    print("со скидкой:", sum(1 for p in products if p.old_price))
    print("категории:", len({p.category for p in products}))


asyncio.run(main())
