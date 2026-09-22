"""satu.kz (Prom/EVO) — HTML поиск.

Каркас: /search?query=<q> + пагинация. Включён с ENABLED=False.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING
from urllib.parse import quote

from ..models import Product

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page

    from ..config import Settings

SHOP = "satu"
BASE = "https://satu.kz"
ENABLED = False

QUERIES = ("смартфон", "ноутбук", "телевизор", "холодильник")
LINK_RE = re.compile(r'href="https?://[^"]*satu\.kz/[^"]*p\d+[^"]*"', re.I)
TITLE_RE = re.compile(r'class="[^"]*product[^"]*title[^"]*"[^>]*>([^<]+)<', re.I | re.S)
PRICE_RE = re.compile(r"(\d[\d\s]*)\s*₸")

log = logging.getLogger(__name__)


def parse(html: str) -> list[Product]:
    products: list[Product] = []
    # эвристика: режем по карточкам
    parts = re.split(r'(?=<a[^>]+satu\.kz)', html)
    for part in parts:
        m = LINK_RE.search(part)
        if not m:
            continue
        href = m.group(0).split('"')[1]
        sku = href.rstrip("/").split("-")[-1][:32] or href[-32:]
        t = TITLE_RE.search(part[:5000])
        pr = PRICE_RE.search(part[:5000])
        if not t or not pr:
            continue
        try:
            price = int(pr.group(1).replace(" ", "").replace("\xa0", ""))
        except Exception:
            continue
        title = " ".join(t.group(1).split())
        products.append(Product(shop=SHOP, sku=sku, title=title, price=price, url=href))
    return products


async def fetch(context: BrowserContext, config: Settings) -> list[Product]:
    if not ENABLED:
        log.info("satu: пропуск (ENABLED=False)")
        return []
    page = await context.new_page()
    products: list[Product] = []
    seen: set[str] = set()
    try:
        for q in QUERIES:
            url = f"{BASE}/search?query={quote(q)}"
            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=config.page_timeout_ms)
                if not resp or resp.status != 200:
                    continue
                html = await page.content()
                for p in parse(html):
                    if p.identity not in seen:
                        seen.add(p.identity)
                        products.append(p)
            except Exception as exc:  # noqa: BLE001
                log.warning("satu %s: %s", q, exc)
            await asyncio.sleep(0.6)
    finally:
        await page.close()
    return products
