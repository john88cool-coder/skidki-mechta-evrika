"""alser.kz: POST /api/v2/mobapi-v3-get-catalog (разведка 2026-09-15).

Сайт — Nuxt; в SSR кладут только 8 витринных карточек, полный листинг категории
клиент получает POST'ом (проверено по network):

    POST https://alser.kz/api/v2/mobapi-v3-get-catalog
    Content-Type: application/json
    {"c_keyword": "<категория>", "page": N, "limit": 50,
     "location_id": 8, "only_local": false}

Ответ: `data.products[]` (id, sku, title, keyword, price, price_old, brand,
stocks_quantity, non_showcase, link_url) и `data.pagination` {page, perPage,
total, pageCount, hasNext}. Список категорий — из сайтмапа
https://alser.kz/uploads/sitemap/categories/root-categories.xml (страницы
/c/<keyword>/); это всегда актуально, новые категории подхватываются сами.

Вне браузера POST отвечает 404 на сайт-роуты Nitro, поэтому сначала заходят на
страницу сайта ради cookies, дальше — context.request.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import TYPE_CHECKING

from ..config import ALSER_GROUPS
from ..models import PartialCrawl, Product, new_products

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext

    from ..config import Settings

SHOP = "alser"
BASE = "https://alser.kz"
API = f"{BASE}/api/v2/mobapi-v3-get-catalog"
# Алматы — location_id из клиентского запроса сайта.
LOCATION_ID = 8
LIMIT = 50
MAX_PAGES = 50  # предохранитель: категорийный максимум — несколько страниц
CATEGORIES_SITEMAP = f"{BASE}/uploads/sitemap/categories/root-categories.xml"
CATEGORY_URL = re.compile(f"{BASE}/c/([a-z0-9-]+)</loc>")
REQUEST_PAUSE_S = 0.3

log = logging.getLogger(__name__)


def _group(keyword: str) -> str:
    lowered = keyword.casefold()
    for needle, group in ALSER_GROUPS:
        if needle in lowered:
            return group
    return "other"


def parse_categories(sitemap_xml: str) -> list[str]:
    """Ключи категорий /c/<keyword>/ из сайтмапа (без бренд-фильтров /f/)."""
    seen: set[str] = set()
    keywords: list[str] = []
    for match in CATEGORY_URL.finditer(sitemap_xml):
        keyword = match.group(1)
        if keyword not in seen:
            seen.add(keyword)
            keywords.append(keyword)
    return keywords


def parse(data: dict, group: str) -> list[Product]:
    payload = (data.get("data") or {})
    products: list[Product] = []
    for item in payload.get("products") or []:
        price = item.get("price")
        sku = item.get("sku")
        title = item.get("title")
        link = item.get("link_url")
        if not (price and sku and title and link):
            continue
        price = int(price)
        old = item.get("price_old")
        stocks = item.get("stocks_quantity")
        products.append(Product(
            shop=SHOP,
            sku=str(sku),
            title=" ".join(str(title).split()),
            price=price,
            url=link,
            brand=item.get("brand") or None,
            old_price=int(old) if old and int(old) > price else None,
            # Товар без информации о складе считаем доступным: сайт показывает
            # его в каталоге; «только витрина» — прочерк наличия.
            in_stock=bool(stocks is None or stocks > 0) and not item.get("non_showcase"),
            group=group,
            image=item.get("image") or None,
        ))
    return products


async def _categories(context: BrowserContext) -> list[str]:
    response = await context.request.get(CATEGORIES_SITEMAP, timeout=45_000)
    if response.status != 200:
        raise RuntimeError(f"сайтмап категорий: HTTP {response.status}")
    keywords = parse_categories(await response.text())
    if not keywords:
        raise RuntimeError("сайтмап категорий пуст — сменилась разметка?")
    return keywords


async def _post_page(context: BrowserContext, keyword: str, page: int, attempts: int = 3) -> dict:
    body = {
        "c_keyword": keyword,
        "page": page,
        "limit": LIMIT,
        "location_id": LOCATION_ID,
        "only_local": False,
    }
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = await context.request.post(
                API, data=json.dumps(body, ensure_ascii=False),
                headers={"Content-Type": "application/json"},
                timeout=45_000,
            )
            if response.status == 200:
                return await response.json()
            last_error = RuntimeError(f"HTTP {response.status}")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        log.warning("alser %s p%d: %s (попытка %d)", keyword, page, last_error, attempt + 1)
        if attempt < attempts - 1:
            await asyncio.sleep(5 * (attempt + 1))
    raise last_error or RuntimeError(f"{API}: не загрузилось")


async def fetch(context: BrowserContext, config: Settings) -> list[Product]:
    # Cookies сайта: без них POST на /api/v2/... отдаёт 404 Nitro-роута.
    page = await context.new_page()
    try:
        await page.goto(BASE, wait_until="domcontentloaded", timeout=config.page_timeout_ms)
    finally:
        await page.close()

    keywords = await _categories(context)
    log.info("alser: %d категорий из сайтмапа", len(keywords))

    seen: set[str] = set()
    products: list[Product] = []
    errors: list[str] = []
    for keyword in keywords:
        group = _group(keyword)
        try:
            first = await _post_page(context, keyword, 1)
            pagination = (first.get("data") or {}).get("pagination") or {}
            total = int(pagination.get("total") or 0)
            if total:
                products.extend(new_products(parse(first, group), seen))
            pages = min(int(pagination.get("pageCount") or 1), MAX_PAGES)
            for number in range(2, pages + 1):
                data = await _post_page(context, keyword, number)
                products.extend(new_products(parse(data, group), seen))
                await asyncio.sleep(REQUEST_PAUSE_S)
        except Exception as exc:  # noqa: BLE001 — категория не должна ронять обход
            log.warning("alser %s: %s", keyword, exc)
            errors.append(keyword)
        await asyncio.sleep(REQUEST_PAUSE_S)

    if not products:
        raise RuntimeError(f"ни одной позиции; упали категории: {len(errors)}")
    if len(errors) > len(keywords) * 0.1:
        raise PartialCrawl(products, f"не загрузились категории: {len(errors)} из {len(keywords)}")
    return products
