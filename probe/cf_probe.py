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
