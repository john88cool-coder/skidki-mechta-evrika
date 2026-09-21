"""technodom.kz: JSON API каталога через context.request (разведка 2026-09-15).

Сайт — Next.js, но SSR кладёт товары в разметку только на первой странице
категории; страницы 2+ SSR отдаёт пустыми, догружая их клиентом с API. Поэтому
товары берут напрямую:

    GET https://api.technodom.kz/katalog/api/v2/products/category/<slug>
        ?city_id=...&limit=50&page=N[&sorting=discount:desc]

Ветку отдаёт целиком по верхнему узлу (по /catalog/smartfony-i-gadzhety API
возвращает все ~1 650 позиций с подкатегориями). Вне браузера API отвечает
404 на /katalog/..., поэтому сначала заходят на страницу сайта ради cookies
Cloudflare, дальше запросы идут из контекста (context.request).

Сортировка `discount:desc` — легальная (API: «можно использовать только
created_at|price|rating|score|discount»); скидочные позиции идут первыми,
так что при неполном обходе собранное полезнее. Поля товара: `sku`, `title`,
`price`, `old_price`, `uri` (карточка: /product/<uri>), `brand`, `discount`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
from urllib.parse import quote

from ..config import TECHNODOM_ROOTS
from ..models import PartialCrawl, Product, new_products

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext

    from ..config import Settings

SHOP = "technodom"
BASE = "https://www.technodom.kz"
API = "https://api.technodom.kz/katalog/api/v2/products/category"
# Алматы — город по умолчанию сайта (id из __NEXT_DATA__ главной).
CITY_ID = "5f5f1e3b4c8a49e692fefd70"
LIMIT = 50  # api держит limit=99+; 50 — как pageSize сайта
MAX_PAGES = 200  # предохранитель от бесконечной пагинации
REQUEST_PAUSE_S = 0.4

log = logging.getLogger(__name__)


def api_url(slug: str, page: int) -> str:
    return (
        f"{API}/{quote(slug)}"
        f"?city_id={CITY_ID}&limit={LIMIT}&page={page}&sorting=discount:desc"
    )


def parse(data: dict, group: str | None = None) -> list[Product]:
    products: list[Product] = []
    for item in data.get("payload") or []:
        price = item.get("price")
        sku = item.get("sku")
        title = item.get("title")
        uri = item.get("uri")
        if not (price and sku and title and uri):
            continue
        price = int(price)
        old = item.get("old_price")
        images = item.get("images") or []
        products.append(Product(
            shop=SHOP,
            sku=str(sku),
            title=" ".join(str(title).split()),
            price=price,
            url=f"{BASE}/p/{uri}",
            brand=item.get("brand") or None,
            category=item.get("categories_ru")[-1] if item.get("categories_ru") else None,
            old_price=int(old) if old and int(old) > price else None,
            group=group,
            image=f"https://api.technodom.kz/f3/api/v1/images/{images[0]}.webp" if images else None,
        ))
    return products


async def _get(context: BrowserContext, url: str, attempts: int = 3) -> dict:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = await context.request.get(url, timeout=45_000)
            if response.status == 200:
                return await response.json()
            last_error = RuntimeError(f"HTTP {response.status}")
        except Exception as exc:  # noqa: BLE001 — таймаут/обрыв: повторяем
            last_error = exc
        log.warning("technodom %s: %s (попытка %d)", url, last_error, attempt + 1)
        if attempt < attempts - 1:
            await asyncio.sleep(5 * (attempt + 1))
    raise last_error or RuntimeError(f"{url}: не загрузилось")


async def fetch(context: BrowserContext, config: Settings) -> list[Product]:
    # Cookies Cloudflare: страница сайта ставит их и api.technodom.kz перестаёт
    # отвечать 404 на /katalog/.
    page = await context.new_page()
    try:
        await page.goto(BASE, wait_until="domcontentloaded", timeout=config.page_timeout_ms)
    finally:
        await page.close()

    seen: set[str] = set()
    products: list[Product] = []
    errors: list[str] = []
    for root, group in TECHNODOM_ROOTS.items():
        try:
            first = await _get(context, api_url(root, 1))
            total = int(first.get("total") or 0)
            pages = min((total + LIMIT - 1) // LIMIT or 1, MAX_PAGES)
            products.extend(new_products(parse(first, group), seen))
            for number in range(2, pages + 1):
                data = await _get(context, api_url(root, number))
                products.extend(new_products(parse(data, group), seen))
                await asyncio.sleep(REQUEST_PAUSE_S)
            log.info("technodom %s: %d позиций (total=%d)", root, len(products), total)
        except Exception as exc:  # noqa: BLE001 — ветка не должна ронять весь магазин
            log.warning("technodom %s: %s", root, exc)
            errors.append(root)
    if not products:
        raise RuntimeError(f"ни одной позиции; упали ветки: {', '.join(errors) or '—'}")
    if errors:
        raise PartialCrawl(products, f"не загрузились ветки: {', '.join(errors)}")
    return products
