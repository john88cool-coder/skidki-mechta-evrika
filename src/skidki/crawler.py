"""Цикл обхода: сбор обоих магазинов, оценка, одно сообщение на обход, тревоги."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from playwright.async_api import BrowserContext

from .browser import open_context
from .config import Rules, Settings, Thresholds, load_rules, settings as default_settings
from .evaluate import Verdict, evaluate, should_send
from .models import PartialCrawl, Product
from .notify import Notifier
from .parsers import REGISTRY
from .report import format_breakage, format_finds, format_watchdog
from .storage import (
    compact,
    connect,
    last_crawl_ok,
    last_successful_crawl,
    mark_alerts_delivered,
    now,
    previous_item_count,
    prune,
    record_alert,
    record_crawl,
    save_products,
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
        text, shown = (
            format_finds(findings, config.thresholds.max_alert_lines) if findings else ("", [])
        )
        # Находка фиксируется до отправки (delivered_at = NULL): база
        # коммитится даже при отказе Telegram, недоставленное уйдёт в следующий раз.
        for verdict in shown:
            record_alert(
                conn, verdict.product.identity, verdict.signals[0].signal.value,
                verdict.product.price,
            )
        removed = prune(conn, config.thresholds.retention_days)
    freed = compact(db_path)
    log.info(
        "находок: %d (показано %d), тревог: %d, удалено отрезков: %d, освобождено %d КБ",
        len(findings), len(shown), len(breakages), removed, freed // 1024,
    )

    for message in breakages:
        notifier.send(message)
    if shown:
        notifier.send(text)
        if getattr(notifier, "confirms_delivery", False):
            with connect(db_path) as conn:
                mark_alerts_delivered(conn, [verdict.product.identity for verdict in shown])
    return len(findings)


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
