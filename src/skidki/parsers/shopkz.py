"""shop.kz: SSR-листинги Битрикса (разведка 2026-09-15).

Раздел каталога — /offers/<slug>/, пагинация ?PAGEN_1=N, 28 карточек на
страницу (SIZEN_1 игнорируется). Данные карточки уже в HTML:

- `data-product='{...}'` — JSON аналитики: `product_id`, `item_name`,
  `item_brand`, `item_category`, `price`, `dimension3` ("available"/…);
- `<link itemprop="url" href="/offer/<slug>/"` — ссылка карточки;
- `<div class="old_price"><span>729 990 ₸</span>` — зачёркнутая цена
  («цена по прайсу»), `<div class="current_price"><span>699 990 ₸</span>`
  — цена интернет-магазина.

Страницы грузятся параллельно воркерами; число страниц не отдают заранее,
поэтому идём по порядку, пока на странице есть карточки.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import TYPE_CHECKING

from ..config import SHOPKZ_SECTIONS
from ..models import PartialCrawl, Product, new_products

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page

    from ..config import Settings

SHOP = "shopkz"
BASE = "https://shop.kz"
MAX_PAGES = 200  # предохранитель: самая большая категория — ~100 страниц
FAILURE_TOLERANCE = 0.1  # доля незагрузившихся страниц, после которой PartialCrawl

DATA_PRODUCT = re.compile(r"data-product='([^']+)'")
CARD_URL = re.compile(r'<link itemprop="url" href="(/offer/[^"]+)"')
OLD_PRICE = re.compile(r'class="old_price">\s*<span>([\d\s]+)\s*₸')
CURRENT_PRICE = re.compile(r'class="current_price">\s*<span>([\d\s]+)\s*₸')
# Пагинация Битрикса отдаёт ссылки на первые страницы и на последнюю.
PAGE_LINK = re.compile(r'PAGEN_1=(\d+)')

log = logging.getLogger(__name__)


def _tenge(text: str) -> int:
    return int(text.replace(" ", "").replace("\xa0", ""))


def section_url(slug: str, page: int) -> str:
    base = f"{BASE}/offers/{slug}/"
    return f"{base}?PAGEN_1={page}" if page > 1 else base


def parse_cards(html: str, group: str | None = None) -> list[Product]:
    """Карточки страницы: сегменты между data-product='...'.

    Внутри сегмента после блока аналитики идут цены — старая («по прайсу») и
    текущая; если старой нет, current совпадает с price из JSON.
    """
    products: list[Product] = []
    blobs = list(DATA_PRODUCT.finditer(html))
    for index, match in enumerate(blobs):
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        end = blobs[index + 1].start() if index + 1 < len(blobs) else len(html)
        segment = html[match.start():end]
        url_match = CARD_URL.search(segment)
        price = data.get("price")
        pid = data.get("product_id")
        name = data.get("item_name")
        if not (price and pid and name and url_match):
            continue
        current = CURRENT_PRICE.search(segment)
        if current:
            price = _tenge(current.group(1))
        old_match = OLD_PRICE.search(segment)
        old = _tenge(old_match.group(1)) if old_match else None
        products.append(Product(
            shop=SHOP,
            sku=str(pid),
            title=" ".join(str(name).split()),
            price=int(price),
            url=f"{BASE}{url_match.group(1)}",
            brand=data.get("item_brand") or None,
            category=data.get("item_category") or None,
            old_price=old if old and old > price else None,
            # dimension3: "available" / "not available" — наличие карточки.
            in_stock=data.get("dimension3") != "not available",
            group=group,
            image=data.get("image") or None,
        ))
    return products


def last_page(html: str) -> int:
    """Число страниц раздела по ссылкам пагинации (максимум PAGEN_1)."""
    pages = [int(match) for match in PAGE_LINK.findall(html)]
    return max(pages, default=1)


def _new_page(context: BrowserContext):
    page = context.new_page()
    return page


async def _load(page: Page, url: str, timeout_ms: int, attempts: int = 3) -> str:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            status = response.status if response else 0
            if status == 200:
                return await response.text()
            last_error = RuntimeError(f"HTTP {status}")
        except Exception as exc:  # noqa: BLE001 — таймаут, обрыв: повторяем
            last_error = exc
        if attempt < attempts - 1:
            await asyncio.sleep(5 * (attempt + 1))
    raise last_error or RuntimeError(f"{url}: не загрузилось")


async def fetch(context: BrowserContext, config: Settings) -> list[Product]:
    queue: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
    for slug in SHOPKZ_SECTIONS:
        queue.put_nowait((slug, 1))
    seen: set[str] = set()
    products: list[Product] = []
    failures: list[str] = []
    queued = len(SHOPKZ_SECTIONS)
    deadline = time.monotonic() + config.evrika_budget_s

    async def worker() -> None:
        nonlocal queued
        page = await _new_page(context)
        try:
            while True:
                slug, number = await queue.get()
                try:
                    if time.monotonic() > deadline:
                        failures.append(f"{slug} p{number}: бюджет времени исчерпан")
                        continue
                    try:
                        html = await _load(page, section_url(slug, number), config.page_timeout_ms)
                    except Exception as exc:  # noqa: BLE001 — страница не роняет обход
                        failures.append(f"{slug} p{number}: {exc}")
                        continue
                    cards = parse_cards(html, SHOPKZ_SECTIONS[slug])
                    if not cards and number > 1:
                        # Пагинация раздела кончилась (HTTP 200, пустой листинг).
                        continue
                    products.extend(new_products(cards, seen))
                    if number == 1 and not cards:
                        failures.append(f"{slug} p1: пусто — раздел съехал?")
                    elif number == 1:
                        # Дальше — только реально существующие страницы.
                        for extra in range(2, min(last_page(html), MAX_PAGES) + 1):
                            queue.put_nowait((slug, extra))
                            queued += 1
                finally:
                    queue.task_done()
        finally:
            await page.close()

    workers = [asyncio.create_task(worker()) for _ in range(max(1, config.evrika_concurrency))]
    drained = asyncio.create_task(queue.join())
    # Если все воркеры упали (браузер умер), join не дождётся никогда.
    all_dead = asyncio.gather(*workers, return_exceptions=True)
    try:
        await asyncio.wait({drained, all_dead}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        drained.cancel()
        for task in workers:
            task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

    if failures:
        log.warning(
            "shopkz: не загрузилось страниц: %d, например: %s",
            len(failures), "; ".join(failures[:3]),
        )
    if not products:
        raise RuntimeError(f"ни одной позиции; ошибок страниц: {len(failures)}")
    if len(failures) > queued * FAILURE_TOLERANCE:
        raise PartialCrawl(products, f"не загрузилось страниц: {len(failures)} из {queued}")
    return products
