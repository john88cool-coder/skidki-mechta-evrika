"""ozon.kz — composer API (требует cookies/session, без них 307).

Каркас: пробует composer API с сессии контекста. Если 307/антибот — пропускает.
Включён с ENABLED=False.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..models import Product

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext

    from ..config import Settings

SHOP = "ozon"
BASE = "https://www.ozon.kz"
ENABLED = False

API = "https://www.ozon.kz/api/composer-api.bx/page/json/v2?url=/search/?text={q}&page={page}"
QUERIES = ("смартфон", "ноутбук", "телевизор", "холодильник")

log = logging.getLogger(__name__)


async def fetch(context: BrowserContext, config: Settings) -> list[Product]:  # noqa: ARG001
    if not ENABLED:
        log.info("ozon: пропуск (ENABLED=False)")
        return []
    # Заходим на главную ради cookies, затем composer
    page = await context.new_page()
    try:
        await page.goto(BASE, wait_until="domcontentloaded", timeout=30000)
    except Exception as exc:  # noqa: BLE001
        log.warning("ozon goto: %s", exc)
    finally:
        await page.close()

    products: list[Product] = []
    seen: set[str] = set()
    for q in QUERIES:
        for p in range(1, 4):
            url = API.format(q=q, page=p)
            try:
                r = await context.request.get(url, headers={"x-o3-app-name": "ozonapp_kz", "Accept": "application/json"}, timeout=20000)
                if r.status != 200:
                    log.warning("ozon %s: HTTP %s", url[:80], r.status)
                    break
                data = await r.json()
                # структура меняется — ищем товары эвристически
                # best-effort: если нет товаров — break
                # не фейлим обход, т.к. ENABLED=False по умолчанию
                _ = data  # placeholder for parsing when Ozon layout stabilizes
                break
            except Exception as exc:  # noqa: BLE001
                log.warning("ozon %s: %s", url[:80], exc)
                break
    if not products:
        log.info("ozon: пусто — каркас, парсинг будет доработан при включении")
    return products
