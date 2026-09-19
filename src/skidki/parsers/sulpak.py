"""sulpak.kz: SSR-первая страница + AJAX /Filter/LoadProducts (2026-09-15).

Категория — /f/<className>/almaty (22 карточки на страницу). Первая страница
приходит SSR, следующие отдаёт AJAX:

    GET /Filter/LoadProducts?className=<cat>&selectedPropertiesTokens=~
        &selectedActionsTokens=~&sort=PopularityDesc&listing=default
        &onPage=22&page=N&price=~
        X-Requested-With: XMLHttpRequest

Ответ — JSON: `products` (HTML-блоки карточек) и `paginator` (в нём
`data-pagesCount` — сразу всё число страниц). Карточка: `data-code`,
`data-name`, `data-price`, `data-brand`, ссылка /g/<slug>; зачёркнутая цена —
`div.product__item-price-old`, процент — `div.product__label-discount`;
«На витрине» и «Нет в наличии» — текстовые метки внутри блока.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from ..config import SULPAK_CATEGORIES
from ..models import PartialCrawl, Product, new_products

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page

    from ..config import Settings

SHOP = "sulpak"
BASE = "https://www.sulpak.kz"
PAGE_SIZE = 22
MAX_PAGES = 200  # предохранитель: smartfoniy ~45 страниц
# Паузы — от эпизодических лимитов и бэкпрессии sulpak; 404 на страницу
# LoadProducts трактуется как конец листинга (кэш paginator иногда врёт на 1).
REQUEST_PAUSE_S = 1.5
LIMIT_RETRY_PAUSE_S = 20
PASS_PAUSE_S = 60
MAX_PASSES = 2

CARD_BLOCK = re.compile(r'<div class="product__item product__item-js.*?(?=<div class="product__item product__item-js|$)', re.S)
DATA_CODE = re.compile(r'data-code="(\d+)"')
DATA_NAME = re.compile(r'data-name="([^"]*)"')
DATA_PRICE = re.compile(r'data-price="([\d.]+)"')
DATA_BRAND = re.compile(r'data-brand="([^"]*)"')
CARD_HREF = re.compile(r'href="(/g/[a-z0-9-]+)"')
OLD_PRICE = re.compile(r'product__item-price-old[^>]*>\s*([\d\s]+)\s*₸')
SHOWCASE = re.compile(r"На витрине")
OUT_OF_STOCK = re.compile(r"Нет в наличии")
# Миниатюра карточки: srcset/source с webp, либо img src.
IMG_SRC = re.compile(r'(?:srcset|src)="(https://object\.pscloud\.io[^"]+?\.webp)"')

log = logging.getLogger(__name__)


def load_products_url(class_name: str, page: int) -> str:
    query = urlencode({
        "className": class_name,
        "selectedPropertiesTokens": "~",
        "selectedActionsTokens": "~",
        "sort": "PopularityDesc",
        "listing": "default",
        "onPage": PAGE_SIZE,
        "page": page,
        "price": "~",
    })
    return f"{BASE}/Filter/LoadProducts?{query}"


def _image(block: str) -> str | None:
    """Миниатюра карточки: первый webp из srcset/source, иначе img src."""
    match = IMG_SRC.search(block)
    if match:
        return match.group(1)
    match = re.search(r'<img[^>]+src="([^"]+)"', block)
    return match.group(1) if match else None


def parse_blocks(html: str, group: str | None = None) -> list[Product]:
    """Карточки из HTML-блока (SSR или products из AJAX-ответа)."""
    products: list[Product] = []
    for match in CARD_BLOCK.finditer(html):
        block = match.group(0)
        code = DATA_CODE.search(block)
        price = DATA_PRICE.search(block)
        href = CARD_HREF.search(block)
        if not (code and price and href):
            continue
        name = DATA_NAME.search(block)
        brand_match = DATA_BRAND.search(block)
        old_match = OLD_PRICE.search(block)
        old = int(old_match.group(1).replace(" ", "").replace("\xa0", "")) if old_match else None
        price_int = int(float(price.group(1)))
        products.append(Product(
            shop=SHOP,
            sku=code.group(1),
            title=" ".join((name.group(1) if name else "").split()),
            price=price_int,
            url=f"{BASE}{href.group(1)}",
            brand=brand_match.group(1) if brand_match else None,
            old_price=old if old and old > price_int else None,
            in_stock=not OUT_OF_STOCK.search(block),
            stock_note="на витрине" if SHOWCASE.search(block) else None,
            group=group,
            image=_image(block),
        ))
    return products


def pages_count(paginator_html: str) -> int | None:
    match = re.search(r'data-pagesCount="(\d+)"', paginator_html)
    return int(match.group(1)) if match else None


def _dedupe(products: list[Product]) -> list[Product]:
    """AJAX дублирует каждый блок (список + плитка) — оставляем первые."""
    seen: set[str] = set()
    unique: list[Product] = []
    for product in products:
        if product.identity in seen:
            continue
        seen.add(product.identity)
        unique.append(product)
    return unique


async def _first_page(context: BrowserContext, class_name: str, timeout_ms: int, attempts: int = 3) -> str:
    url = f"{BASE}/f/{class_name}"
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = await context.request.get(url, timeout=timeout_ms, max_redirects=5)
            if response.status == 200:
                return await response.text()
            last_error = RuntimeError(f"HTTP {response.status}")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        log.warning("sulpak %s p1: %s (попытка %d)", class_name, last_error, attempt + 1)
        if attempt < attempts - 1:
            await asyncio.sleep(LIMIT_RETRY_PAUSE_S)
    raise last_error or RuntimeError(f"{url}: не загрузилось")


async def _load_ajax(context: BrowserContext, class_name: str, page_number: int, timeout_ms: int, attempts: int = 3) -> dict:
    url = load_products_url(class_name, page_number)
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = await context.request.get(
                url,
                timeout=timeout_ms,
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            if response.status == 200:
                return await response.json()
            last_error = RuntimeError(f"HTTP {response.status}")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        if attempt < attempts - 1:
            await asyncio.sleep(LIMIT_RETRY_PAUSE_S)
    raise last_error or RuntimeError(f"{url}: не загрузилось")


async def _crawl_category(
    context: BrowserContext, class_name: str, group: str | None,
    seen: set[str], timeout_ms: int, deadline: float,
) -> list[Product]:
    """Полная выгрузка категории; товары дедуплицируются с `seen`."""
    html = await _first_page(context, class_name, timeout_ms)
    products = new_products(parse_blocks(html, group), seen)
    # Число страниц знает AJAX: запрашиваем страницу 2; paginator в ответе
    # отдаёт data-pagesCount (даже если 2 > pagesCount). SSR-листинг содержит
    # переменное число карточек (промо-слоты), по нему не судим. У категории
    # с одной страницей LoadProducts?page=2 отвечает 404.
    await asyncio.sleep(REQUEST_PAUSE_S)
    try:
        ajax = await _load_ajax(context, class_name, 2, timeout_ms)
    except RuntimeError as exc:
        if "404" in str(exc):
            log.info("sulpak %s: страницы 2 нет — одна страница", class_name)
            return products
        raise
    pages = pages_count(ajax.get("paginator", "")) or 1
    products += new_products(_dedupe(parse_blocks(ajax.get("products", ""), group)), seen)
    for number in range(3, min(pages, MAX_PAGES) + 1):
        if time.monotonic() > deadline:
            raise RuntimeError(f"страница {number}: бюджет времени исчерпан")
        await asyncio.sleep(REQUEST_PAUSE_S)
        try:
            ajax = await _load_ajax(context, class_name, number, timeout_ms)
        except RuntimeError as exc:
            if "404" in str(exc):
                # Кэш paginator отдал страницу лишнюю — конец листинга.
                log.info("sulpak %s: p%d 404 — листинг кончился", class_name, number)
                break
            raise
        products += new_products(_dedupe(parse_blocks(ajax.get("products", ""), group)), seen)
    log.info("sulpak %s: %d позиций (страниц %d)", class_name, len(products), pages)
    return products


async def fetch(context: BrowserContext, config: Settings) -> list[Product]:
    # Cookies города: первая страница категории ставит cookies (город Алматы).
    page = await context.new_page()
    try:
        await page.goto(BASE, wait_until="domcontentloaded", timeout=config.page_timeout_ms)
    finally:
        await page.close()

    seen: set[str] = set()
    products: list[Product] = []
    deadline = time.monotonic() + config.evrika_budget_s
    # Кумулятивный лимит sulpak: после ~100 быстрых запросов часть категорий
    # отвечает 404 в течение нескольких минут, окно сбрасывается в тишине
    # (эксперимент 2026-09-15). Провальные категории возвращаются в следующих
    # проходах — пока идут остальные, лимит отдыхает.
    pending: list[str] = list(SULPAK_CATEGORIES)
    for pass_number in range(1, MAX_PASSES + 1):
        if not pending or time.monotonic() > deadline:
            break
        if pass_number > 1:
            log.info("sulpak: проход %d, категорий в очереди: %d", pass_number, len(pending))
            await asyncio.sleep(PASS_PAUSE_S)
        retry: list[str] = []
        for class_name in pending:
            group = SULPAK_CATEGORIES[class_name]
            try:
                products.extend(
                    await _crawl_category(
                        context, class_name, group, seen, config.page_timeout_ms, deadline
                    )
                )
            except Exception as exc:  # noqa: BLE001 — категория не должна ронять обход
                log.warning("sulpak %s (проход %d): %s", class_name, pass_number, exc)
                retry.append(class_name)
            await asyncio.sleep(REQUEST_PAUSE_S)
        pending = retry

    if not products:
        raise RuntimeError("ни одной позиции; все категории недоступны")
    if pending:
        raise PartialCrawl(products, f"не загрузились категории: {', '.join(pending[:5])} и ещё {len(pending) - 5}")
    return products
