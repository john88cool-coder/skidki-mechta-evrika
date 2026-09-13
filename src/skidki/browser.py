"""Общий браузер Playwright для обоих магазинов.

Настоящий Chromium проходит JS-челлендж Cloudflare, которым закрыты оба сайта,
но только если не выдаёт себя за автоматизацию. Смок 2026-09-13 на mechta:
старый headless с подменённым UA (Chrome/128 при движке 151, бренд
HeadlessChrome в Client Hints, navigator.webdriver = true) получал 200 на
первый запрос к API и 403 «Just a moment» на все следующие. Новый headless с
родным UA без «HeadlessChrome» и без флага автоматизации — 12 из 12.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from playwright.async_api import Browser, BrowserContext, Route, async_playwright

# Картинки, шрифты и медиа данных не несут — не грузим их.
_BLOCKED_RESOURCES = frozenset({"image", "font", "media"})
_LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]
_HIDE_WEBDRIVER = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"


async def _block_heavy(route: Route) -> None:
    if route.request.resource_type in _BLOCKED_RESOURCES:
        await route.abort()
    else:
        await route.continue_()


async def _native_user_agent(browser: Browser) -> str:
    """Родной UA движка без «HeadlessChrome».

    Версия в UA обязана совпадать с Client Hints (sec-ch-ua): расхождение —
    готовый признак бота. Поэтому UA не придумываем, а только чистим.
    """
    page = await browser.new_page()
    try:
        agent = await page.evaluate("navigator.userAgent")
    finally:
        await page.close()
    return agent.replace("HeadlessChrome", "Chrome")


@asynccontextmanager
async def open_context(headless: bool = True) -> AsyncIterator[BrowserContext]:
    async with async_playwright() as playwright:
        # channel="chromium" — новый headless (полный Chromium), а не headless shell,
        # который представляется брендом HeadlessChrome.
        browser = await playwright.chromium.launch(
            headless=headless, channel="chromium", args=_LAUNCH_ARGS
        )
        try:
            context = await browser.new_context(
                user_agent=await _native_user_agent(browser), locale="ru-RU"
            )
            await context.add_init_script(_HIDE_WEBDRIVER)
            await context.route("**/*", _block_heavy)
            yield context
        finally:
            await browser.close()
