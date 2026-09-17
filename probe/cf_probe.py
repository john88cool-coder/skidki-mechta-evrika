"""Проба доступа с IP раннера GitHub Actions: варианты против Cloudflare.

Первый обход с Actions (2026-09-13): evrika — 3 677 позиций, mechta — 403
со страницей блокировки Cloudflare («no-js ie6 oldie») на каждый запрос к
API, хотя утренняя разовая проба с раннера проходила (старый headless, один
запрос). Проба сравнивает варианты и пишет итоги в аннотации (::notice) —
их видно через публичный API без входа, в отличие от логов.

Выход всегда 0: это диагностика, а не проверка.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid

import httpx
from playwright.async_api import BrowserContext, async_playwright

from skidki.browser import open_context
from skidki.config import settings
from skidki.parsers import evrika, mechta

SECTION = "tv-audio-video"
REQUESTS = 5
OLD_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def report(title: str, text: str) -> None:
    text = " ".join(text.split())
    print(f"{title}: {text}", flush=True)
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::notice title={title}::{text}", flush=True)


async def _via_page(context: BrowserContext) -> str:
    page = await context.new_page()
    try:
        response = await page.goto(
            f"{mechta.BASE}/section/{SECTION}/", wait_until="domcontentloaded", timeout=90_000
        )
        title = await page.title()
        device_id = str(uuid.uuid4())
        statuses = []
        for number in range(1, REQUESTS + 1):
            result = await page.evaluate(
                mechta.FETCH_JS, {"url": mechta.api_url(SECTION, number), "deviceId": device_id}
            )
            statuses.append(result["status"])
            await asyncio.sleep(1)
        return f"страница {response.status if response else 0} «{title[:40]}», API {statuses}"
    finally:
        await page.close()


async def mechta_new_headless() -> str:
    async with open_context() as context:
        return await _via_page(context)


async def mechta_old_headless() -> str:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context(user_agent=OLD_UA, locale="ru-RU")
            return await _via_page(context)
        finally:
            await browser.close()


def mechta_httpx() -> str:
    headers = {
        "User-Agent": OLD_UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru",
        "Referer": "https://www.mechta.kz/",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "X-Mechta-App": "site",
        "X-Mechta-Device-Id": str(uuid.uuid4()),
    }
    statuses = []
    with httpx.Client(timeout=30, headers=headers) as client:
        for number in range(1, REQUESTS + 1):
            statuses.append(client.get(mechta.BASE + mechta.api_url(SECTION, number)).status_code)
            time.sleep(1)
    return f"API {statuses}"


async def evrika_page() -> str:
    async with open_context() as context:
        page = await evrika._new_page(context)
        try:
            data = await evrika._load(
                page, evrika.category_url(310, "smart-chasy"), settings.page_timeout_ms
            )
        finally:
            await page.close()
    items, last_page = evrika.parse_products(data)
    return f"{len(items)} товаров, страниц {last_page}"


def _cards(html: str) -> int:
    return html.count("product__item product__item-js") or html.count("data-product='")


async def new_shops_httpx() -> str:
    """shop.kz и sulpak: обычные SSR-запросы, как их делает парсер."""
    import re

    results = []
    async with httpx.AsyncClient(
        timeout=30,
        headers={"User-Agent": OLD_UA, "Accept-Language": "ru"},
        follow_redirects=True,
    ) as client:
        r = await client.get("https://shop.kz/offers/smartfony/")
        cards = len(re.findall(r"data-product='([^']+)'", r.text))
        results.append(f"shop.kz HTTP {r.status_code}, карточек {cards}")

        r = await client.get("https://www.sulpak.kz/f/smartfoniy")
        results.append(f"sulpak SSR HTTP {r.status_code}, карточек {_cards(r.text)}")
        r = await client.get(
            "https://www.sulpak.kz/Filter/LoadProducts?className=smartfoniy"
            "&selectedPropertiesTokens=~&selectedActionsTokens=~&sort=PopularityDesc"
            "&listing=default&onPage=22&page=2&price=~",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        results.append(f"sulpak AJAX HTTP {r.status_code}")
    return "; ".join(results)


async def technodom_api() -> str:
    """API technodom требует cookies сайта — как в парсере: страница, затем API."""
    from skidki.parsers import technodom

    async with open_context() as context:
        page = await context.new_page()
        try:
            await page.goto(technodom.BASE, wait_until="domcontentloaded", timeout=90_000)
        finally:
            await page.close()
        data = await technodom._get(context, technodom.api_url("smart-chasy", 1))
    return f"товаров {len(data.get('payload') or [])}, total {data.get('total')}"


async def alser_api() -> str:
    """POST get-catalog тоже требует cookies сайта."""
    from skidki.parsers import alser

    async with open_context() as context:
        page = await context.new_page()
        try:
            await page.goto(alser.BASE, wait_until="domcontentloaded", timeout=90_000)
        finally:
            await page.close()
        data = await alser._post_page(context, "vse-smartfony", 1)
    payload = data.get("data") or {}
    return (
        f"товаров {len(payload.get('products') or [])}, "
        f"total {(payload.get('pagination') or {}).get('total')}"
    )


async def main() -> None:
    try:
        ip = httpx.get("https://api.ipify.org", timeout=10).text
    except Exception:  # noqa: BLE001
        ip = "?"
    report("IP раннера", ip)
    # Новый headless — первым и последним: видно, не «закрывает» ли Cloudflare
    # IP после первых запросов.
    variants = (
        ("mechta новый headless", mechta_new_headless),
        ("mechta старый headless", mechta_old_headless),
        ("mechta httpx", lambda: asyncio.to_thread(mechta_httpx)),
        ("evrika новый headless", evrika_page),
        ("shop.kz + sulpak httpx", new_shops_httpx),
        ("technodom API", technodom_api),
        ("alser API", alser_api),
        ("mechta новый headless повтор", mechta_new_headless),
    )
    for name, variant in variants:
        started = time.monotonic()
        try:
            result = await variant()
        except Exception as exc:  # noqa: BLE001 — проба должна отчитаться, а не упасть
            result = f"{type(exc).__name__}: {str(exc)[:150]}"
        report(name, f"{result} ({time.monotonic() - started:.0f} с)")


if __name__ == "__main__":
    asyncio.run(main())
