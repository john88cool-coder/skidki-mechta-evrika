"""Межмагазинное сопоставление моделей электроники и расчёт рыночной медианы.

Вместо недоступных без прокси маркетплейсов (Kaspi/WB/Ozon) ориентиром служит
собственный пул из 6 розничных сетей РК (`mechta`, `evrika`, `shopkz`, `sulpak`,
`technodom`, `alser`): если одна и та же модель найдена минимум в 2 магазинах,
медиана их минимальных цен в наличии даёт объективный рыночный ориентир.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from statistics import median

from .models import Product

# Samsung SM-S928BZKDSKZ / SM-A556E/DS -> базовый код модели SM-S928B / SM-A556E
_SAMSUNG_RE = re.compile(r"\b(SM-[A-Z]\d{3}[A-Z]?)[A-Z0-9/]*\b", re.I)
# Apple MPN вида MYNF3HX/A, MU793RU/A, MGN63 -> 5-символьная база MYNF3, MU793, MGN63
_APPLE_REGIONAL_RE = re.compile(r"\b([A-Z]{2}[A-Z0-9]{3})(?:[A-Z]{1,2}/A)\b")
# Общий заводской партномер с дефисом (G614JV-N4071, WH-1000XM5, OLED55C4RLA)
_GENERIC_MPN_RE = re.compile(r"\b([A-Z0-9]{2,8}-[A-Z0-9]{3,10})\b")

_IGNORE_MPN_PREFIXES = (
    "WI-FI",
    "WIFI",
    "USB-",
    "TYPE-C",
    "MICRO-",
    "MINI-",
    "HDMI-",
    "DDR4-",
    "DDR5-",
    "CORE-",
    "RYZEN-",
    "GEN-",
)
_SPEC_NOISE_RE = re.compile(
    r"^(?:\d+(?:GB|ГБ|TB|ТБ|MAH|МАЧ|HZ|ГЦ|W|ВТ|MM|ММ|MP|МП)|"
    r"\d+/\d+(?:GB|ГБ)?|WIFI\d*|BT\d*|IP\d{2}|DDR\d|4K|8K|5G|LTE)$",
    re.I,
)

_STORAGE_RE = re.compile(r"(?:\b\d{1,2}\s*/\s*)?(\d{2,4})\s*(GB|ГБ|TB|ТБ)\b", re.I)

_STOP_WORDS = frozenset(
    {
        "смартфон", "телефон", "сотовый", "мобильный", "ноутбук", "ультрабук",
        "планшет", "телевизор", "наушники", "беспроводные", "проводные", "гарнитура",
        "смарт", "часы", "умные", "пылесос", "робот", "вертикальный", "холодильник",
        "стиральная", "машина", "кофемашина", "микроволновая", "печь", "кондиционер",
        "монитор", "игровой", "игровая", "консоль", "приставка", "колонка", "портативная",
        "черный", "чёрный", "белый", "серый", "синий", "голубой", "зеленый", "зелёный",
        "красный", "розовый", "желтый", "жёлтый", "фиолетовый", "сиреневый", "бежевый",
        "серебристый", "серебро", "золотой", "золото", "графитовый", "графит",
        "титановый", "титан", "темно", "тёмно", "светло", "небесно",
        "black", "white", "gray", "grey", "silver", "gold", "blue", "green", "pink",
        "purple", "violet", "yellow", "red", "midnight", "starlight", "graphite",
        "titanium", "natural", "desert", "space", "cosmic", "awesome", "phantom",
        "cream", "lavender", "mint", "coral", "navy", "olive", "obsidian", "porcelain",
        "dual", "sim", "esim", "5g", "4g", "lte", "wifi", "wi", "fi", "nfc",
        "gb", "гб", "tb", "тб", "ram", "ssd", "hdd",
    }
)


def _clean_explicit_mpn(raw: str) -> str | None:
    cleaned = re.sub(r"[\s_]+", "-", raw.strip().upper())
    if len(cleaned) < 5:
        return None
    if not (any(ch.isalpha() for ch in cleaned) and any(ch.isdigit() for ch in cleaned)):
        return None
    if _SPEC_NOISE_RE.match(cleaned):
        return None
    m_sam = _SAMSUNG_RE.search(cleaned)
    if m_sam:
        return m_sam.group(1).upper()
    m_app = _APPLE_REGIONAL_RE.search(cleaned)
    if m_app:
        return m_app.group(1).upper()
    return cleaned


def extract_mpn(title: str, explicit_mpn: str | None = None) -> str | None:
    """Извлекает канонический заводской партномер из поля mpn или заголовка."""
    if explicit_mpn:
        explicit = _clean_explicit_mpn(explicit_mpn)
        if explicit:
            return explicit

    upper = title.upper()
    m_sam = _SAMSUNG_RE.search(upper)
    if m_sam:
        return m_sam.group(1).upper()

    m_app = _APPLE_REGIONAL_RE.search(upper)
    if m_app:
        return m_app.group(1).upper()

    for match in _GENERIC_MPN_RE.finditer(upper):
        candidate = match.group(1)
        if candidate.startswith(_IGNORE_MPN_PREFIXES):
            continue
        if _SPEC_NOISE_RE.match(candidate):
            continue
        if any(ch.isalpha() for ch in candidate) and any(ch.isdigit() for ch in candidate):
            return candidate
    return None


def _normalize_brand(brand: str | None, title: str) -> str | None:
    if brand and brand.strip():
        b = brand.strip().casefold()
        if b in ("redmi", "xiaomi"):
            return "xiaomi"
        return re.sub(r"[^a-z0-9а-яё]+", "", b) or None
    lowered = title.casefold()
    for known in ("apple", "samsung", "xiaomi", "huawei", "honor", "asus", "lenovo", "sony", "lg", "dyson"):
        if re.search(rf"\b{known}\b", lowered):
            return known
    return None


def _extract_storage_gb(title: str) -> int | None:
    matches = list(_STORAGE_RE.finditer(title))
    if not matches:
        return None
    # Берём наибольший объём (в записи 12/256GB или 16GB/512GB это накопитель, а не ОЗУ)
    values_gb: list[int] = []
    for m in matches:
        num = int(m.group(1))
        unit = m.group(2).upper()
        gb = num * 1024 if unit in ("TB", "ТБ") else num
        if gb >= 32:
            values_gb.append(gb)
    return max(values_gb) if values_gb else None


def model_key(product: Product) -> str | None:
    """Канонический ключ модели для группировки предложений разных магазинов."""
    brand = _normalize_brand(product.brand, product.title)
    if not brand:
        return None

    mpn = extract_mpn(product.title, product.mpn)
    if mpn:
        return f"{brand}:mpn:{mpn}"

    storage_gb = _extract_storage_gb(product.title)
    cleaned = re.sub(r"\b\d{1,2}\s*/\s*\d{2,4}\s*(?:GB|ГБ|TB|ТБ)\b", " ", product.title, flags=re.I)
    cleaned = _STORAGE_RE.sub(" ", cleaned)
    raw_tokens = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9+]+", cleaned.casefold())
    tokens = [
        tok
        for tok in raw_tokens
        if tok not in _STOP_WORDS
        and tok != brand
        and not _SPEC_NOISE_RE.match(tok)
    ]
    if len(tokens) < 2 or len(tokens) > 6:
        return None
    if not any(any(ch.isdigit() for ch in tok) for tok in tokens):
        return None
    sig = "-".join(tokens[:5])
    suffix = f":{storage_gb}gb" if storage_gb else ""
    return f"{brand}:sig:{sig}{suffix}"


def marketplace_medians(products: Iterable[Product]) -> dict[str, int]:
    """Возвращает `identity -> рыночная медиана` для моделей из >= 2 магазинов."""
    clusters: dict[str, list[Product]] = {}
    for product in products:
        if not product.in_stock or product.price <= 0:
            continue
        key = model_key(product)
        if key:
            clusters.setdefault(key, []).append(product)

    medians_by_identity: dict[str, int] = {}
    for group in clusters.values():
        best_per_shop: dict[str, int] = {}
        for p in group:
            prev = best_per_shop.get(p.shop)
            if prev is None or p.price < prev:
                best_per_shop[p.shop] = p.price
        if len(best_per_shop) < 2:
            continue
        med = int(round(median(best_per_shop.values())))
        for p in group:
            medians_by_identity[p.identity] = med
    return medians_by_identity
