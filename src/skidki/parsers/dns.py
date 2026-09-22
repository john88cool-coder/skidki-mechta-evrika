"""dns-shop.kz — CF challenge, как у mechta (через Playwright).

Каркас аналогичен mechta: грузим категорию в браузере, парсим HTML.
ENABLED=False — включать, когда нужен long-tail PC-компонентов.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..models import Product

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext

    from ..config import Settings

SHOP = "dns"
BASE = "https://www.dns-shop.kz"
ENABLED = False

log = logging.getLogger(__name__)


async def fetch(context: BrowserContext, config: Settings) -> list[Product]:  # noqa: ARG001
    if not ENABLED:
        log.info("dns: пропуск (ENABLED=False)")
        return []
    page = await context.new_page()
    try:
        await page.goto(f"{BASE}/catalog/", wait_until="domcontentloaded", timeout=30000)
        html = await page.content()
        # stub — реальный парсинг каталога DNS при включении
        _ = html
    except Exception as exc:  # noqa: BLE001
        log.warning("dns goto: %s", exc)
    finally:
        await page.close()
    return []
