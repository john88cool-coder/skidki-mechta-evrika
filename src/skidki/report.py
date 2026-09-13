"""Форматирование сообщений Telegram (HTML).

Одна находка — одна карточка: заголовок с процентом, название, цена со
старой ценой и экономией, основание сигнала, категория, кнопка на товар.
Владелец читает с телефона: карточка не длиннее 10 строк. Все названия и
ссылки — через html.escape (урок gpu-deals).
"""

from __future__ import annotations

import html

from .evaluate import Signal, Verdict

SHOP_LABELS = {"mechta": "Мечта", "evrika": "Эврика"}
SHOP_BUTTONS = {"mechta": "🛒 Открыть в Мечте", "evrika": "🛒 Открыть в Эврике"}

Buttons = list[list[tuple[str, str]]]


def tenge(value: int) -> str:
    return f"{value:,}".replace(",", " ") + " ₸"


def _plural(count: int, one: str, few: str, many: str) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return one
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return few
    return many


def _pct(base: int, price: int) -> int:
    return round((base - price) / base * 100)


def short_title(title: str, limit: int = 120) -> str:
    return title if len(title) <= limit else title[: limit - 1].rstrip() + "…"


def _rank_key(verdict: Verdict) -> tuple[bool, float]:
    # Цели владельца — первыми, дальше по глубине падения.
    return (not verdict.has(Signal.TARGET), -(verdict.drop_pct or 0.0))


def rank(verdicts: list[Verdict], limit: int) -> tuple[list[Verdict], int]:
    """Что показать в этом обходе и сколько осталось на следующие."""
    ordered = sorted(verdicts, key=_rank_key)
    return ordered[:limit], max(len(ordered) - limit, 0)


def _headline(verdict: Verdict) -> str:
    product = verdict.product
    target = verdict.hit(Signal.TARGET)
    deal = verdict.hit(Signal.DEAL)
    drop = verdict.hit(Signal.DROP)
    low = verdict.hit(Signal.LOW)
    if target and target.target:
        head = f"🎯 <b>Цель достигнута: ≤ {tenge(target.target)}</b>"
    elif deal and deal.base:
        head = f"🏷 <b>Скидка −{_pct(deal.base, product.price)}%</b>"
    elif drop and drop.base:
        head = f"📉 <b>Цена упала на {_pct(drop.base, product.price)}%</b>"
    elif low and low.base:
        head = f"📉 <b>Минимум за 30 дней: −{_pct(low.base, product.price)}%</b>"
    else:
        head = "🔔 <b>Находка</b>"
    return f"{head} · {SHOP_LABELS.get(product.shop, product.shop)}"


def format_card(verdict: Verdict) -> tuple[str, Buttons]:
    """Карточка находки и кнопка со ссылкой на товар."""
    product = verdict.product
    lines = [_headline(verdict), "", f"<b>{html.escape(short_title(product.title))}</b>"]

    price = f"💰 <b>{tenge(product.price)}</b>"
    if product.old_price and product.old_price > product.price:
        price += f"  <s>{tenge(product.old_price)}</s>  −{tenge(product.old_price - product.price)}"
    lines.append(price)

    drop = verdict.hit(Signal.DROP)
    if drop and drop.base:
        # Честная глубина: медиана считается по тому, что уже накоплено (≤ 14 дней).
        days = max(1, min(round(drop.days or 14), 14))
        lines.append(
            f"📊 Обычно {tenge(drop.base)} (медиана за {days} дн) → −{_pct(drop.base, product.price)}%"
        )
    low = verdict.hit(Signal.LOW)
    if low and low.base:
        lines.append(
            f"📉 Ниже минимума за 30 дней ({tenge(low.base)}) на {_pct(low.base, product.price)}%"
        )
    if verdict.has(Signal.RESTOCK):
        lines.append("✅ Снова в наличии")

    meta = " · ".join(part for part in (product.category, product.brand) if part)
    if meta:
        lines.append(f"📂 {html.escape(meta)}")
    if product.stock_note:
        lines.append(f"⚠️ {html.escape(product.stock_note.capitalize())}")

    label = SHOP_BUTTONS.get(product.shop, "🛒 Открыть товар")
    return "\n".join(lines), [[(label, product.url)]]


def format_more(rest: int) -> str:
    return (
        f"ℹ️ И ещё {rest} {_plural(rest, 'находка', 'находки', 'находок')} — "
        "покажу следующими обходами."
    )


def format_breakage(shop: str, count: int, previous: int | None, error: str | None) -> str:
    name = SHOP_LABELS.get(shop, shop)
    if error:
        reason = f"ошибка: {html.escape(error[:200])}"
    elif previous:
        reason = f"{count} позиций вместо обычных {previous}"
    else:
        reason = f"{count} позиций"
    return (
        f"⚠️ <b>{name}</b>: обход сломался — {reason}.\n"
        "Мог измениться сайт или защита; пока не починено, находок по магазину не будет."
    )


def format_watchdog(stale: list[tuple[str, float | None]], max_age_hours: float) -> str:
    lines = [f"🚨 <b>Нет свежих обходов</b> (порог {max_age_hours:g} ч)"]
    for shop, age in stale:
        name = SHOP_LABELS.get(shop, shop)
        when = "ни одного успешного обхода" if age is None else f"последний успешный {age:.0f} ч назад"
        lines.append(f"• {name}: {when}")
    lines.append("Тишина в Telegram сейчас не значит «скидок нет». Проверьте Actions → crawl.")
    return "\n".join(lines)
