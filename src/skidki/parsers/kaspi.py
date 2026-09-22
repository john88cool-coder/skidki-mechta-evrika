"""kaspi.kz: HTML-парсер категории (маркетплейс, без открытого JSON API).

Категория: https://kaspi.kz/shop/c/<slug>/ — SSR HTML с карточками товаров.
Карточка ищется по ссылке /shop/p/<slug>-<id>/, цена — в тексте карточки.
Ограничения: без merchant-доступа API требует auth, поэтому парсим HTML.
По умолчанию отключён (enabled=False) — включать, когда нужен охват рынка
для «честной цены» (см. docs/KZ_MARKET_2026.md).

Разметка меняется чаще, чем у специалистов: парсер устойчив к отсутствию
цены/бренда — карточка без цены пропускается, без бренда — остаётся.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING
from urllib.parse import urljoin

from ..config import KASPI_CATEGORIES
from ..models import PartialCrawl, Product, new_products

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page

    from ..config import Settings

SHOP = "kaspi"
BASE = "https://kaspi.kz"
ENABLED = False  # включить, когда нужен рыночный медианный срез
MAX_PAGES = 10
RETAIL_LIMIT = 30  # карточек на страницу (эвристика пагинации HTML)

log = logging.getLogger(__name__)

LINK_RE = re.compile(r'href="(/shop/p/[^"]+)"')
TITLE_RE = re.compile(r'class="[^"]*item__title[^"]*"[^>]*>([^<]+)<', re.S)
PRICE_RE = re.compile(r"(\d[\d\s]*)\s*₸")
BRAND_RE = re.compile(r'class="[^"]*item__brand[^"]*"[^>]*>([^<]+)<', re.S)
IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"', re.S)


def _tenge(s: str) -> int | None:
    try:
        return int(s.replace(" ", "").replace("\xa0", "").replace("\u202f", ""))
    except Exception:
        return None


def category_url(slug: str, page: int) -> str:
    base = f"{BASE}/shop/c/{slug}/"
    return f"{base}?page={page}" if page > 1 else base


def parse(html: str, group: str | None = None) -> list[Product]:
    # Категория Kaspi: карточки содержат ссылку /shop/p/... — режем по ней
    products: list[Product] = []
    # Разбиваем по ссылкам на карточки, чтобы цена/бренд искались внутри карточки
    parts = re.split(r'(?=/shop/p/)', html)
    for part in parts:
        m = LINK_RE.search(part)
        if not m:
            continue
        href = m.group(1)
        # sku — последний сегмент id после последней "-"
        sku = href.rstrip("/").split("-")[-1].split("/")[0] or href
        title_m = TITLE_RE.search(part[:4000])
        price_m = PRICE_RE.search(part[:4000])
        if not title_m or not price_m:
            continue
        price = _tenge(price_m.group(1))
        if not price:
            continue
        title = " ".join(title_m.group(1).split())
        brand_m = BRAND_RE.search(part[:2000])
        brand = brand_m.group(1).strip() if brand_m else None
        img_m = IMG_RE.search(part[:4000])
        img = urljoin(BASE, img_m.group(1)) if img_m else None
        products.append(Product(
            shop=SHOP, sku=sku, title=title, price=price,
            url=urljoin(BASE, href), brand=brand, group=group, image=img,
        ))
    return products


async def _load(page: Page, url: str, timeout_ms: int) -> str:
    resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    if resp and resp.status == 200:
        return await page.content()
    raise RuntimeError(f"HTTP {resp.status if resp else 0} for {url}")


async def fetch(context: BrowserContext, config: Settings) -> list[Product]:
    if not ENABLED:
        # Не роняем обход, просто пропускаем — включение через ENABLED=True
        log.info("kaspi: пропуск (ENABLED=False)")
        return []
    seen: set[str] = set()
    products: list[Product] = []
    page = await context.new_page()
    try:
        for slug, group in KASPI_CATEGORIES.items():
            for p in range(1, MAX_PAGES + 1):
                try:
                    html = await _load(page, category_url(slug, p), config.page_timeout_ms)
                except Exception as exc:  # noqa: BLE001
                    log.warning("kaspi %s p%d: %s", slug, p, exc)
                    break
                cards = parse(html, group)
                if not cards:
                    break
                fresh = new_products(cards, seen)
                if not fresh:
                    break
                products.extend(fresh)
                if len(cards) < RETAIL_LIMIT:
                    break
                await asyncio.sleep(0.6)
    finally:
        await page.close()
    if not products:
        raise PartialCrawl(products, "kaspi: пусто — разметка сменилась или категории недоступны")
    return products
