"""Оценка: сигналы только по собственной истории цен.

Магазинная «скидка» (зачёркнутая цена, бейдж «−71%») сигналом не является:
магазины рисуют её от завышенной цены — та же ловушка, что у Technodom с
видеокартами (handoff §5). Основание — только наша история.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from .config import Rules, Thresholds
from .models import Product
from .storage import Span, history, last_alert, last_span, now


class Signal(str, Enum):
    DROP = "упало"
    LOW = "минимум"
    TARGET = "цель"
    RESTOCK = "в наличии"


@dataclass(frozen=True)
class SignalHit:
    signal: Signal
    base: int | None = None     # база сравнения: медиана (DROP) или прошлый минимум (LOW)
    days: float | None = None   # глубина истории, на которой держится сигнал
    target: int | None = None   # целевая цена (TARGET, RESTOCK)


@dataclass
class Verdict:
    product: Product
    signals: list[SignalHit] = field(default_factory=list)
    reference: int | None = None  # медиана за окно тренда

    def hit(self, signal: Signal) -> SignalHit | None:
        return next((item for item in self.signals if item.signal is signal), None)

    def has(self, signal: Signal) -> bool:
        return self.hit(signal) is not None

    @property
    def drop_pct(self) -> float | None:
        base = next((item.base for item in self.signals if item.base), None) or self.reference
        if not base:
            return None
        return (base - self.product.price) / base * 100


# Вес точечного наблюдения: отрезок из одного обхода имеет нулевую длину,
# а весить должен как интервал между обходами.
_POINT_WEIGHT = timedelta(hours=2)


def weighted_median(spans: list[Span], since: datetime, until: datetime) -> int | None:
    """Медиана цены, взвешенная по времени, которое цена продержалась в окне.

    История хранится отрезками; простая медиана по строкам дала бы цене,
    державшейся неделю, тот же вес, что и двухчасовой распродаже.
    """
    weighted: list[tuple[int, float]] = []
    for span in spans:
        if not span.in_stock:
            continue
        start, end = max(span.first_seen, since), min(span.last_seen, until)
        if end < start:
            continue
        weighted.append((span.price, (end - start + _POINT_WEIGHT).total_seconds()))
    if not weighted:
        return None
    weighted.sort()
    half = sum(weight for _, weight in weighted) / 2
    accumulated = 0.0
    for price, weight in weighted:
        accumulated += weight
        if accumulated >= half:
            return price
    return weighted[-1][0]


def coverage_days(spans: list[Span], until: datetime) -> float:
    """Сколько дней назад позиция впервые наблюдалась в наличии (в пределах выборки)."""
    starts = [span.first_seen for span in spans if span.in_stock]
    if not starts:
        return 0.0
    return (until - min(starts)).total_seconds() / 86_400


def evaluate(
    conn: sqlite3.Connection,
    product: Product,
    rules: Rules,
    thresholds: Thresholds,
    at: datetime | None = None,
) -> Verdict:
    """Оценивает позицию против её истории. Вызывать ДО записи наблюдения."""
    at = at or now()
    verdict = Verdict(product)
    # Отсутствующие позиции пишутся в базу, но не будят: «товара на самом деле
    # нет» — не находка.
    if not product.in_stock:
        return verdict
    price = product.price

    # «Упало»: ниже медианы окна тренда. Медиана, а не минимум: рынок может
    # подорожать навсегда, и прошлый минимум заглушил бы сигнал.
    trend_since = at - timedelta(days=thresholds.trend_window_days)
    trend = [span for span in history(conn, product.identity, trend_since) if span.in_stock]
    reference = weighted_median(trend, trend_since, at)
    verdict.reference = reference
    trend_days = coverage_days(trend, at)
    drop_pct = rules.drop_pct_for(product.category, thresholds.drop_pct)
    if (
        reference
        and trend_days >= thresholds.min_history_days
        and reference - price >= thresholds.min_drop_tenge
        and (reference - price) / reference * 100 >= drop_pct
    ):
        verdict.signals.append(SignalHit(Signal.DROP, base=reference, days=trend_days))

    # «Минимум за 30 дней»: ниже всего, что видели за окно, с запасом.
    low_since = at - timedelta(days=thresholds.low_window_days)
    low = [span for span in history(conn, product.identity, low_since) if span.in_stock]
    low_days = coverage_days(low, at)
    if low and low_days >= thresholds.min_low_history_days:
        floor = min(span.price for span in low)
        if (
            price <= floor * (1 - thresholds.low_margin_pct / 100)
            and floor - price >= thresholds.min_drop_tenge
        ):
            verdict.signals.append(SignalHit(Signal.LOW, base=floor, days=low_days))

    # «Цель»: владелец назвал сумму — медианы ни при чём, надо брать.
    reached = [target for target in rules.targets_for(product) if price <= target]
    if reached:
        verdict.signals.append(SignalHit(Signal.TARGET, target=min(reached)))
        # «Появился в наличии» — только для позиций с целью: ресток любого из
        # 16 тыс. товаров засыпал бы чат.
        previous = last_span(conn, product.identity)
        if previous is not None and not previous.in_stock:
            verdict.signals.append(SignalHit(Signal.RESTOCK, target=min(reached)))
    return verdict


def should_send(
    conn: sqlite3.Connection, verdict: Verdict, thresholds: Thresholds, at: datetime | None = None
) -> bool:
    """Повтор по позиции — только при новом снижении (или возврате в наличие)."""
    if not verdict.signals:
        return False
    if verdict.has(Signal.RESTOCK):
        return True
    since = (at or now()) - timedelta(days=thresholds.trend_window_days)
    previous = last_alert(conn, verdict.product.identity, since)
    return previous is None or verdict.product.price < previous
