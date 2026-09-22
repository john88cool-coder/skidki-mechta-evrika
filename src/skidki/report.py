"""Форматирование сообщений Telegram (HTML).

Одна сводка на обход (решение владельца 2026-09-14 — вместо отдельных
карточек): находки по группам, у каждой — процент, цена со старой ценой и
ссылка на товар. Группы включаются и выключаются кнопками (/groups, слушатель
skidki bot). Все названия и ссылки — через html.escape (урок gpu-deals).
"""

from __future__ import annotations

import html
from datetime import datetime

from .config import GROUPS, OTHER_GROUP, OTHER_LABEL
from .evaluate import Signal, Verdict

SHOP_LABELS = {
    "mechta": "Мечта",
    "evrika": "Эврика",
    "shopkz": "Shop.kz",
    "sulpak": "Сулпак",
    "technodom": "Технодом",
    "alser": "Алсер",
}

# Понятные формулировки пометок наличия: «на витрине» читалось как ошибка.
STOCK_NOTES = {"на витрине": "витринный образец"}

# Разница с медианой истории меньше 3% — цена по сути не двигалась.
FLAT_TOLERANCE = 0.03

Buttons = list[list[tuple[str, str]]]

# Кнопка под сводкой: callback «groups» обрабатывает слушатель (skidki bot).
DIGEST_BUTTONS: Buttons = [[("⚙️ Группы уведомлений", "groups")]]
# В облаке (GitHub Actions) группы не действуют: выключение пишется в базу
# ноутбука, облачная база о нём не знает. Там под сводкой — ссылка на панель.
DASHBOARD_URL = "https://john88cool-coder.github.io/skidki-mechta-evrika/"
CLOUD_BUTTONS: Buttons = [[("📊 Все скидки на панели", DASHBOARD_URL)]]


def digest_buttons() -> Buttons:
    import os

    return CLOUD_BUTTONS if os.environ.get("GITHUB_ACTIONS") else DIGEST_BUTTONS


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


def short_title(title: str, limit: int = 70) -> str:
    return title if len(title) <= limit else title[: limit - 1].rstrip() + "…"


def _rank_key(verdict: Verdict) -> tuple[bool, float]:
    # Цели владельца — первыми, дальше по глубине падения.
    return (not verdict.has(Signal.TARGET), -(verdict.drop_pct or 0.0))


def rank(verdicts: list[Verdict], limit: int) -> tuple[list[Verdict], int]:
    """Что показать в этой сводке и сколько осталось на следующие."""
    ordered = sorted(verdicts, key=_rank_key)
    return ordered[:limit], max(len(ordered) - limit, 0)


def group_label(key: str | None) -> str:
    return GROUPS.get(key or "", OTHER_LABEL)


def _group_key(verdict: Verdict) -> str:
    key = verdict.product.group
    return key if key in GROUPS else OTHER_GROUP


def _headline(verdict: Verdict) -> str:
    price = verdict.product.price
    target = verdict.hit(Signal.TARGET)
    deal = verdict.hit(Signal.DEAL)
    drop = verdict.hit(Signal.DROP)
    low = verdict.hit(Signal.LOW)
    if target and target.target:
        return f"🎯 <b>цель ≤ {tenge(target.target)}</b>"
    if deal and deal.base:
        return f"🏷 <b>−{_pct(deal.base, price)}%</b>"
    if drop and drop.base:
        return f"📉 <b>−{_pct(drop.base, price)}%</b>"
    if low and low.base:
        return f"📉 <b>−{_pct(low.base, price)}%</b>"
    return "🔔"


def format_line(verdict: Verdict) -> str:
    """Две строки на находку: процент и товар со ссылкой — цена и магазин."""
    product = verdict.product
    title = html.escape(short_title(product.title))
    url = html.escape(product.url, quote=True)
    first = f'{_headline(verdict)} <a href="{url}">{title}</a>'

    parts = [f"<b>{tenge(product.price)}</b>"]
    if product.old_price and product.old_price > product.price:
        parts.append(f"<s>{tenge(product.old_price)}</s>")
    drop = verdict.hit(Signal.DROP)
    deal = verdict.hit(Signal.DEAL)
    if drop and drop.base:
        parts.append(f"обычно {tenge(drop.base)}")
    elif deal and deal.reference:
        # Скидка магазина против собственной истории: двигалась ли цена на деле.
        gap = deal.reference - product.price
        if gap >= product.price * FLAT_TOLERANCE:
            parts.append(f"обычно {tenge(deal.reference)}")
        elif -gap >= product.price * FLAT_TOLERANCE:
            parts.append(f"⚠️ обычно дешевле: {tenge(deal.reference)}")
        else:
            parts.append("⚠️ цена не менялась")
    low = verdict.hit(Signal.LOW)
    if low and low.base and not drop:
        parts.append(f"мин. за 30 дн. был {tenge(low.base)}")
    if verdict.has(Signal.RESTOCK):
        parts.append("снова в наличии")
    parts.append(SHOP_LABELS.get(product.shop, product.shop))
    if product.stock_note:
        note = STOCK_NOTES.get(product.stock_note.casefold(), product.stock_note)
        # Без ⚠️: значок — только у пометки о цене, иначе строка пестрит.
        parts.append(html.escape(note))
    return f"{first}\n└ {' · '.join(parts)}"


def format_more(rest: int) -> str:
    return (
        f"ℹ️ И ещё {rest} {_plural(rest, 'находка', 'находки', 'находок')} — "
        "покажу в следующей сводке."
    )


def format_digest(verdicts: list[Verdict], rest: int = 0, title: str = "🔥 Новые скидки") -> str:
    """Сводка обхода: находки по группам в постоянном порядке, внутри — по глубине.

    Каждая строка самодостаточна (теги открываются и закрываются в ней же):
    длинную сводку notify режет по строкам, не ломая разметку.
    """
    lines = [f"<b>{title}: {len(verdicts) + rest}</b>"]
    by_group: dict[str, list[Verdict]] = {}
    for verdict in sorted(verdicts, key=_rank_key):
        by_group.setdefault(_group_key(verdict), []).append(verdict)
    for key in [*GROUPS, OTHER_GROUP]:
        items = by_group.get(key)
        if not items:
            continue
        lines += ["", f"<b>{group_label(key)}</b> · {len(items)}"]
        lines += [format_line(verdict) for verdict in items]
    if rest:
        lines += ["", format_more(rest)]
    return "\n".join(lines)


def format_groups_menu(muted: set[str]) -> tuple[str, Buttons]:
    """Меню групп: кнопка на группу, ✅ — присылать, 🔕 — не присылать."""
    off = [label for key, label in GROUPS.items() if key in muted]
    lines = [
        "⚙️ <b>Группы уведомлений</b>",
        "Нажмите на группу, чтобы включить или выключить её в сводках.",
        "Выключены: " + ", ".join(off) if off else "Сейчас включены все группы.",
    ]
    buttons = [
        [(f"{'🔕' if key in muted else '✅'} {label}", f"toggle:{key}")]
        for key, label in GROUPS.items()
    ]
    return "\n".join(lines), buttons


def format_status(
    crawls: list[tuple[str, datetime | None, int | None]], queued: int, muted: set[str]
) -> str:
    lines = ["📊 <b>Состояние</b>"]
    for shop, when, count in crawls:
        name = SHOP_LABELS.get(shop, shop)
        if when is None:
            lines.append(f"• {name}: на этом ПК не обходится — состояние на веб-панели")
        else:
            items = f"{count or 0:,}".replace(",", " ")
            lines.append(f"• {name}: последний обход {when.astimezone():%d.%m %H:%M}, {items} позиций")
    lines.append(f"• В очереди: {queued}")
    if muted:
        lines.append("• Выключены: " + ", ".join(group_label(key) for key in sorted(muted)))
    return "\n".join(lines)


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
    lines.append("Тишина в Telegram сейчас не значит «скидок нет». Проверьте ПК и задачу skidki-crawl.")
    return "\n".join(lines)
