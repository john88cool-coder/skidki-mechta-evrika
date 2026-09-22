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

from .config import ROOT
from .models import Product
from .scoring import score_product
from .storage import connect, current_deals, history as spans_history, last_successful_crawl, previous_item_count

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


def _product_to_dict(p: Product) -> dict:
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
    }


def _fair_discount_for(conn, product, at):
    # честная скидка по истории ИС: медиана 14д, минимум 3 дня, просадка >= drop threshold
    from datetime import timedelta
    from .config import Thresholds
    from .evaluate import weighted_median, coverage_days
    th = Thresholds()
    trend_since = at - timedelta(days=th.trend_window_days)
    spans = [s for s in spans_history(conn, product.identity, trend_since) if s.in_stock]
    ref = weighted_median(spans, trend_since, at)
    if not ref or coverage_days(spans, at) < th.min_history_days:
        return None
    drop = (ref - product.price) / ref * 100
    if drop < th.drop_pct or ref - product.price < th.min_drop_tenge:
        # История есть, а падения нет: честная скидка — ноль, а не «неизвестно».
        # Иначе нарисованная «−81%» при цене, стоящей неделю, не получала
        # бейдж «Рисованная?» (он требует подтверждённую fair_discount).
        return 0.0
    return round(drop, 1)


def _score_for(conn, product, at):
    # возраст последнего наблюдения для freshness
    try:
        from datetime import UTC
        last = conn.execute("SELECT last_seen FROM spans WHERE identity=? ORDER BY last_seen DESC LIMIT 1", (product.identity,)).fetchone()
        age_h = None
        if last:
            from datetime import datetime
            dt = datetime.fromisoformat(last[0].replace("Z","+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            age_h = (at - dt).total_seconds()/3600
    except Exception:
        age_h = None
    fair = _fair_discount_for(conn, product, at)
    return score_product(product, fair_discount=fair, age_hours=age_h)


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

    deals = []
    picked: dict[str, Product] = {}
    for shop in SHOPS:
        products = current_deals(
            conn,
            DASHBOARD_MIN_PCT,
            DASHBOARD_MIN_PRICE,
            DASHBOARD_MAX_PCT,
            DASHBOARD_LIMIT,
            shop,
        )
        for product in products:
            sc = _score_for(conn, product, now)
            picked[product.identity] = product
            deals.append({
                "product": _product_to_dict(product),
                "signal": "deal",
                "drop_pct": product.shop_discount_pct,
                "fair_discount": sc.fair_discount,
                "value_score": sc.value_score,
                "is_pick": sc.is_pick,
                "badges": list(sc.badges),
                "inflated_gap": sc.inflated_gap,
            })
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
    avg_discount = median([d["drop_pct"] or 0 for d in deals]) if deals else 0

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
    since = (datetime.now(UTC) - timedelta(days=90)).isoformat(timespec="seconds")

    for product in deals[:limit]:
        rows = conn.execute(
            """SELECT first_seen, price, old_price FROM spans
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

        prices = sorted(point["price"] for point in points)
        history[product.identity] = {
            "points": points,
            # Five visible observations plus their preceding baseline. Never
            # downsample this tail: card percentages compare adjacent prices.
            "recent_points": [
                {"date": row[0], "price": row[1], "old_price": row[2]}
                for row in rows[-6:]
            ],
            "min": prices[0],
            "median": prices[len(prices) // 2],
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
