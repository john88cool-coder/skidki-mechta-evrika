"""Каталог v2: весь наблюдаемый каталог и история цен по магазинам пакетами.

Витрина (latest.json) показывает только скидки; карточка товара Stage 2
должна открываться и без скидки, поэтому каждому магазину с успешным
обходом выпускаются стабильные файлы catalog-v2/<shop>/{index,history}.json,
а manifest.json связывает их SHA-256 и время последнего обхода. Файлы
магазинов завершаются первыми, манифест заменяется атомарно: читатель не
видит манифест, ссылающийся на недописанный ресурс. Пути стабильны, поэтому
публикация с keep_files: true не копит файлы между выпусками.

Контракт на диске: схема — целое 2, время — UTC ISO 8601 (суффикс Z),
цена — положительное целое число тенге, отсутствующее значение — JSON null.
Хеши считаются ровно по записываемым UTF-8 байтам.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .config import Thresholds
from .evaluate import coverage_days, weighted_median
from .export import SHOPS, _product_to_dict, fair_reference_from_spans
from .storage import (
    Span,
    catalog_products_for_shop,
    first_seen_map,
    histories_for_shop,
    last_successful_crawl,
)

SCHEMA_VERSION = 2
# Хвост карточки: пять видимых наблюдений и стоящее перед ними наблюдение —
# база сравнения. Не даунсемплить: проценты на карточке сравнивают соседние цены.
RECENT_OBSERVATIONS = 6


def _iso_z(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _z(value: str) -> str:
    """Метку времени из базы — в единый формат catalog-v2 (UTC ISO 8601, Z)."""
    return _iso_z(datetime.fromisoformat(value.replace("Z", "+00:00")))


def export_moment(conn: sqlite3.Connection) -> datetime:
    """Момент выпуска catalog-v2 — из данных, а не из часов экспортёра.

    Последний успешный обход по всем магазинам: пока новых наблюдений нет,
    содержимое не меняется и хеши стабильны между запусками — манифест остаётся
    честным детектором изменений, а публикации не дёргают gh-pages. Fallback —
    конец последнего отрезка (успешных обходов не было, манифест и так пуст);
    на совсем пустой базе — текущее время (вывод от него не зависит).
    """
    row = conn.execute("SELECT MAX(started_at) FROM crawls WHERE ok = 1").fetchone()
    stamp = row[0] if row else None
    if not stamp:
        row = conn.execute("SELECT MAX(last_seen) FROM spans").fetchone()
        stamp = row[0] if row else None
    if not stamp:
        return datetime.now(UTC)
    return datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))


def _write(path: Path, payload: dict) -> bytes:
    """Пишет JSON и возвращает ровно те байты, которые оказались в файле."""
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    path.write_bytes(body)
    return body


def _history_row(spans: list[Span], at: datetime, window_since: datetime) -> dict:
    """HistoryRow магазина: график по дням и хвост исходных наблюдений.

    Точки строятся по наблюдениям в наличии, как в legacy-истории: последняя
    цена за день плюс окончание последнего отрезка. Покрытие считается по
    отрезкам и не зависит от числа экспортированных точек.
    """
    stocked = [s for s in spans if s.in_stock]
    by_day: dict[str, dict] = {}
    for span in stocked:
        day = span.first_seen.astimezone(UTC).date().isoformat()
        # Отрезки идут по времени: поздний отрезок дня перезаписывает ранний —
        # в графике остаётся последняя цена за день.
        by_day[day] = {"date": day, "price": span.price, "old_price": span.old_price}
    points = [by_day[day] for day in sorted(by_day)]

    last = stocked[-1] if stocked else None
    if last is not None:
        end = last.last_seen.astimezone(UTC).date().isoformat()
        # Окончание последнего отрезка: цена, державшаяся дни, — линия, а не точка.
        if not points or points[-1]["date"] != end:
            points.append({"date": end, "price": last.price, "old_price": last.old_price})

    prices = [s.price for s in stocked] + ([spans[-1].price] if spans else [])
    w_med = weighted_median(stocked, window_since, at)
    days_at_current = 0
    if last is not None:
        streak_start = last.first_seen
        for span in reversed(stocked):
            if span.price != last.price:
                break
            streak_start = span.first_seen
        days_at_current = max(
            0, int((last.last_seen - streak_start).total_seconds() // 86_400)
        )

    return {
        "points": points,
        "recent_points": [
            {"date": _iso_z(s.first_seen), "price": s.price, "old_price": s.old_price}
            for s in stocked[-RECENT_OBSERVATIONS:]
        ],
        "min": min(prices) if prices else None,
        "median": w_med if w_med is not None else (sorted(prices)[len(prices) // 2] if prices else None),
        "days_at_current": days_at_current,
        "coverage_days": coverage_days(spans, at),
    }


def export_catalog(conn: sqlite3.Connection, out_dir: Path, *, at: datetime) -> Path:
    """Выпускает catalog-v2 в out_dir и возвращает каталог catalog-v2.

    Все чтения идут в одном снимке SQLite: обход, завершившийся параллельно,
    увидит следующий экспорт — манифест и файлы магазинов всегда согласованы.
    """
    th = Thresholds()
    window_since = at - timedelta(days=th.retention_days)
    fair_since = at - timedelta(days=th.low_window_days)
    catalog_dir = Path(out_dir) / "catalog-v2"
    catalog_dir.mkdir(parents=True, exist_ok=True)

    own_snapshot = not conn.in_transaction
    if own_snapshot:
        conn.execute("BEGIN")  # единый снимок WAL для всех чтений экспорта
    try:
        shops: dict[str, dict] = {}
        for shop in SHOPS:  # стабильный порядок магазинов
            last_crawl = last_successful_crawl(conn, shop)
            if last_crawl is None:
                # Магазин без успешного обхода не получает запись манифеста.
                continue
            products = catalog_products_for_shop(conn, shop, window_since)
            histories = histories_for_shop(conn, shop, window_since)
            first_seen = first_seen_map(conn, (p.identity for p in products))
            shop_dir = catalog_dir / shop
            shop_dir.mkdir(parents=True, exist_ok=True)

            rows: list[dict] = []
            items: dict[str, dict] = {}
            for product in sorted(products, key=lambda p: p.sku):  # SKU лексикографически
                spans = histories.get(product.identity, [])
                # Fair-reference — по окну low_window_days, как legacy
                # `_fair_reference_and_age`: полоса между low-окном и retention
                # не влияет на вердикт. Retention остаётся окном графика.
                fair_spans = [s for s in spans if s.last_seen >= fair_since]
                fair, ref, _age, pump = fair_reference_from_spans(product, fair_spans, at, th)
                last_seen = spans[-1].last_seen if spans else None
                seen_first = first_seen.get(product.identity)
                rows.append(
                    {
                        "product": _product_to_dict(
                            product, _z(seen_first) if seen_first else None
                        ),
                        "last_seen": _iso_z(last_seen) if last_seen else None,
                        "base_price": ref,
                        "fair_discount": fair,
                        "pump_price": pump,
                        # Точное совпадение модели добавляет задача 6.
                        "exact_model": None,
                    }
                )
                items[product.sku] = _history_row(spans, at, window_since)

            index_body = _write(
                shop_dir / "index.json", {"schema": SCHEMA_VERSION, "shop": shop, "rows": rows}
            )
            history_body = _write(
                shop_dir / "history.json", {"schema": SCHEMA_VERSION, "shop": shop, "items": items}
            )
            shops[shop] = {
                "last_crawl": _iso_z(last_crawl),
                "count": len(rows),
                "index_sha256": hashlib.sha256(index_body).hexdigest(),
                "history_sha256": hashlib.sha256(history_body).hexdigest(),
            }
    finally:
        if own_snapshot:
            conn.commit()

    # Файлы магазинов завершены — манифест заменяется атомарно.
    tmp = catalog_dir / "manifest.json.tmp"
    _write(tmp, {"schema": SCHEMA_VERSION, "shops": shops})
    os.replace(tmp, catalog_dir / "manifest.json")
    return catalog_dir
