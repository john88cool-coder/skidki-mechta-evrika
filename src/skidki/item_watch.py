"""Формат точной ценовой цели из карточки товара (задача 8) — общий с фронтендом.

Веб-карточка строит `w2_<base64url(UTF8(JSON.stringify([shop, sku, maxPrice])))>`
без padding (`web/src/lib/utils/watch-link.ts`); бот разбирает тот же формат.
В payload входят только публичные данные — магазин, точный SKU и целевая цена:
ни title, ни chat_id, ни токен бота в ссылку не попадают.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from typing import Protocol

from .models import Product

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
