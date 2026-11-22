"""Формат точной ценовой цели из карточки товара (задача 8) — общий с фронтендом.

Веб-карточка строит `w2_<base64url(UTF8(JSON.stringify([shop, sku, maxPrice])))>`
без padding (`web/src/lib/utils/watch-link.ts`); бот разбирает тот же формат.
В payload входят только публичные данные — магазин, точный SKU и целевая цена:
ни title, ни chat_id, ни токен бота в ссылку не попадают.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import escape
from http import HTTPStatus
from typing import Callable, Protocol

import httpx

from .catalog_export import SCHEMA_VERSION
from .models import Product
from .report import SHOP_LABELS, tenge
from .storage import (
    ItemWatch,
    ItemWatchEvent,
    connect,
    get_item_watch,
    get_item_watch_state,
    list_item_watches,
    mark_item_watch_events_delivered,
    now,
    pending_item_watch_events,
    record_item_watch_event,
    set_item_watch_state,
    delete_item_watch_events,
)

# Строгий список магазинов: только включённые парсеры (REGISTRY без каркасов).
SHOPS = ("mechta", "evrika", "shopkz", "sulpak", "technodom", "alser")
PRICE_MIN = 1
PRICE_MAX = 999_999_999
PAYLOAD_PREFIX = "w2_"
START_LIMIT = 64  # лимит параметра deep-link /start в Telegram
MESSAGE_LIMIT = 4096  # лимит текста сообщения Telegram
WATCH_COMMAND = "/watchitem"

# Тело payload — строго base64url-алфавит, padding запрещён.
_PAYLOAD_BODY_RE = re.compile(r"[A-Za-z0-9_-]+")


@dataclass(frozen=True)
class ItemTarget:
    """Разобранная цель: магазин, точный SKU, порог в тенге."""

    shop: str
    sku: str
    max_price: int


class ItemLookup(Protocol):
    """Адаптер задачи 9: поиск товара по индексу выбранного магазина."""

    def lookup(self, shop: str, sku: str) -> Product | None: ...


class NoLookup:
    """Заглушка до задачи 9: индексы магазинов ещё не подключены."""

    def lookup(self, shop: str, sku: str) -> Product | None:
        return None


def _valid_target(shop: str, sku: str, max_price: int) -> bool:
    return (
        shop in SHOPS
        and isinstance(sku, str)
        and sku.strip() != ""
        and isinstance(max_price, int)
        and not isinstance(max_price, bool)
        and PRICE_MIN <= max_price <= PRICE_MAX
    )


def encode_payload(shop: str, sku: str, max_price: int) -> str | None:
    """Строит w2_-payload; None — данные не проходят валидацию или команда
    `/watchitem <payload>` не помещается в лимит сообщения Telegram."""
    if not _valid_target(shop, sku, max_price):
        return None
    raw = json.dumps([shop, sku, max_price], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    payload = PAYLOAD_PREFIX + base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    if len(WATCH_COMMAND) + 1 + len(payload) > MESSAGE_LIMIT:
        return None
    return payload


def decode_payload(payload: str) -> ItemTarget | None:
    """Разбирает payload с полной валидацией; None — повреждён или подделан."""
    if not isinstance(payload, str) or not payload.startswith(PAYLOAD_PREFIX):
        return None
    body = payload[len(PAYLOAD_PREFIX) :]
    if not _PAYLOAD_BODY_RE.fullmatch(body):
        return None
    padded = body + "=" * (-len(body) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        text = raw.decode("utf-8")
        parsed = json.loads(text)
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(parsed, list) or len(parsed) != 3:
        return None
    shop, sku, max_price = parsed
    if not isinstance(shop, str) or shop not in SHOPS:
        return None
    if not isinstance(sku, str) or sku.strip() == "":
        return None
    if not isinstance(max_price, int) or isinstance(max_price, bool):
        return None
    if not PRICE_MIN <= max_price <= PRICE_MAX:
        return None
    return ItemTarget(shop, sku, max_price)


# ==================== Задача 9: доставка личных оповещений ====================

log = logging.getLogger("skidki.item_watch")

# Порог устаревания среза — тот же, что на панели (export.py stale_after и
# merge.ts staleAfterMs): обход расписан раз в 2 часа, 6 часов — запас.
STALE_AFTER = timedelta(hours=6)
# Ограничение размера ответа: index.json крупнейшего магазина ~ единицы МБ.
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
# Фиксированный разрешённый URL панели (GitHub Pages проекта). Администратор
# может переопределить корень переменной окружения SKIDKI_PANEL_URL; ссылки
# из внешних источников не принимаются никогда.
DEFAULT_PANEL_URL = "https://john88cool-coder.github.io/skidki-mechta-evrika/"
PANEL_URL_ENV = "SKIDKI_PANEL_URL"
HTTP_ATTEMPTS = 3  # повтор загрузки с задержкой
RETRY_DELAY_S = 5.0
HTTP_TIMEOUT_S = 15.0

EVENT_PRICE = "price"  # цена впервые оказалась не выше порога
EVENT_RESTOCK = "restock"  # возврат: отсутствие → наличие при цене ниже цели


def panel_url() -> str:
    """Разрешённый корень панели: код или настройка администратора."""
    return os.environ.get(PANEL_URL_ENV) or DEFAULT_PANEL_URL


@dataclass(frozen=True)
class ItemObservation:
    """Срез одного магазина из опубликованного каталога выбранной стороны."""

    shop: str
    side: str  # 'local' | 'cloud'
    version: str  # f"{side}:{last_crawl}" — версия среза для дедупликации
    last_crawl: datetime
    rows: dict[str, Product]  # sku -> позиция по последнему срезу


class PublicationReader:
    """Читатель публикации проекта (catalog-v2) с внедряемым HTTP.

    Правило выбора стороны — то же, что в задаче 3 (catalog-source.ts):
    local с last_crawl в манифесте побеждает, иначе cloud. Так домашний
    слушатель видит товар магазина, обойдённого только в облаке, при этом
    цели владельца никуда не передаются — читаются только опубликованные
    индексы. HTTP_GET(url) возвращает bytes (None — 404) или бросает
    httpx.HTTPError; в тестах подменяется fake-функцией.
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        http_get: Callable[[str], bytes | None] | None = None,
        attempts: int = HTTP_ATTEMPTS,
        retry_delay: float = RETRY_DELAY_S,
        timeout: float = HTTP_TIMEOUT_S,
        max_bytes: int = MAX_RESPONSE_BYTES,
    ) -> None:
        self._base = (base_url or panel_url()).rstrip("/") + "/"
        self._http_get = http_get or self._default_get
        self._attempts = max(1, attempts)
        self._retry_delay = retry_delay
        self._timeout = timeout
        self._max_bytes = max_bytes
        self._sources: dict[str, tuple[str, dict]] | None = None

    # ---------- HTTP ----------

    def _default_get(self, url: str) -> bytes | None:
        resp = httpx.get(url, timeout=self._timeout, follow_redirects=True)
        if resp.status_code == HTTPStatus.NOT_FOUND:
            return None
        resp.raise_for_status()
        return resp.content

    def _fetch(self, url: str) -> bytes | None:
        """GET с тайм-аутом, ограничением размера и повтором с задержкой."""
        last_exc: Exception | None = None
        for attempt in range(1, self._attempts + 1):
            try:
                body = self._http_get(url)
            except httpx.HTTPError as exc:
                last_exc = exc
            else:
                if body is not None and len(body) > self._max_bytes:
                    raise ValueError(f"ответ больше {self._max_bytes} байт: {url}")
                return body
            if attempt < self._attempts:
                time.sleep(self._retry_delay)
        assert last_exc is not None
        raise last_exc

    # ---------- Источники ----------

    def refresh(self) -> dict[str, tuple[str, dict]]:
        """Перечитывает манифесты обеих сторон (один раз за обслуживающий тик)."""
        self._sources = None
        return self.sources()

    def sources(self) -> dict[str, tuple[str, dict]]:
        """Магазин -> (сторона, запись манифеста); только магазины с last_crawl."""
        if self._sources is not None:
            return self._sources
        cloud = self._manifest("data/catalog-v2/manifest.json")
        local = self._manifest("data/local/catalog-v2/manifest.json")
        out: dict[str, tuple[str, dict]] = {}
        for shop, entry in (local or {}).items():
            if entry.get("last_crawl"):
                out[shop] = ("local", entry)  # local с last_crawl побеждает
        for shop, entry in (cloud or {}).items():
            if shop not in out and entry.get("last_crawl"):
                out[shop] = ("cloud", entry)
        self._sources = out
        return out

    def _manifest(self, path: str) -> dict[str, dict] | None:
        """shops из манифеста; None — файла нет, схема не та или ошибка сети."""
        try:
            body = self._fetch(self._base + path)
            if body is None:
                return None
            data = json.loads(body.decode("utf-8"))
        except (httpx.HTTPError, ValueError, UnicodeDecodeError) as exc:
            log.warning("%s: %s", path, type(exc).__name__)
            return None
        if not isinstance(data, dict) or data.get("schema") != SCHEMA_VERSION:
            return None
        shops = data.get("shops")
        return shops if isinstance(shops, dict) else None

    # ---------- Наблюдения ----------

    def observation(self, shop: str) -> ItemObservation | None:
        """Срез магазина по выбранной стороне; None — источника/данных нет.

        Хеш index.json проверяется по манифесту (как на панели), schema и
        shop — по содержимому; любое расхождение считается отсутствием
        измерения, а не подорожанием.
        """
        src = self.sources().get(shop)
        if src is None:
            return None
        side, entry = src
        prefix = "local/" if side == "local" else ""
        body = self._fetch(f"{self._base}data/{prefix}catalog-v2/{shop}/index.json")
        if body is None:
            return None
        if hashlib.sha256(body).hexdigest() != entry.get("index_sha256"):
            log.warning("index.json магазина %s не совпал с манифестом", shop)
            return None
        try:
            data = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None
        if not isinstance(data, dict) or data.get("schema") != SCHEMA_VERSION:
            return None
        if data.get("shop") != shop:
            return None
        rows: dict[str, Product] = {}
        for row in data.get("rows") or []:
            if not isinstance(row, dict):
                continue
            product = row.get("product") or {}
            sku = product.get("sku")
            price = product.get("price")
            if not isinstance(sku, str) or not sku or not isinstance(price, int):
                continue  # цена неизвестна — измерения по позиции нет
            rows[sku] = Product(
                shop=shop,
                sku=sku,
                title=str(product.get("title") or ""),
                price=price,
                url=str(product.get("url") or ""),
                in_stock=bool(product.get("in_stock")),
            )
        try:
            last_crawl = datetime.fromisoformat(str(entry["last_crawl"]).replace("Z", "+00:00"))
        except ValueError:
            return None
        if last_crawl.tzinfo is None:
            last_crawl = last_crawl.replace(tzinfo=UTC)
        return ItemObservation(shop, side, f"{side}:{entry['last_crawl']}", last_crawl, rows)

    def lookup(self, shop: str, sku: str) -> Product | None:
        """Адаптер ItemLookup (задача 8): товар из индекса выбранной стороны."""
        try:
            obs = self.observation(shop)
        except (httpx.HTTPError, ValueError, OSError) as exc:
            log.warning("lookup %s/%s: %s", shop, sku, type(exc).__name__)
            return None
        return obs.rows.get(sku) if obs else None


def poll_item_watches(conn, reader: PublicationReader, *, clock=None) -> int:
    """Синхронизирует состояние целей со свежими срезами; создаёт события.

    Для каждой цели — последняя обработанная версия и условие прошлого
    измерения. Первый свежий price <= target создаёт одно событие; повтор
    той же версии и последующие цены ниже порога не дублируют; новое
    достоверное значение выше порога снова разрешает оповещение. Переход
    «отсутствие → наличие» при цене ниже цели — событие restock. Ошибка
    HTTP, неизвестная цена, устаревшая версия (старше STALE_AFTER — тот же
    порог, что на панели) и отсутствие магазина измерением не считаются.
    Возвращает число созданных событий.
    """
    watches = list_item_watches(conn)
    if not watches:
        return 0
    moment = (clock or now)()
    try:
        reader.refresh()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("манифесты: %s", type(exc).__name__)
        return 0
    created = 0
    by_shop: dict[str, list] = {}
    for watch in watches:
        by_shop.setdefault(watch.shop, []).append(watch)
    for shop, group in by_shop.items():
        try:
            obs = reader.observation(shop)
        except (httpx.HTTPError, ValueError, OSError) as exc:
            # Ошибка HTTP — не измерение: состояние цели не меняется.
            log.warning("срез %s: %s", shop, type(exc).__name__)
            continue
        if obs is None or moment - obs.last_crawl > STALE_AFTER:
            continue  # магазина нет или срез устарел — тоже не измерение
        for watch in group:
            product = obs.rows.get(watch.sku)
            if product is None:
                continue  # неизвестная цена — измерения нет
            state = get_item_watch_state(conn, watch.shop, watch.sku)
            if state is not None and state.version == obs.version:
                continue  # версия уже обработана
            below = bool(product.in_stock) and product.price <= watch.max_price
            was_below = bool(state.last_below) if state else False
            if below and not was_below:
                kind = (
                    EVENT_RESTOCK
                    if state is not None and state.last_in_stock is False
                    else EVENT_PRICE
                )
                if record_item_watch_event(
                    conn, watch.id, obs.version, kind, product.price,
                    title=product.title, url=product.url, at=moment,
                ):
                    created += 1
            set_item_watch_state(
                conn, watch.shop, watch.sku, obs.version, below, product.in_stock
            )
    return created


def format_item_watch_event(watch: ItemWatch, event: ItemWatchEvent) -> str:
    """Текст личного уведомления: цель достигнута или возврат товара."""
    label = SHOP_LABELS.get(watch.shop, watch.shop)
    title = escape(event.title or watch.sku)
    link = (
        f'<a href="{escape(event.url, quote=True)}">{title}</a>'
        if event.url
        else title
    )
    head = (
        "🎯 <b>Цель достигнута</b>"
        if event.kind == EVENT_PRICE
        else "🔁 <b>Снова в наличии</b>"
    )
    return (
        f"{head}\n"
        f"[{escape(label)}] {link}\n"
        f"Артикул: <code>{escape(watch.sku)}</code>\n"
        f"Цена: <b>{tenge(event.price)}</b> — цель до {tenge(watch.max_price)}"
    )


def deliver_item_watch_events(conn, api, chat_id, *, clock=None) -> int:
    """Отправляет ожидающие события; подтверждает доставку после ответа API.

    Сбой отправки оставляет событие ожидающим — повтор в следующем тике
    (задержку задаёт интервал цикла). ВНИМАНИЕ: если Telegram фактически
    доставил сообщение, а ответ не дожил до клиента (неопределённый
    тайм-аут), подтверждение не будет записано и возможен повтор сообщения.
    Это принятая особенность at-least-once доставки, задокументированная
    здесь; обхода в коде нет.
    """
    moment = (clock or now)()
    sent = 0
    for event in pending_item_watch_events(conn):
        watch = get_item_watch(conn, event.watch_id)
        if watch is None:
            delete_item_watch_events(conn, event.watch_id)  # цель удалена
            continue
        try:
            response = api.call(
                "sendMessage",
                chat_id=chat_id,
                text=format_item_watch_event(watch, event),
                parse_mode="HTML",
            )
        except httpx.HTTPError as exc:
            log.warning("доставка цели %s: %s", watch.id, type(exc).__name__)
            continue
        if not (response or {}).get("ok", True):
            continue
        mark_item_watch_events_delivered(
            conn, [(event.watch_id, event.version, event.kind)], at=moment
        )
        sent += 1
    return sent


def maintenance_tick(db_path, reader: PublicationReader, api, chat_id, *, clock=None) -> int:
    """Обслуживающий цикл точных целей с собственной SQLite connection.

    Загрузка индексов и сетевые тайм-ауты живут только здесь — ответы
    /groups и остальные команды слушателя открывают короткие соединения и
    сетевого тайм-аута не ждут. Возвращает число доставленных сообщений.
    """
    with connect(db_path) as conn:
        poll_item_watches(conn, reader, clock=clock)
        return deliver_item_watch_events(conn, api, chat_id, clock=clock)
