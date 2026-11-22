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
# Полный токен Samsung с вариантным хвостом и/или суффиксом /DS (для exact-ключа)
_SAMSUNG_TOKEN_RE = re.compile(r"\b(SM-[A-Z]\d{3}[A-Z0-9]*(?:/[A-Z0-9]{1,4})?)\b", re.I)
# Apple MPN вида MYNF3HX/A, MU793RU/A, MGN63 -> 5-символьная база MYNF3, MU793, MGN63
_APPLE_REGIONAL_RE = re.compile(r"\b([A-Z]{2}[A-Z0-9]{3})(?:[A-Z]{1,2}/A)\b")
# Полный Apple-артикул с региональным суффиксом (для exact-ключа)
_APPLE_TOKEN_RE = re.compile(r"\b([A-Z]{2}[A-Z0-9]{3}[A-Z]{1,2}/A)\b", re.I)
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

# Класс-токены железа и стандартов: описывают категорию/характеристику, а не
# конкретную модель производителя. Два разных ноутбука с одной видеокартой или
# два разных роутера одного WiFi-класса не должны получать один exact-ключ.
# GPU: RTX-3050/GTX-1650/RX-6600; WiFi-стандарты: AX-3000/AX1800/AC-1200.
_CLASS_TOKEN_RE = re.compile(
    r"^(?:(?:RTX|GTX|ARC|RX|GT)[\s-]?\d{3,4}[A-Z]{0,2}|"
    r"(?:AX|AC|ADSL|WIFI)[\s-]?\d{3,5})$",
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


def _title_article(brand: str, upper_title: str) -> str | None:
    """Полный артикул производителя, записанный в самом заголовке (поле mpn
    заполнено не у всех магазинов). Samsung и Apple — по своим схемам артикулов
    (с вариантным хвостом и региональным суффиксом), остальные — общий
    партномер с дефисом. Токены связи (WIFI6, DDR5-...) и объёмы памяти
    артикулом не считаются."""
    if brand == "samsung":
        m = _SAMSUNG_TOKEN_RE.search(upper_title)
        return m.group(1).upper() if m else None
    if brand == "apple":
        m = _APPLE_TOKEN_RE.search(upper_title)
        return m.group(1).upper() if m else None
    for match in _GENERIC_MPN_RE.finditer(upper_title):
        candidate = match.group(1)
        if candidate.startswith(_IGNORE_MPN_PREFIXES) or _SPEC_NOISE_RE.match(candidate):
            continue
        # Класс-токен (RTX-3050, AX-3000) — характеристика, а не артикул модели.
        if _CLASS_TOKEN_RE.match(candidate):
            continue
        if any(ch.isalpha() for ch in candidate) and any(ch.isdigit() for ch in candidate):
            return candidate
    return None


def _mpn_article(brand: str, mpn: str | None) -> str | None:
    """Полный артикул из поля mpn: безопасная нормировка регистра и пробелов,
    вариантные хвосты и региональные суффиксы сохраняются. Числовые SKU
    продавца, слова без цифр и класс-токены (RTX-3050, AX-3000) артикулом
    не считаются."""
    if not mpn:
        return None
    cleaned = re.sub(r"\s+", " ", mpn.strip()).upper()
    if len(cleaned) < 5:
        return None
    if not (any(ch.isalpha() for ch in cleaned) and any(ch.isdigit() for ch in cleaned)):
        return None
    if _SPEC_NOISE_RE.match(cleaned) or _CLASS_TOKEN_RE.match(cleaned):
        return None
    if brand == "samsung":
        m = _SAMSUNG_TOKEN_RE.fullmatch(cleaned)
        return m.group(1).upper() if m else None
    if brand == "apple":
        m = _APPLE_TOKEN_RE.fullmatch(cleaned)
        return m.group(1).upper() if m else None
    return cleaned


def _variant_pinned(brand: str, code: str) -> bool:
    """Артикул сам различает варианты семейства: полный код Samsung и Apple
    несёт хвост цвета/региона (SM-S928BZKDSKZ, MYNF3HX/A). Запись вида
    SM-S931B — общий код семейства, комплектацию он не задаёт."""
    if brand == "samsung":
        m = _SAMSUNG_RE.fullmatch(code)
        return bool(m) and m.group(1).upper() != code
    if brand == "apple":
        return _APPLE_TOKEN_RE.fullmatch(code) is not None and len(code) > 5
    return True


def _storage_signature(title: str) -> str:
    """Объём памяти в нормированной записи ('256gb', '1024gb') или '' — вариант
    комплектации для семейств с общим базовым кодом."""
    matches = [(int(m.group(1)), m.group(2).upper()) for m in _STORAGE_RE.finditer(title)]
    gb_values = [num * 1024 if unit in ("TB", "ТБ") else num for num, unit in matches]
    gb_values = [gb for gb in gb_values if gb >= 32]
    return f"{max(gb_values)}gb" if gb_values else ""


def exact_offer_key(product: Product) -> str | None:
    """Подтверждённый ключ «той же комплектации» для публичного блока офферов.

    Отличия от model_key (предварительная группировка): только подтверждённый
    полный артикул производителя и бренд; нормализация — безопасные регистр и
    пробелы; региональные суффиксы, знаки, память и комплектация сохраняются.
    Обычный SKU продавца модель не подтверждает. Заголовок и поле mpn должны
    называть одну модель (иначе конфликт — None). Для семейств с общим базовым
    кодом (SM-S931B у Samsung) требуется совпадение вариантов: объём памяти
    входит в ключ, а без него идентификатор неполон — None. Полный код с
    вариантным хвостом комплектацию задаёт сам.
    """
    brand = _normalize_brand(product.brand, product.title)
    if not brand:
        return None
    upper = re.sub(r"\s+", " ", product.title).upper()
    t_code = _title_article(brand, upper)
    m_code = _mpn_article(brand, product.mpn)
    if t_code and m_code:
        # Два подтверждения: они должны описывать одну модель (одно — усечённая
        # запись другого); расходятся варианты — характеристики конфликтуют.
        if not (t_code == m_code or t_code.startswith(m_code) or m_code.startswith(t_code)):
            return None
        code = t_code if len(t_code) >= len(m_code) else m_code
    else:
        code = t_code or m_code
    if not code:
        return None
    if _variant_pinned(brand, code):
        return f"{brand}:{code}"
    storage = _storage_signature(product.title)
    if not storage:
        return None  # семейство с общим артикулом без варианта — не подтверждено
    return f"{brand}:{code}/{storage}"
