"""evrika.com: Next.js SSR, товары в __NEXT_DATA__ (react-query dehydratedState).

Разведка 2026-09-13 (RECON_2026-09-13.md):
- категории — `/catalog/<slug>/c<id>`; товары отдают только листовые, верхние
  показывают витрину подкатегорий;
- `?page=N`, 50 товаров на страницу, `meta.last_page`;
- `cost` — текущая цена, `old_cost` — зачёркнутая (равна cost без скидки);
- SSR отвечает 12–35 с на страницу, поэтому страницы грузятся параллельно.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import TYPE_CHECKING

from ..config import EVRIKA_GROUPS, EVRIKA_ROOTS
from ..models import PartialCrawl, Product, new_products

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page

    from ..config import Settings

SHOP = "evrika"
BASE = "https://evrika.com"
MAX_PAGES = 60  # предохранитель: самая большая листовая категория — ~20 страниц
# Доля незагрузившихся страниц, после которой обход считается неполным.
FAILURE_TOLERANCE = 0.1

NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)

log = logging.getLogger(__name__)


def next_data(html: str) -> dict:
    match = NEXT_DATA.search(html)
    if not match:
        raise ValueError("нет __NEXT_DATA__ — челлендж Cloudflare или смена разметки")
    return json.loads(match.group(1))


def _query(data: dict, key: str):
    queries = (
        data.get("props", {}).get("pageProps", {}).get("dehydratedState", {}).get("queries", [])
    )
    for query in queries:
        query_key = query.get("queryKey") or []
        if query_key and query_key[0] == key:
            return query.get("state", {}).get("data")
    return None


def menu_tree(data: dict) -> list[dict]:
    return (_query(data, "categories/menutree") or {}).get("data") or []


def leaf_categories(tree: list[dict], roots: set[int]) -> list[tuple[int, str]]:
    """Листовые категории (id, slug) под заданными верхними."""
    by_id = {node["id"]: node for node in tree}
    parents = {node.get("parent_id") for node in tree}

    def root_of(node: dict) -> int:
        visited: set[int] = set()
        while node.get("parent_id") in by_id and node["id"] not in visited:
            visited.add(node["id"])
            node = by_id[node["parent_id"]]
        return node["id"]

    return [
        (node["id"], node["slug"])
        for node in tree
        if node["id"] not in parents and root_of(node) in roots
    ]


def category_groups(tree: list[dict], mapping: dict[int, str]) -> dict[int, str]:
    """Группа уведомлений каждой категории — по ближайшему предку из `mapping`."""
    by_id = {node["id"]: node for node in tree}
    groups: dict[int, str] = {}
    for node in tree:
        current, visited = node, set()
        while (
            current["id"] not in mapping
            and current.get("parent_id") in by_id
            and current["id"] not in visited
        ):
            visited.add(current["id"])
            current = by_id[current["parent_id"]]
        if current["id"] in mapping:
            groups[node["id"]] = mapping[current["id"]]
    return groups


def category_url(category_id: int, slug: str, page: int = 1) -> str:
    url = f"{BASE}/catalog/{slug}/c{category_id}"
    return f"{url}?page={page}" if page > 1 else url


def parse_products(data: dict, group: str | None = None) -> tuple[list[Product], int]:
    """Товары страницы и номер последней страницы категории."""
    block = _query(data, "products")
    if not block:
        return [], 0
    products: list[Product] = []
    for item in block.get("data") or []:
        cost = item.get("cost")
        pid = item.get("id")
        slug = item.get("slug")
        name = item.get("name")
        if not (cost and pid and slug and name):
            continue
        old = item.get("old_cost")
        products.append(Product(
            shop=SHOP,
            sku=str(pid),
            # В названиях evrika встречаются неразрывные пробелы.
            title=" ".join(name.split()),
            price=int(cost),
            url=f"{BASE}/catalog/{slug}/p{pid}",
            brand=item.get("brand") or None,
            category=item.get("category_name") or None,
            old_price=int(old) if old and old > cost else None,
            in_stock=bool(item.get("availableForPurchase") or item.get("availableForPurchaseFromDc")),
            stock_note="предзаказ" if item.get("is_preorder") else None,
            group=group,
        ))
    last_page = int((block.get("meta") or {}).get("last_page") or 1)
    return products, last_page


async def _new_page(context: BrowserContext) -> Page:
    page = await context.new_page()
    # Данные уже в HTML: JS и CSS приложения не нужны, а гидратация React на
    # 1,4 МБ страницы — основная нагрузка на процессор раннера. Скрипты
    # челленджа Cloudflare (/cdn-cgi/) не трогаем.
    await page.route("**/_next/static/**", lambda route: route.abort())
    return page


async def _load(page: Page, url: str, timeout_ms: int, attempts: int = 3) -> dict:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            status = response.status if response else 0
            if status == 200:
                return next_data(await response.text())
            last_error = RuntimeError(f"HTTP {status}")
        except Exception as exc:  # noqa: BLE001 — таймаут, обрыв, челлендж: повторяем
            last_error = exc
        if attempt < attempts - 1:
            await asyncio.sleep(5 * (attempt + 1))
    raise last_error or RuntimeError(f"{url}: не загрузилось")


async def fetch(context: BrowserContext, config: Settings) -> list[Product]:
    root_id, root_slug = EVRIKA_ROOTS[0]
    page = await _new_page(context)
    try:
        data = await _load(page, category_url(root_id, root_slug), config.page_timeout_ms)
    finally:
        await page.close()
    tree = menu_tree(data)
    leaves = leaf_categories(tree, {cid for cid, _ in EVRIKA_ROOTS})
    groups = category_groups(tree, EVRIKA_GROUPS)
    if not leaves:
        raise RuntimeError("дерево категорий пустое — сменилась разметка?")
    log.info("evrika: %d листовых категорий", len(leaves))

    queue: asyncio.Queue[tuple[int, str, int]] = asyncio.Queue()
    for category_id, slug in leaves:
        queue.put_nowait((category_id, slug, 1))
    seen: set[str] = set()
    products: list[Product] = []
    failures: list[str] = []
    queued = len(leaves)
    deadline = time.monotonic() + config.evrika_budget_s

    async def worker() -> None:
        nonlocal queued
        page = await _new_page(context)
        try:
            while True:
                category_id, slug, number = await queue.get()
                try:
                    if time.monotonic() > deadline:
                        failures.append(f"{slug} p{number}: бюджет времени исчерпан")
                        continue
                    try:
                        data = await _load(
                            page, category_url(category_id, slug, number), config.page_timeout_ms
                        )
                    except Exception as exc:  # noqa: BLE001 — страница не должна ронять обход
                        failures.append(f"{slug} p{number}: {exc}")
                        continue
                    items, last_page = parse_products(data, groups.get(category_id))
                    products.extend(new_products(items, seen))
                    if number == 1:
                        for extra in range(2, min(last_page, MAX_PAGES) + 1):
                            queue.put_nowait((category_id, slug, extra))
                            queued += 1
                finally:
                    queue.task_done()
        finally:
            await page.close()

    workers = [asyncio.create_task(worker()) for _ in range(max(1, config.evrika_concurrency))]
    drained = asyncio.create_task(queue.join())
    # Если все воркеры упали (например, браузер умер), join не дождётся никогда.
    all_dead = asyncio.gather(*workers, return_exceptions=True)
    try:
        await asyncio.wait({drained, all_dead}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        drained.cancel()
        for task in workers:
            task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

    if failures:
        log.warning(
            "evrika: не загрузилось страниц: %d, например: %s",
            len(failures), "; ".join(failures[:3]),
        )
    if not products:
        raise RuntimeError(f"ни одной позиции; ошибок страниц: {len(failures)}")
    if len(failures) > queued * FAILURE_TOLERANCE:
        raise PartialCrawl(products, f"не загрузилось страниц: {len(failures)} из {queued}")
    return products
