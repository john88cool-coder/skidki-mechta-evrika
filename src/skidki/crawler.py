"""Цикл обхода: сбор обоих магазинов, оценка, одно сообщение на обход, тревоги."""

from __future__ import annotations

import asyncio
import httpx
import json
import logging
import re
import sqlite3
import time
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path

from playwright.async_api import BrowserContext

from .browser import open_browser, open_shop_context
from .config import OTHER_GROUP, Rules, Settings, Thresholds, load_rules, settings as default_settings
from .evaluate import Signal, SignalHit, Verdict, evaluate, should_send
from .models import PartialCrawl, Product
from .notify import Notifier
from .parsers import REGISTRY
from .report import digest_buttons, format_breakage, has_real_findings, format_digest, format_watchdog, rank
from .storage import (
    Queued,
    compact,
    connect,
    current_deals,
    dequeue,
    enqueue,
    histories_for_shop,
    import_prefs,
    last_alerts_for_shop,
    last_crawl_ok,
    last_spans_for_shop,
    last_successful_crawl,
    list_watches,
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


_BOT_TOKEN_RE = re.compile(r"bot\d+:[A-Za-z0-9_-]+")


def _redact_secrets(text: str) -> str:
    return _BOT_TOKEN_RE.sub("bot<REDACTED>", text)


async def _fetch_shop(
    context: BrowserContext | None, name: str, config: Settings | None
) -> ShopResult:
    cfg = config or default_settings
    started = time.monotonic()
    try:
        products = await asyncio.wait_for(
            REGISTRY[name].fetch(context, cfg),  # type: ignore[arg-type]
            timeout=cfg.shop_timeout_s,
        )
    except PartialCrawl as exc:
        msg = _redact_secrets(str(exc))[:300]
        # Собранное пишется в историю, но обход — неуспешный: тревога о поломке.
        log.warning("%s: обход неполный (%d позиций) — %s", name, len(exc.products), msg)
        return name, exc.products, msg
    except Exception as exc:  # noqa: BLE001 — один упавший магазин не должен ронять обход
        msg = _redact_secrets(f"{type(exc).__name__}: {exc}")[:300]
        log.warning("%s: %s", name, msg)
        return name, [], msg
    log.info("%s: %d позиций за %.0f с", name, len(products), time.monotonic() - started)
    return name, products, None


async def _fetch_isolated(
    browser: object, ua: str, name: str, config: Settings
) -> ShopResult:
    async with open_shop_context(browser, ua) as context:  # type: ignore[arg-type]
        return await _fetch_shop(context, name, config)


async def collect(shops: Sequence[str], config: Settings) -> list[ShopResult]:
    async with open_browser() as (browser, ua):
        return list(
            await asyncio.gather(*(_fetch_isolated(browser, ua, name, config) for name in shops))
        )


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
    history_window = max(thresholds.trend_window_days, thresholds.low_window_days)
    history_since = at - timedelta(days=history_window)
    alert_since = at - timedelta(days=thresholds.trend_window_days)
    # Подписки из БД (/watch) — цели наравне с правилами rules.toml.
    watches = list_watches(conn)

    for shop, products, error in results:
        ok = error is None and bool(products)
        previous = previous_item_count(conn, shop)
        if ok and previous and len(products) < previous * thresholds.breakage_ratio:
            ok = False
            error = f"подозрительно мало позиций: {len(products)} вместо {previous}"
        if not ok and last_crawl_ok(conn, shop) is not False:
            # Тревога — на переходе в поломку, а не каждые 2 часа, пока она длится.
            breakages.append(format_breakage(shop, len(products), previous, error))
        record_crawl(conn, shop, len(products), ok, error, at)

        if not products:
            continue

        spans_by_id = histories_for_shop(conn, shop, history_since)
        last_by_id = last_spans_for_shop(conn, shop)
        alerts_by_id = last_alerts_for_shop(conn, shop, alert_since)

        # Оценка — ДО записи: история должна быть без текущего наблюдения.
        for product in products:
            # Первый успешный обход магазина — база: висящие скидки не новость.
            verdict = evaluate(
                conn,
                product,
                rules,
                thresholds,
                at,
                cold_start=previous is None,
                preloaded_spans=spans_by_id.get(product.identity, []),
                preloaded_last_span=last_by_id.get(product.identity),
                extra_watches=watches,
            )
            if should_send(
                conn,
                verdict,
                thresholds,
                at,
                preloaded_last_alert=alerts_by_id.get(product.identity),
            ):
                findings.append(verdict)
        save_products(conn, products, at)
    return findings, breakages


def sync_remote_prefs(conn: sqlite3.Connection, prefs_url: str) -> bool:
    """Подтягивает muted + watches из опубликованного локального среза (gh-pages)."""
    try:
        response = httpx.get(prefs_url, timeout=10.0, follow_redirects=True)
        if response.status_code == 404:
            return False
        # raise_for_status в httpx>=0.28 бросает RuntimeError на ответе без
        # request (в тестах подставляют httpx.Response(200, json=...)), поэтому
        # ошибочный статус проверяем явно — поведение как у HTTPStatusError.
        if response.is_error:
            log.warning("prefs sync: HTTP %d", response.status_code)
            return False
        payload = response.json()
        if isinstance(payload, dict):
            import_prefs(conn, payload)
            return True
    except Exception as exc:  # noqa: BLE001 — сеть не должна срывать обход
        log.warning("prefs sync: %s", type(exc).__name__)
    return False


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
        if config.prefs_url:
            sync_remote_prefs(conn, config.prefs_url)
        findings, breakages = process(conn, results, rules, config.thresholds)
        # Всё найденное — в очередь ДО отправки: база коммитится даже при
        # отказе Telegram, а находки сверх лимита доживают до следующих обходов.
        for verdict in findings:
            enqueue(conn, verdict.product.identity, verdict.product.price, _dump_signals(verdict))
        removed = prune(conn, config.thresholds.retention_days)
    freed = compact(db_path) if removed > 0 else 0
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
            # Одни нарисованные «скидки» — не повод будить: снимаем их с очереди молча.
            if has_real_findings(shown):
                notifier.send(format_digest(shown, rest), digest_buttons())
            else:
                log.info("в сводке только нарисованные скидки (%d) — не отправляю", len(shown))
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
    *,
    remote_url: str | None = None,
    remote_shops: Sequence[str] | None = None,
) -> bool:
    """Тревога, если по какому-то магазину (в БД или в удалённом срезе) нет свежего обхода."""
    current = now()
    stale: list[tuple[str, float | None]] = []
    with connect(db_path) as conn:
        for shop in shops or REGISTRY:
            last = last_successful_crawl(conn, shop)
            age = None if last is None else (current - last).total_seconds() / 3600
            if age is None or age >= max_age_hours:
                stale.append((shop, age))

    if remote_url:
        targets = list(remote_shops or ("mechta",))
        remote_map: dict[str, str | None] = {}
        try:
            resp = httpx.get(remote_url, timeout=15.0, follow_redirects=True)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("shops") or []:
                    if isinstance(item, dict) and item.get("name"):
                        remote_map[str(item["name"])] = item.get("last_crawl")
        except Exception as exc:  # noqa: BLE001 — недоступность среза сама по себе повод проверить
            log.warning("watchdog remote: %s", type(exc).__name__)
        for shop in targets:
            raw_ts = remote_map.get(shop)
            age = None
            if raw_ts:
                try:
                    dt = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        from datetime import timezone
                        dt = dt.replace(tzinfo=timezone.utc)
                    age = (current - dt).total_seconds() / 3600
                except Exception as exc:  # noqa: BLE001 — мусор в срезе не должен валить сторожа
                    log.warning("watchdog remote: %s", type(exc).__name__)
                    age = None
            if age is None or age >= max_age_hours:
                stale.append((shop, age))

    if not stale:
        return False
    notifier.send(format_watchdog(stale, max_age_hours))
    return True
