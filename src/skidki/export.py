"""Экспорт данных из SQLite в JSON для веб-панели skidki-dashboard.

Панель статична (GitHub Pages): бэкенда нет, поэтому обход после каждой
итерации выгружает срез данных в `web/static/data`, а workflow публикует его
в ветку gh-pages рядом со сборкой фронтенда.
"""

from __future__ import annotations

import json
import os
import sqlite3
from statistics import median
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .config import ROOT, Thresholds
from .evaluate import coverage_days, honest_baseline, returned_to_earlier, weighted_median
from .matching import marketplace_medians
from .models import Product
from .scoring import score_product
from .storage import (
    Span,
    active_catalog_products,
    connect,
    current_deals,
    first_seen_map,
    history as spans_history,
    last_successful_crawl,
    previous_item_count,
    price_drop_candidates,
)

# Только включённые парсеры: каркасы (kaspi, wb, ozon, satu, dns) висели на
# панели красными «ошибками», хотя их никто не обходит.
from .parsers import REGISTRY  # noqa: E402

SHOPS = tuple(REGISTRY)

# Куда пишется срез: SvelteKit копирует static/ в сборку как есть.
# В CI пакет установлен в site-packages, там ROOT — не репозиторий, поэтому
# путь можно переопределить переменной SKIDKI_WEB_DATA (задаёт crawl.yml).
WEB_DATA = Path(os.environ.get("SKIDKI_WEB_DATA") or ROOT / "web" / "static" / "data")

# Порог для топа панели: мягче сигналов владельца (rules.toml — от 20% и
# 20 000 ₸), иначе панель почти пуста. Скидки ≤ 90% — ошибки цены, отсекаем.
DASHBOARD_MIN_PCT = 15
DASHBOARD_MIN_PRICE = 10_000
DASHBOARD_MAX_PCT = 90.0
DASHBOARD_LIMIT = 50  # на магазин
# Всего в срезе: 50 на всю панель отдавали топ одному магазину (mechta — 34 из
# 50 с её «−80%»), shop.kz и Алсер не попадали вовсе.
DASHBOARD_TOTAL = 150
DASHBOARD_PER_SHOP_MIN = 10
# Лента «реальных снижений»: цена ниже собственной медианы за 14 дней,
# независимо от того, рисует ли магазин зачёркнутую цену. На живых данных
# 2026-09-23 147 из 150 «скидок» витрины оказались обычной ценой, а в одной
# только Мечте 399 позиций реально подешевели на 10%+ — и на сайт не попадали.
REAL_DROP_PREFILTER_PCT = 8
REAL_DROP_PER_SHOP = 40
REAL_DROP_TOTAL = 150


def _first_seen(conn: sqlite3.Connection, identity: str) -> str | None:
    """Когда позиция впервые появилась в мониторинге (переживает prune spans)."""
    row = conn.execute(
        "SELECT first_seen FROM products WHERE identity = ?", (identity,)
    ).fetchone()
    if row and row[0]:
        return row[0]
    fallback = conn.execute(
        "SELECT MIN(first_seen) FROM spans WHERE identity = ?", (identity,)
    ).fetchone()
    return fallback[0] if fallback and fallback[0] else None


def _product_to_dict(p: Product, first_seen: str | None = None) -> dict:
    return {
        "shop": p.shop,
        "sku": p.sku,
        "title": p.title,
        "price": p.price,
        "old_price": p.old_price,
        "url": p.url,
        "brand": p.brand,
        "category": p.category,
        "group": p.group,
        "in_stock": p.in_stock,
        "discount_pct": p.shop_discount_pct,
        "image": p.image,
        "mpn": p.mpn,
        "rating": p.rating,
        "reviews_count": p.reviews_count,
        "first_seen": first_seen,
    }


def _fair_reference_and_age(
    conn: sqlite3.Connection, product: Product, at: datetime
) -> tuple[float | None, int | None, float | None, int | None]:
    """За один запрос к истории: (fair_discount, reference, age_hours, pump_price).

    reference — честная база (evaluate.honest_baseline); pump_price — цена, до
    которой товар поднимали перед скидкой (None, если накрутки не было).
    """
    th = Thresholds()
    trend_since = at - timedelta(days=th.trend_window_days)
    window = spans_history(conn, product.identity, at - timedelta(days=th.low_window_days))
    all_spans = [s for s in window if s.last_seen >= trend_since]
    age_h: float | None = None
    if all_spans:
        age_h = max(0.0, (at - all_spans[-1].last_seen).total_seconds() / 3600.0)
    else:
        last = conn.execute(
            "SELECT last_seen FROM spans WHERE identity = ? ORDER BY last_seen DESC, id DESC LIMIT 1",
            (product.identity,),
        ).fetchone()
        if last and last[0]:
            dt = datetime.fromisoformat(str(last[0]).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            age_h = max(0.0, (at - dt).total_seconds() / 3600.0)

    spans = [s for s in all_spans if s.in_stock]
    baseline = honest_baseline(window, at, th)
    ref = baseline.reference
    if not ref or coverage_days(spans, at) < th.min_history_days:
        return None, None, age_h, None
    drop = (ref - product.price) / ref * 100
    earlier = [s for s in window if s.last_seen < trend_since]
    if returned_to_earlier(earlier, product.price):
        # Цена вернулась к прежнему уровню после временного подъёма — не скидка.
        return 0.0, ref, age_h, None
    if drop < th.drop_pct or ref - product.price < th.min_drop_tenge:
        # История есть, а падения нет: честная скидка — ноль, а не «неизвестно».
        return 0.0, ref, age_h, None
    return round(drop, 1), ref, age_h, baseline.pump_price


def _deal_dict(
    conn: sqlite3.Connection,
    product: Product,
    now: datetime,
    signal: str,
    *,
    first_seen: str | None = None,
    market_median: int | None = None,
) -> dict:
    """Позиция витрины: заявленная скидка магазина + вердикт собственной истории и рынка."""
    fair, ref, age_h, pump_price = _fair_reference_and_age(conn, product, now)
    sc = score_product(
        product,
        fair_discount=fair,
        marketplace_median=market_median,
        rating=product.rating,
        reviews_count=product.reviews_count,
        age_hours=age_h,
    )
    resolved_first = first_seen if first_seen is not None else _first_seen(conn, product.identity)
    return {
        "product": _product_to_dict(product, resolved_first),
        "signal": signal,
        "drop_pct": product.shop_discount_pct,
        "fair_discount": fair,
        # Обычная цена — взвешенная медиана окна тренда (для «обычно X ₸»).
        "base_price": ref,
        # Накрутка: до этой цены товар поднимали перед скидкой (иначе None).
        "pump_price": pump_price,
        "value_score": sc.value_score,
        "is_pick": sc.is_pick,
        "badges": list(sc.badges),
        "inflated_gap": sc.inflated_gap,
    }


def _shop_label(shop: str) -> str:
    labels = {
        "mechta": "Мечта",
        "evrika": "Эврика",
        "shopkz": "Shop.kz",
        "sulpak": "Сулпак",
        "technodom": "Технодом",
        "alser": "Алсер",
        "kaspi": "Kaspi",
        "wb": "Wildberries",
        "ozon": "Ozon",
        "satu": "Satu.kz",
        "dns": "DNS",
    }
    return labels.get(shop, shop)


def export_dashboard(conn: sqlite3.Connection, out_dir: Path) -> list[Product]:
    """Главный JSON: топ-скидки по всем магазинам и состояние обходов."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # Порог «давно не было обхода»: расписание — раз в 2 часа.
    now = datetime.now(UTC)
    stale_after = timedelta(hours=6)

    # Рыночные медианы по активному каталогу: скоринг видит кросс-магазинный контекст.
    market_medians = marketplace_medians(active_catalog_products(conn))

    deals = []
    picked: dict[str, Product] = {}
    candidates: list[Product] = []
    for shop in SHOPS:
        candidates.extend(
            current_deals(
                conn,
                DASHBOARD_MIN_PCT,
                DASHBOARD_MIN_PRICE,
                DASHBOARD_MAX_PCT,
                DASHBOARD_LIMIT,
                shop,
            )
        )
    fmap = first_seen_map(conn, (p.identity for p in candidates))
    for product in candidates:
        picked[product.identity] = product
        deals.append(
            _deal_dict(
                conn,
                product,
                now,
                "deal",
                first_seen=fmap.get(product.identity),
                market_median=market_medians.get(product.identity),
            )
        )
    # Подозрительные («Рисованная?») — в конец: витрина обещает скидки,
    # проверенные историей, а не самые большие зачёркнутые цены.
    rank = lambda deal: ("Рисованная?" in deal["badges"], -(deal["drop_pct"] or 0))  # noqa: E731
    deals.sort(key=rank)
    # Каждому магазину — минимум DASHBOARD_PER_SHOP_MIN мест, иначе магазины
    # со скромными, но честными скидками (Алсер: до −48%) вытеснялись целиком.
    guaranteed: list[dict] = []
    for shop in SHOPS:
        guaranteed += [d for d in deals if d["product"]["shop"] == shop][:DASHBOARD_PER_SHOP_MIN]
    taken = {id(d) for d in guaranteed}
    rest = [d for d in deals if id(d) not in taken]
    deals = sorted([*guaranteed, *rest[: max(0, DASHBOARD_TOTAL - len(guaranteed))]], key=rank)
    shown_ids = {f'{d["product"]["shop"]}:{d["product"]["sku"]}' for d in deals}
    picked = {identity: product for identity, product in picked.items() if identity in shown_ids}

    # Реальные снижения по собственной истории — независимо от зачёркнутой цены.
    real: list[dict] = []
    since = now - timedelta(days=Thresholds().trend_window_days)
    for shop in SHOPS:
        per_shop: list[dict] = []
        for product in price_drop_candidates(
            conn, since, REAL_DROP_PREFILTER_PCT, DASHBOARD_MIN_PRICE, REAL_DROP_PER_SHOP * 3, shop
        ):
            if product.identity in shown_ids:
                continue
            deal = _deal_dict(
                conn,
                product,
                now,
                "drop",
                first_seen=fmap.get(product.identity),
                market_median=market_medians.get(product.identity),
            )
            if (deal["fair_discount"] or 0) >= Thresholds().drop_pct:
                per_shop.append(deal)
                picked[product.identity] = product
        per_shop.sort(key=lambda d: -(d["fair_discount"] or 0))
        real += per_shop[:REAL_DROP_PER_SHOP]
    real.sort(key=lambda d: -(d["fair_discount"] or 0))
    real = real[:REAL_DROP_TOTAL]
    real_ids = {f'{d["product"]["shop"]}:{d["product"]["sku"]}' for d in real}
    picked = {i: p for i, p in picked.items() if i in shown_ids or i in real_ids}
    deals = [*deals, *real]

    shops: list[dict] = []
    for shop in SHOPS:
        last = last_successful_crawl(conn, shop)
        count = previous_item_count(conn, shop) or 0

        if last is None:
            status = "error"
        elif now - last > stale_after:
            status = "warning"
        else:
            status = "ok"

        shops.append(
            {
                "name": shop,
                "label": _shop_label(shop),
                "last_crawl": last.isoformat() if last else None,
                "item_count": count,
                "status": status,
            }
        )

    # Статистика
    total_products = sum(s["item_count"] for s in shops)
    total_deals = len(deals)
    effective_discounts = [
        float(d["fair_discount"])
        if (d.get("fair_discount") or 0) > 0
        else float(d["drop_pct"])
        for d in deals
        if (d.get("fair_discount") or 0) > 0 or (d.get("drop_pct") or 0) > 0
    ]
    avg_discount = median(effective_discounts) if effective_discounts else 0.0

    data = {
        "updated_at": now.isoformat(),
        "deals": deals,
        "shops": shops,
        "stats": {
            "total_products": total_products,
            "total_deals": total_deals,
            "avg_discount": round(avg_discount, 1),
        },
    }

    with open(out_dir / "latest.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # Позиции витрины — для истории: у каждой карточки должен быть график.
    return [
        picked[identity]
        for deal in deals
        if (identity := f'{deal["product"]["shop"]}:{deal["product"]["sku"]}') in picked
    ]


def export_history(
    conn: sqlite3.Connection, out_dir: Path, limit: int = 300, shown: list[Product] | None = None
) -> None:
    """История цен одним файлом — только по самым интересным позициям.

    Раньше история лежала тысячью мелких JSON (по файлу на товар): ~10 тыс.
    файлов и ~5,6 МБ на каждые два часа — дорого для git и gh-pages.
    Поэтому берём `limit` позиций с самой глубокой скидкой и кладём всё в
    history.json (ключ — identity). Фронтенд грузит файл один раз и кэширует.
    """
    deals = []
    for shop in SHOPS:
        deals.extend(current_deals(conn, min_pct=15, min_price=10000, max_pct=90, limit=limit, shop=shop))
    deals.sort(key=lambda p: p.shop_discount_pct or 0, reverse=True)
    # Сначала — позиции витрины (их карточкам история нужна обязательно),
    # затем — самые глубокие скидки до лимита.
    if shown:
        seen = {p.identity for p in shown}
        deals = [*shown, *(p for p in deals if p.identity not in seen)]

    history: dict[str, dict] = {}
    now = datetime.now(UTC)
    th = Thresholds()
    window_since = now - timedelta(days=th.retention_days)
    since = window_since.isoformat(timespec="seconds")

    for product in deals[:limit]:
        rows = conn.execute(
            """SELECT first_seen, price, old_price, last_seen FROM spans
               WHERE identity = ? AND in_stock = 1 AND last_seen >= ?
               ORDER BY first_seen""",
            (product.identity, since),
        ).fetchall()
        if not rows:
            continue

        step = max(1, len(rows) // 60)  # не больше ~60 точек на график
        points = [
            {"date": row[0][:10], "price": row[1], "old_price": row[2]}
            for row in rows[::step]
        ]
        # Последнее наблюдение — обязательно: график должен кончаться текущей ценой.
        if points and points[-1]["price"] != product.price:
            points.append({"date": rows[-1][0][:10], "price": product.price, "old_price": None})
        # Конец последнего отрезка: цена, державшаяся 10 дней, — линия, а не точка.
        last_seen = rows[-1][3][:10]
        if points and points[-1]["date"] != last_seen:
            points.append(
                {
                    "date": last_seen,
                    "price": points[-1]["price"],
                    "old_price": points[-1]["old_price"],
                }
            )

        span_objs = [
            Span(
                first_seen=datetime.fromisoformat(str(r[0]).replace("Z", "+00:00")),
                last_seen=datetime.fromisoformat(str(r[3]).replace("Z", "+00:00")),
                price=int(r[1]),
                in_stock=True,
                old_price=int(r[2]) if r[2] is not None else None,
            )
            for r in rows
        ]
        w_med = weighted_median(span_objs, window_since, now)
        all_prices = [int(r[1]) for r in rows] + [product.price]

        # Сколько дней подряд держится текущая цена в хвосте отрезков:
        streak_start = span_objs[-1].last_seen
        current_price = span_objs[-1].price
        for sp in reversed(span_objs):
            if sp.price != current_price:
                break
            streak_start = sp.first_seen
        days_at_current = max(
            0, int((span_objs[-1].last_seen - streak_start).total_seconds() // 86_400)
        )

        history[product.identity] = {
            "points": points,
            # Five visible observations plus their preceding baseline. Never
            # downsample this tail: card percentages compare adjacent prices.
            "recent_points": [
                {"date": row[0], "price": row[1], "old_price": row[2]}
                for row in rows[-6:]
            ],
            "min": min(all_prices),
            "median": w_med if w_med is not None else sorted(all_prices)[len(all_prices) // 2],
            "days_at_current": days_at_current,
        }

    with open(out_dir / "history.json", "w", encoding="utf-8") as f:
        json.dump({"updated_at": datetime.now(UTC).isoformat(timespec="seconds"), "history": history}, f, ensure_ascii=False)


def export_for_web(db_path: Path | None = None, out_dir: Path | None = None) -> Path:
    """Генерирует все JSON для веб-панели."""
    out = out_dir or WEB_DATA
    out.mkdir(parents=True, exist_ok=True)

    with connect(db_path) as conn:
        shown = export_dashboard(conn, out)
        export_history(conn, out, shown=shown)

    return out


if __name__ == "__main__":
    target = export_for_web()
    print(f"экспортировано для веб-панели: {target}")
