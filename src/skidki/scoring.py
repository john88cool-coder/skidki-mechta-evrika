"""Скоринг «лучшей покупки» — честная скидка + ценность.

См. docs/RANKING_2026.md. Считается при экспорте, в БД не пишется:
история и маркетплейсная медиана меняются, так что скоринг всегда свежий.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Product

# Бренды с повышенным доверием (эвристика по продажам KZ).
# Noname / OEM ниже — не штрафуем сильно, но и не бонусим.
TRUSTED_BRANDS: set[str] = {
    "samsung", "apple", "xiaomi", "lg", "sony", "bosch", "panasonic", "philips",
    "huawei", "honor", "realme", "oneplus", "lenovo", "asus", "hp", "acer",
    "dell", "msi", "canon", "nikon", "dyson", "tefal", "braun", "kitchenaid",
    "jbl", "bose", "sennheiser", "pioneer", "yamaha", "artel", "beko", "haier",
    "indesit", "atlant", "biryusa", "pozis",
}
TOP_BRANDS: set[str] = {
    "samsung", "apple", "xiaomi", "lg", "sony", "bosch", "dyson", "asus", "lenovo", "hp",
}


def _brand_trust(brand: str | None) -> float:
    if not brand:
        return 0.5
    b = brand.strip().casefold()
    if b in TOP_BRANDS:
        return 1.0
    if b in TRUSTED_BRANDS:
        return 0.8
    # короткие / цифровые / OEM-подобные
    if len(b) <= 2 or re.match(r"^[a-z0-9\-]{1,4}$", b):
        return 0.3
    return 0.5


def _availability_score(in_stock: bool, stock_note: str | None) -> float:
    if not in_stock:
        return 0.0
    if stock_note and stock_note.casefold() in {"на витрине", "осталось мало", "предзаказ"}:
        return 0.6
    return 1.0


def _freshness_score(age_hours: float | None) -> float:
    if age_hours is None:
        return 0.5
    if age_hours <= 6:
        return 1.0
    if age_hours <= 24:
        return 0.55
    return 0.2


def _norm_discount(pct: float | None) -> float:
    if pct is None or pct <= 0:
        return 0.0
    # 0%→0, 15%→0.35, 20%→0.55, 30%→0.82, 40%+→1.0
    x = min(pct, 45) / 45
    # smoothstep
    return x * x * (3 - 2 * x)


@dataclass(frozen=True)
class Score:
    """Результат скоринга одного товара."""

    fair_discount: float | None  # честная скидка %, None если не подтверждена историей
    inflated_gap: float | None  # shop_discount - fair_discount (п.п.), если оба есть
    value_score: int  # 0..100
    is_pick: bool
    badges: tuple[str, ...]  # Выбор ИС / Честная скидка / Топ-Бренд / Рисованная?


def score_product(
    product: Product,
    *,
    fair_discount: float | None,
    marketplace_median: int | None = None,
    rating: float | None = None,
    reviews_count: int | None = None,
    age_hours: float | None = None,
) -> Score:
    """Считает value_score + бейджи.

    fair_discount — честная скидка, уже посчитанная по истории ИС
    (и при наличии — с учётом маркетплейсной медианы). Если None — скидка
    не подтверждена историей (слишком мало наблюдений).
    """
    shop_pct = product.shop_discount_pct
    # честная скидка с учётом маркетплейса: если зачёркнутая сильно выше
    # рыночной медианы — режем fair_discount
    effective_fair = fair_discount
    if marketplace_median and product.old_price and marketplace_median > 0:
        # насколько зачёркнутая выше рынка
        market_pct = (product.old_price - marketplace_median) / product.old_price * 100
        if market_pct > 12:  # завышена >12% над рынком — подозрительно
            if effective_fair is not None:
                effective_fair = max(0.0, effective_fair - market_pct * 0.5)

    inflated_gap: float | None = None
    if shop_pct is not None and effective_fair is not None:
        inflated_gap = shop_pct - effective_fair

    # компоненты
    fair_norm = _norm_discount(effective_fair)
    brand = _brand_trust(product.brand)
    avail = _availability_score(product.in_stock, product.stock_note)
    fresh = _freshness_score(age_hours)

    # веса (0.55, 0.2, 0.15, 0.10)
    base = 0.55 * fair_norm + 0.20 * brand + 0.15 * avail + 0.10 * fresh
    # бонус за внешние оценки — мягкий, справочный
    bonus = 0.0
    if rating is not None and reviews_count is not None:
        if rating >= 4.5 and reviews_count >= 50:
            bonus = 0.05
        elif rating >= 4.2 and reviews_count >= 20:
            bonus = 0.02

    value = int(round(min(1.0, base + bonus) * 100))

    badges: list[str] = []
    is_pick = (
        value >= 78 and (effective_fair or 0) >= 18 and product.price >= 20_000 and product.in_stock
    )
    if is_pick:
        badges.append("Выбор ИС")
    if effective_fair is not None and effective_fair >= 15:
        badges.append("Честная скидка")
    if product.brand and product.brand.strip().casefold() in TOP_BRANDS:
        badges.append("Топ-Бренд")
    if inflated_gap is not None and inflated_gap >= 15:
        badges.append("Рисованная?")

    return Score(
        fair_discount=round(effective_fair, 1) if effective_fair is not None else None,
        inflated_gap=round(inflated_gap, 1) if inflated_gap is not None else None,
        value_score=value,
        is_pick=is_pick,
        badges=tuple(badges),
    )
