"""Форматирование сообщений Telegram (HTML).

Владелец читает с телефона: сообщение не длиннее 10 строк. Все названия и
ссылки — через html.escape (урок gpu-deals).
"""

from __future__ import annotations

import html

from .evaluate import Signal, Verdict

SHOP_LABELS = {"mechta": "Мечта", "evrika": "Эврика"}


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


def short_title(title: str, limit: int = 60) -> str:
    return title if len(title) <= limit else title[: limit - 1].rstrip() + "…"


def _rank(verdict: Verdict) -> tuple[bool, float]:
    # Цели владельца — первыми, дальше по глубине падения.
    return (not verdict.has(Signal.TARGET), -(verdict.drop_pct or 0.0))


def format_line(verdict: Verdict) -> str:
    product = verdict.product
    details: list[str] = []
    drop = verdict.hit(Signal.DROP)
    low = verdict.hit(Signal.LOW)
    target = verdict.hit(Signal.TARGET)
    if drop and drop.base:
        details.append(f"−{_pct(drop.base, product.price)}% к медиане {tenge(drop.base)}")
    if low and low.base:
        details.append("мин. за 30 дн" if drop else f"мин. за 30 дн, было {tenge(low.base)}")
    deal = verdict.hit(Signal.DEAL)
    if deal and deal.base:
        details.append(f"скидка −{_pct(deal.base, product.price)}%, было {tenge(deal.base)}")
    if target and target.target:
        details.append(f"цель ≤ {tenge(target.target)}")
    if verdict.has(Signal.RESTOCK):
        details.append("снова в наличии")
    if product.stock_note:
        details.append(product.stock_note)
    title = html.escape(short_title(product.title))
    url = html.escape(product.url, quote=True)
    shop = SHOP_LABELS.get(product.shop, product.shop)
    return (
        f'• <b>{tenge(product.price)}</b> <a href="{url}">{title}</a>'
        f" — {'; '.join(details)} · {shop}"
    )


def format_finds(verdicts: list[Verdict], limit: int) -> tuple[str, list[Verdict]]:
    """Одно сообщение на обход: заголовок, до `limit` находок, хвост «ещё N».

    Возвращает текст и показанные находки — только они фиксируются как
    алерты; остальные будут оценены заново следующим обходом.
    """
    ordered = sorted(verdicts, key=_rank)
    shown = ordered[:limit]
    count = len(verdicts)
    lines = [f"🔥 <b>{count} {_plural(count, 'находка', 'находки', 'находок')}</b>"]
    lines += [format_line(verdict) for verdict in shown]
    rest = count - len(shown)
    if rest:
        lines.append(f"…и ещё {rest} — покажу следующими обходами")
    return "\n".join(lines), shown


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
