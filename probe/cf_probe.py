"""Проба: пускает ли Cloudflare наш IP к mechta.kz и evrika.com (через Playwright).

Настоящий Chromium проходит JS-челлендж Cloudflare; API mechta вызывается
fetch'ем из контекста открытой страницы — с cookie и TLS-отпечатком браузера.
Запускается локально и в GitHub Actions (workflow probe.yml) ДО написания
основного бота. Выход 0 — оба магазина отдали товары, 1 — хотя бы один нет.
"""

from __future__ import annotations

import json
import sys
import time

from playwright.sync_api import Browser, Page, sync_playwright

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
EVRIKA_TIMEOUT_MS = 90_000
# Картинки, шрифты и медиа данных не несут — не грузим их.
_BLOCKED_RESOURCES = {"image", "font", "media"}

# Заголовки взяты из бандла mechta (/_nuxt/*.js, функция sae): без
# X-Mechta-Device-Id API отвечает 422 device_id_not_provided.
MECHTA_FETCH = """async (url) => {
    const deviceId = localStorage.getItem('user_device_id') || crypto.randomUUID();
    const r = await fetch(url, {headers: {
        'Accept': 'application/json, text/plain, */*',
        'X-Mechta-App': 'site',
        'X-Mechta-Device-Id': deviceId,
    }});
    return {status: r.status, body: await r.text()};
}"""


def _new_page(browser: Browser) -> Page:
    page = browser.new_page(user_agent=UA, locale="ru-RU")
    page.route(
        "**/*",
        lambda route: route.abort()
        if route.request.resource_type in _BLOCKED_RESOURCES
        else route.continue_(),
    )
    return page


def probe_mechta(browser: Browser) -> tuple[bool, str]:
    page = _new_page(browser)
    try:
        page.goto("https://www.mechta.kz/section/tv-audio-video/", wait_until="domcontentloaded")
        api = "/api/v3/catalog/products?slug=tv-audio-video&page=1&pageSize=50"
        result = page.evaluate(MECHTA_FETCH, api)
    finally:
        page.close()
    if result["status"] != 200:
        return False, f"HTTP {result['status']}: {result['body'][:120]!r}"
    data = json.loads(result["body"])
    products = data.get("products") or []
    if not products:
        return False, f"пустой список: {result['body'][:120]!r}"
    first = products[0]
    return True, (
        f"{len(products)} товаров, всего {data['meta']['totalCount']}; "
        f"пример: {first['name']} — {first['prices']['finalPrice']} ₸"
    )


def probe_evrika(browser: Browser) -> tuple[bool, str]:
    page = _new_page(browser)
    try:
        # SSR evrika отвечает 12–35 с — стандартных 30 с goto не хватает.
        response = page.goto(
            "https://evrika.com/catalog/smart-chasy/c310",
            wait_until="domcontentloaded",
            timeout=EVRIKA_TIMEOUT_MS,
        )
        status = response.status if response else 0
        raw = page.locator("#__NEXT_DATA__").text_content(timeout=15_000) if status == 200 else None
    finally:
        page.close()
    if status != 200:
        return False, f"HTTP {status}"
    if not raw:
        return False, "нет __NEXT_DATA__ (челлендж Cloudflare?)"
    queries = json.loads(raw)["props"]["pageProps"]["dehydratedState"]["queries"]
    block = next((q["state"]["data"] for q in queries if q["queryKey"][0] == "products"), None)
    if not block or not block["data"]:
        return False, "в __NEXT_DATA__ нет товаров"
    first = block["data"][0]
    return True, (
        f"{len(block['data'])} товаров, всего {block['meta']['total']}; "
        f"пример: {first['name']} — {first['cost']} ₸ (было {first['old_cost']})"
    )


def main() -> int:
    ok_all = True
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            for name, probe in (("mechta", probe_mechta), ("evrika", probe_evrika)):
                started = time.monotonic()
                try:
                    ok, detail = probe(browser)
                except Exception as exc:  # noqa: BLE001 — проба должна отчитаться, а не упасть
                    ok, detail = False, f"{type(exc).__name__}: {str(exc)[:200]}"
                elapsed = time.monotonic() - started
                print(f"{'OK  ' if ok else 'FAIL'} {name:7} {elapsed:5.1f}s  {detail}", flush=True)
                ok_all &= ok
        finally:
            browser.close()
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
