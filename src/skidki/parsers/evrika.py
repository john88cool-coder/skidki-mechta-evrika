"""evrika.com: Next.js App Router — RSC-поток + серверные карточки каталога.

Переезд сайта (сбор сломался 2026-09-28): Pages Router с `__NEXT_DATA__`
заменён на App Router. Теперь:
- дерево категорий — деигидратированное состояние react-query внутри
  RSC-потока (скрипты `self.__next_f.push`), достаётся из корневой категории;
- товары — серверно отрисованные карточки листовой категории: ссылка
  `__titleOfProduct`, цены `__currentPrice` и зачёркнутая `__oldPrice`,
  картинка в `data-original-src`; наличие — JSON-LD schema.org
  (`Offer.availability`);
- пагинация — ссылки `?page=N` (50 карточек на страницу).

SSR отвечает 12–35 с на страницу, поэтому страницы грузятся параллельно.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from html import unescape
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

RSC_PUSH = re.compile(r"<script[^>]*>self\.__next_f\.push\((\[.*?\])\)</script>", re.S)
# props HydrationBoundary: {"state": {"mutations": [], "queries": [...]}}
STATE_OPEN = '{"state":{"mutations":'
# Ряд RSC-потока: <hex-id>:<значение до начала следующего ряда>
RSC_ROW = re.compile(r"(?m)^([0-9a-f]{1,7}):")
LD_JSON = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
PAGE_LINK = re.compile(r"[?&]page=(\d+)")
CARD_ANCHOR = re.compile(r'titleOfProduct[^"]*"[^>]*href="([^"]+?/p(\d+))"[^>]*>(.*?)</a>', re.S)
# Класс цены может идти с суффиксом (`currentPrice_less`); у зачёркнутой цены
# lookahead отсекает `oldPriceContainer` (там бонусы, не цена).
CURRENT_PRICE = re.compile(r'__currentPrice[^"]*">\s*([\d\s\u00a0]+)')
OLD_PRICE = re.compile(r'__oldPrice(?!Container)[^"]*">\s*([\d\s\u00a0]+)')
CARD_IMAGE = re.compile(r'data-original-src="([^"]+)"')
OUT_OF_STOCK = "OutOfStock"

log = logging.getLogger(__name__)


def _rsc_blob(html: str) -> str:
    """Полётные данные App Router: склейка строк всех self.__next_f.push."""
    parts: list[str] = []
    for match in RSC_PUSH.finditer(html):
        try:
            chunks = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        parts.extend(chunk for chunk in chunks[1:] if isinstance(chunk, str))
    return "".join(parts)


def _json_at(blob: str, start: int) -> str:
    """JSON-объект из блоба с позиции start (с учётом строк и экранирования)."""
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(blob)):
        char = blob[i]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
            if depth == 0:
                return blob[start : i + 1]
    raise ValueError("незакрытый JSON в RSC-потоке")


def _rsc_rows(blob: str) -> dict[str, object]:
    """Ряды RSC-потока: id → JSON-значение (что не парсится — None)."""
    starts = [(m.group(1), m.end(), m.start()) for m in RSC_ROW.finditer(blob)]
    rows: dict[str, object] = {}
    for idx, (rid, value_start, _) in enumerate(starts):
        value_end = starts[idx + 1][2] if idx + 1 < len(starts) else len(blob)
        raw = blob[value_start:value_end].rstrip("\n")
        try:
            rows[rid] = json.loads(raw)
        except json.JSONDecodeError:
            rows[rid] = None
    return rows


def _resolve_ref(rows: dict[str, object], ref: str, depth: int = 0) -> object:
    """RSC-ссылка `$<ряд>:<ключ>:<индекс>:…` → данные по пути в ряде.

    В элемент-массиве `["$","тип",null,props]` именованные слоты — это индексы
    (props → 3), как их нумерует клиент React Flight.
    """
    element_slots = {"props": 3, "type": 1, "key": 2}
    if depth > 5 or not ref.startswith("$"):
        return None
    parts = ref[1:].split(":")
    value = rows.get(parts[0])
    for part in parts[1:]:
        if isinstance(value, list):
            index = element_slots.get(part) if part in element_slots else (
                int(part) if part.isdigit() else None
            )
            value = value[index] if index is not None and index < len(value) else None
        elif isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    if isinstance(value, str) and value.startswith("$"):
        return _resolve_ref(rows, value, depth + 1)
    return value


def flight_state(html: str) -> dict:
    """Деигидратированное состояние react-query из RSC-потока страницы."""
    blob = _rsc_blob(html)
    queries: list[dict] = []
    i = blob.find(STATE_OPEN)
    while i != -1:
        try:
            props = json.loads(_json_at(blob, i))
        except (ValueError, json.JSONDecodeError):
            props = None
        if isinstance(props, dict):
            inner = props["state"] if isinstance(props.get("state"), dict) else props
            found = inner.get("queries")
            if isinstance(found, list):
                queries.extend(q for q in found if isinstance(q, dict))
        i = blob.find(STATE_OPEN, i + 1)
    if not queries:
        raise ValueError("нет RSC-состояния react-query — челлендж Cloudflare или смена разметки")
    # Данные query могут быть ссылкой (`$2:props:…`) — резолвим по рядам потока.
    rows = _rsc_rows(blob)
    for query in queries:
        state = query.get("state")
        if not isinstance(state, dict):
            continue
        data = state.get("data")
        if isinstance(data, str) and data.startswith("$"):
            state["data"] = _resolve_ref(rows, data)
    return {"queries": queries}


def _query(data: dict, key: str):
    for query in data.get("queries", []):
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


def _price(text: str) -> int:
    return int(re.sub(r"\D", "", text) or 0)


def _last_page(html: str) -> int:
    pages = [int(p) for p in PAGE_LINK.findall(html)]
    if pages:
        return max(pages)
    return 2 if 'rel="next"' in html else 1


def _ld_availability(html: str) -> dict[str, bool]:
    """sku → есть ли товар в наличии, по JSON-LD (schema.org Offer)."""
    availability: dict[str, bool] = {}
    for match in LD_JSON.finditer(html):
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        offers = data.get("offers") if isinstance(data, dict) else None
        if isinstance(offers, dict):  # AggregateOffer
            offers = offers.get("offers")
        if not isinstance(offers, list):
            continue
        for offer in offers:
            if not isinstance(offer, dict):
                continue
            sku = re.search(r"/p(\d+)$", str(offer.get("url") or ""))
            if sku:
                availability[sku.group(1)] = not str(
                    offer.get("availability") or ""
                ).endswith(OUT_OF_STOCK)
    return availability


def parse_page(
    html: str, group: str | None = None, category: str | None = None
) -> tuple[list[Product], int]:
    """Товары листовой категории из SSR-карточек и номер последней страницы."""
    # Цены и названия приходят с HTML-сущностями (&nbsp; в разрядах цен,
    # &amp; в названиях) — декодируем один раз до разбора.
    html = unescape(html)
    cards = html.split("productCard-ui")[1:]
    if not cards:
        # Пустая листовая категория валидна, если в потоке есть состояние
        # react-query; без него — челлендж или смена разметки.
        if STATE_OPEN not in _rsc_blob(html):
            raise ValueError("нет карточек и RSC-состояния — челлендж Cloudflare или смена разметки")
        return [], _last_page(html)
    in_stock = _ld_availability(html)
    products: list[Product] = []
    for chunk in cards:
        anchor = CARD_ANCHOR.search(chunk)
        if not anchor:
            continue
        current = CURRENT_PRICE.search(chunk)
        price = _price(current.group(1)) if current else 0
        if not price:
            continue
        old = OLD_PRICE.search(chunk)
        image = CARD_IMAGE.search(chunk)
        title = " ".join(re.sub(r"<[^>]+>", " ", anchor.group(3)).split())
        products.append(Product(
            shop=SHOP,
            sku=anchor.group(2),
            title=title,
            price=price,
            url=f"{BASE}{anchor.group(1)}",
            category=category,
            old_price=_price(old.group(1)) if old else None,
            in_stock=in_stock.get(anchor.group(2), True),
            group=group,
            image=image.group(1) if image else None,
        ))
    return products, _last_page(html)


async def _new_page(context: BrowserContext) -> Page:
    page = await context.new_page()
    # Данные уже в HTML: JS и CSS приложения не нужны, а гидратация React на
    # 1,4 МБ страницы — основная нагрузка на процессор раннера. Скрипты
    # челленджа Cloudflare (/cdn-cgi/) не трогаем.
    await page.route("**/_next/static/**", lambda route: route.abort())
    return page


async def _load(page: Page, url: str, timeout_ms: int, attempts: int = 3) -> str:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            status = response.status if response else 0
            if status == 200:
                return await response.text()
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
        html = await _load(page, category_url(root_id, root_slug), config.page_timeout_ms)
    finally:
        await page.close()
    tree = menu_tree(flight_state(html))
    leaves = leaf_categories(tree, {cid for cid, _ in EVRIKA_ROOTS})
    groups = category_groups(tree, EVRIKA_GROUPS)
    names = {node["id"]: node.get("name") for node in tree}
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
                        page_html = await _load(
                            page, category_url(category_id, slug, number), config.page_timeout_ms
                        )
                        items, last_page = parse_page(
                            page_html,
                            group=groups.get(category_id),
                            category=names.get(category_id),
                        )
                    except Exception as exc:  # noqa: BLE001 — страница не должна ронять обход
                        failures.append(f"{slug} p{number}: {exc}")
                        continue
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
