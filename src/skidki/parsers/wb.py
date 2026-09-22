"""wildberries (wildberries.kz / wildberries.ru) — API-парсер.

Использует публичные search/card API с dest для KZ:
  search: https://search.wb.ru/exactmatch/ru/common/v4/search?curr=kzt&dest=-3623895&query=<q>&resultset=catalog
  card  : https://card.wb.ru/cards/v1/detail?curr=kzt&nm=<ids>

Антибот WBAAS может отдать challenge — тогда _get вернёт HTTP !=200 и
парсер пропустит запрос (включён с ENABLED=False по умолчанию).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from ..models import Product

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext

    from ..config import Settings

SHOP = "wb"
BASE = "https://www.wildberries.kz"
ENABLED = False

SEARCH_URL = "https://search.wb.ru/exactmatch/ru/common/v4/search?ab_testid=fallback&appType=1&curr=kzt&dest=-3623895&resultset=catalog&query={q}&page={page}"
CARD_URL = "https://card.wb.ru/cards/v1/detail?curr=kzt&nm={ids}"

QUERIES: tuple[str, ...] = (
    "смартфон", "ноутбук", "телевизор", "холодильник", "стиральная машина",
)

log = logging.getLogger(__name__)


def _parse_search(data: dict) -> list[dict]:
    d = data.get("data") or {}
    return d.get("products") or []


def _to_product(item: dict) -> Product | None:
    nm = item.get("id") or item.get("nmId")
    name = item.get("name")
    price = item.get("salePriceU") or item.get("priceU")
    if not (nm and name and price):
        return None
    # priceU — в копейках *100 (WB формат)
    try:
        price_kzt = int(int(price) / 100)
    except Exception:
        return None
    old = item.get("priceU")
    old_kzt = None
    try:
        if old and int(old) > int(price):
            old_kzt = int(int(old) / 100)
    except Exception:
        old_kzt = None
    brand = item.get("brand")
    return Product(
        shop=SHOP, sku=str(nm), title=" ".join(str(name).split()),
        price=price_kzt, url=f"{BASE}/catalog/{nm}/detail.aspx",
        brand=brand, old_price=old_kzt,
        image=f"https://basket-01.wbbasket.ru/vol{int(nm)//100000}/part{int(nm)//1000}/{nm}/images/c516x688/1.webp" if nm else None,
    )


async def _get_json(context: BrowserContext, url: str) -> dict | None:
    try:
        r = await context.request.get(url, headers={"Accept": "application/json"}, timeout=20000)
        if r.status == 200:
            return await r.json()
        log.warning("wb %s: HTTP %s", url[:80], r.status)
    except Exception as exc:  # noqa: BLE001
        log.warning("wb %s: %s", url[:80], exc)
    return None


async def fetch(context: BrowserContext, config: Settings) -> list[Product]:
    if not ENABLED:
        log.info("wb: пропуск (ENABLED=False)")
        return []
    seen: set[str] = set()
    products: list[Product] = []
    for q in QUERIES:
        for page in range(1, 4):
            data = await _get_json(context, SEARCH_URL.format(q=q, page=page))
            if not data:
                break
            items = _parse_search(data)
            if not items:
                break
            for it in items:
                p = _to_product(it)
                if p and p.identity not in seen:
                    seen.add(p.identity)
                    products.append(p)
            await asyncio.sleep(0.5)
            if len(items) < 30:
                break
    if not products:
        from ..models import PartialCrawl
        raise PartialCrawl(products, "wb: пусто — antibot или нет данных")
    return products
