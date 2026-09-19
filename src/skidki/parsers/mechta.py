"""mechta.kz: JSON API каталога, вызываемый fetch'ем изнутри открытой страницы.

Разведка 2026-09-13 (RECON_2026-09-13.md): сайт — Nuxt SPA, товары отдаёт
`/api/v3/catalog/products?slug=<раздел>&page=N&pageSize≤50`. Вне браузера
Cloudflare отвечает 403, а API без X-Mechta-Device-Id — 422
device_id_not_provided. Страница раздела даёт cookie Cloudflare и origin,
поэтому запросы идут из её контекста.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from ..config import MECHTA_GROUPS, MECHTA_SECTIONS
from ..models import PartialCrawl, Product, new_products

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page

    from ..config import Settings

SHOP = "mechta"
BASE = "https://www.mechta.kz"
PAGE_SIZE = 50  # максимум API: больше — 422 validation.max.numeric
MAX_PAGES = 200  # предохранитель от бесконечной пагинации
REQUEST_PAUSE_S = 0.5

log = logging.getLogger(__name__)

# Заголовки — из бандла mechta (/_nuxt/*.js, функция sae).
FETCH_JS = """async ({url, deviceId}) => {
    try {
        const r = await fetch(url, {headers: {
            'Accept': 'application/json, text/plain, */*',
            'X-Mechta-App': 'site',
            'X-Mechta-Device-Id': deviceId,
        }});
        return {status: r.status, body: await r.text()};
    } catch (e) {
        return {status: 0, body: String(e)};
    }
}"""


def api_url(slug: str, page: int) -> str:
    query = urlencode({"slug": slug, "page": page, "pageSize": PAGE_SIZE})
    return f"/api/v3/catalog/products?{query}"


def _stock_note(item: dict) -> str | None:
    if item.get("preorder"):
        return "предзаказ"
    if item.get("lowStock"):
        return "осталось мало"
    if item.get("onlyShopwindow"):
        return "на витрине"
    return None


def parse(data: dict, group: str | None = None) -> list[Product]:
    products: list[Product] = []
    for item in data.get("products") or []:
        prices = item.get("prices") or {}
        price = prices.get("finalPrice")
        code = item.get("code") or item.get("id")
        slug = item.get("slug")
        name = item.get("name")
        if not (price and code and slug and name):
            continue
        base = prices.get("basePrice")
        metrics = item.get("metrics") or {}
        # CDN mechta (pi.mdev.kz) умеет ресайз: ?w=400 даёт 17 КБ вместо 115 КБ
        # оригинала — для карточки панели и страницы товара этого достаточно.
        images = item.get("images") or []
        products.append(Product(
            shop=SHOP,
            sku=str(code),
            title=" ".join(name.split()),
            price=int(price),
            url=f"{BASE}/product/{slug}/",
            brand=metrics.get("brand") or None,
            category=metrics.get("category") or None,
            old_price=int(base) if base and base > price else None,
            in_stock=item.get("availability") == "available",
            stock_note=_stock_note(item),
            group=group,
            image=f"{images[0]}?w=400" if images else None,
        ))
    return products


def total_pages(data: dict) -> int:
    return int((data.get("meta") or {}).get("totalPages") or 0)


async def _get(page: Page, url: str, device_id: str, attempts: int = 3) -> dict:
    detail = ""
    for attempt in range(attempts):
        result = await page.evaluate(FETCH_JS, {"url": url, "deviceId": device_id})
        if result["status"] == 200:
            return json.loads(result["body"])
        detail = f"HTTP {result['status']}: {result['body'][:120]}"
        log.warning("mechta %s: %s (попытка %d)", url, detail, attempt + 1)
        if attempt < attempts - 1:
            await asyncio.sleep(5 * (attempt + 1))
            if result["status"] == 403:
                # Cloudflare переспросил челлендж — перезагрузка проходит его заново.
                await page.reload(wait_until="domcontentloaded")
    raise RuntimeError(f"{url} — {detail}")


async def fetch(context: BrowserContext, config: Settings) -> list[Product]:
    device_id = str(uuid.uuid4())
    seen: set[str] = set()
    products: list[Product] = []
    errors: list[str] = []
    page = await context.new_page()
    try:
        await page.goto(
            f"{BASE}/section/{MECHTA_SECTIONS[0]}/",
            wait_until="domcontentloaded",
            timeout=config.page_timeout_ms,
        )
        for slug in MECHTA_SECTIONS:
            try:
                number, pages = 1, 1
                while number <= min(pages, MAX_PAGES):
                    data = await _get(page, api_url(slug, number), device_id)
                    pages = total_pages(data)
                    products.extend(new_products(parse(data, MECHTA_GROUPS.get(slug)), seen))
                    number += 1
                    await asyncio.sleep(REQUEST_PAUSE_S)
            except Exception as exc:  # noqa: BLE001 — раздел не должен ронять весь магазин
                log.warning("mechta %s: %s", slug, exc)
                errors.append(slug)
    finally:
        await page.close()
    if not products:
        raise RuntimeError(f"ни одной позиции; упали разделы: {', '.join(errors) or '—'}")
    if errors:
        raise PartialCrawl(products, f"не загрузились разделы: {', '.join(errors)}")
    return products
