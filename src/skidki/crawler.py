"""Цикл обхода: сбор обоих магазинов, оценка, одно сообщение на обход, тревоги."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path

from playwright.async_api import BrowserContext

from .browser import open_context
from .config import OTHER_GROUP, Rules, Settings, Thresholds, load_rules, settings as default_settings
from .evaluate import Signal, SignalHit, Verdict, evaluate, should_send
from .models import PartialCrawl, Product
from .notify import Notifier
from .parsers import REGISTRY
from .report import digest_buttons, format_breakage, format_digest, format_watchdog, rank
from .storage import (
    Queued,
    compact,
    connect,
    current_deals,
    dequeue,
    enqueue,
    last_crawl_ok,
    last_successful_crawl,
    mark_alerts_delivered,
    muted_groups,
    now,
    previous_item_count,
    prune,
    record_alert,
    record_crawl,
    save_products,
    take_queue,
)

log = logging.getLogger("skidki")

ShopResult = tuple[str, list[Product], str | None]


async def _fetch_shop(context: BrowserContext, name: str, config: Settings) -> ShopResult:
    started = time.monotonic()
    try:
        products = await REGISTRY[name].fetch(context, config)
    except PartialCrawl as exc:
        # Собранное пишется в историю, но обход — неуспешный: тревога о поломке.
        log.warning("%s: обход неполный (%d позиций) — %s", name, len(exc.products), exc)
        return name, exc.products, str(exc)[:300]
    except Exception as exc:  # noqa: BLE001 — один упавший магазин не должен ронять обход
        log.warning("%s: %s", name, exc)
        return name, [], f"{type(exc).__name__}: {exc}"[:300]
    log.info("%s: %d позиций за %.0f с", name, len(products), time.monotonic() - started)
    return name, products, None


async def collect(shops: Sequence[str], config: Settings) -> list[ShopResult]:
    async with open_context() as context:
        return list(await asyncio.gather(*(_fetch_shop(context, name, config) for name in shops)))


def process(
    conn: sqlite3.Connection,
    results: list[ShopResult],
    rules: Rules,
    thresholds: Thresholds,
    at: datetime | None = None,
) -> tuple[list[Verdict], list[str]]:
    """Оценка и запись одного обхода без сети: находки и тревоги о поломке."""
    at = at or now()
    findings: list[Verdict] = []
    breakages: list[str] = []
    for shop, products, error in results:
        ok = error is None and bool(products)
        previous = previous_item_count(conn, shop)
        if not ok:
            # Тревога — на переходе в поломку, а не каждые 2 часа, пока она длится.
            if last_crawl_ok(conn, shop) is not False:
                breakages.append(format_breakage(shop, len(products), previous, error))
        elif previous and len(products) < previous * thresholds.breakage_ratio:
            breakages.append(format_breakage(shop, len(products), previous, None))
        record_crawl(conn, shop, len(products), ok, error, at)

        # Оценка — ДО записи: история должна быть без текущего наблюдения.
        for product in products:
            # Первый успешный обход магазина — база: висящие скидки не новость.
            verdict = evaluate(conn, product, rules, thresholds, at, cold_start=previous is None)
            if should_send(conn, verdict, thresholds, at):
                findings.append(verdict)
        save_products(conn, products, at)
    return findings, breakages


def run_once(
    notifier: Notifier,
    shops: Sequence[str] | None = None,
    config: Settings | None = None,
    db_path: Path | None = None,
) -> int:
    """Полный обход. Возвращает число находок (показанных и нет)."""
    config = config or default_settings
    names = list(shops or REGISTRY)
    results = asyncio.run(collect(names, config))
    rules = load_rules()

    with connect(db_path) as conn:
        findings, breakages = process(conn, results, rules, config.thresholds)
        # Всё найденное — в очередь ДО отправки: база коммитится даже при
        # отказе Telegram, а находки сверх лимита доживают до следующих обходов.
        for verdict in findings:
            enqueue(conn, verdict.product.identity, verdict.product.price, _dump_signals(verdict))
        removed = prune(conn, config.thresholds.retention_days)
    freed = compact(db_path)
    log.info(
        "находок: %d, тревог: %d, удалено отрезков: %d, освобождено %d КБ",
        len(findings), len(breakages), removed, freed // 1024,
    )

    for message in breakages:
        notifier.send(message)
    confirms = getattr(notifier, "confirms_delivery", False)
    with connect(db_path) as conn:
        since = now() - timedelta(hours=config.thresholds.queue_hours)
        muted = muted_groups(conn)
        queued = [
            verdict
            for verdict in (_load_verdict(item) for item in take_queue(conn, since))
            # Выключенные группы ждут в очереди (до суток): включил — увидел.
            if (verdict.product.group or OTHER_GROUP) not in muted
        ]
        conn.commit()
        shown, rest = rank(queued, config.thresholds.max_alerts)
        log.info(
            "в очереди: %d, показано: %d, осталось: %d, выключены группы: %s",
            len(queued), len(shown), rest, ", ".join(sorted(muted)) or "—",
        )
        if shown:
            notifier.send(format_digest(shown, rest), digest_buttons())
            if confirms:
                # Сводка — одна отправка: доставлена — её находки сняты с
                # очереди; упала — все остаются до следующего обхода. Консоль
                # (dry-run) очередь не расходует.
                for verdict in shown:
                    identity = verdict.product.identity
                    record_alert(conn, identity, _primary(verdict).value, verdict.product.price)
                    dequeue(conn, identity)
                mark_alerts_delivered(conn, [verdict.product.identity for verdict in shown])
    return len(findings)


# Какой сигнал — главный в карточке (заголовок): тот и пишется в alerts.
_HEADLINE_ORDER = (Signal.TARGET, Signal.DEAL, Signal.DROP, Signal.LOW, Signal.RESTOCK)


def _primary(verdict: Verdict) -> Signal:
    return next(signal for signal in _HEADLINE_ORDER if verdict.has(signal))


def _dump_signals(verdict: Verdict) -> str:
    return json.dumps(
        [
            {
                "signal": hit.signal.value, "base": hit.base, "days": hit.days,
                "target": hit.target, "reference": hit.reference,
            }
            for hit in verdict.signals
        ],
        ensure_ascii=False,
    )


def _load_verdict(item: Queued) -> Verdict:
    hits = [
        SignalHit(
            Signal(raw["signal"]), raw.get("base"), raw.get("days"), raw.get("target"),
            raw.get("reference"),
        )
        for raw in json.loads(item.signals)
    ]
    return Verdict(item.product, hits)


def send_sample(
    notifier: Notifier,
    per_shop: int = 4,
    config: Settings | None = None,
    db_path: Path | None = None,
    shops: Sequence[str] | None = None,
) -> int:
    """Пример оформления: самые глубокие текущие скидки из базы — по магазину.

    Это не находки и дедупликацию не трогает: владелец смотрит, как выглядят
    карточки, не дожидаясь настоящих новых скидок.
    """
    config = config or default_settings
    thresholds = config.thresholds
    rules = load_rules()
    min_pct = rules.deal_pct if rules.deal_pct is not None else thresholds.deal_pct
    min_price = (
        rules.deal_min_price if rules.deal_min_price is not None else thresholds.deal_min_price
    )
    # Гибрид 2026-09-18: база ноутбука — только mechta, база Actions — всё,
    # кроме mechta; пример из облачной базы не должен показывать чужие скидки.
    with connect(db_path) as conn:
        products = [
            product
            for shop in shops or REGISTRY
            for product in current_deals(
                conn, min_pct, min_price, thresholds.deal_max_pct, per_shop, shop
            )
        ]
    if not products:
        notifier.send("🧪 В базе пока нет скидок для примера — дождитесь первого обхода.")
        return 0
    verdicts = [Verdict(product, [SignalHit(Signal.DEAL, base=product.old_price)]) for product in products]
    notifier.send(
        format_digest(verdicts, title="🧪 Пример сводки — самые глубокие скидки из базы, не находки"),
        digest_buttons(),
    )
    return len(products)


def send_watchdog(
    notifier: Notifier,
    max_age_hours: float,
    shops: Sequence[str] | None = None,
    db_path: Path | None = None,
) -> bool:
    """Тревога, если по какому-то магазину нет свежего успешного обхода.

    Тишина в Telegram неотличима от «скидок нет» — сторож будит сам.
    """
    current = now()
    stale: list[tuple[str, float | None]] = []
    with connect(db_path) as conn:
        for shop in shops or REGISTRY:
            last = last_successful_crawl(conn, shop)
            age = None if last is None else (current - last).total_seconds() / 3600
            if age is None or age >= max_age_hours:
                stale.append((shop, age))
    if not stale:
        return False
    notifier.send(format_watchdog(stale, max_age_hours))
    return True
