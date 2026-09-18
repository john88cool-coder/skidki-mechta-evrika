"""Экспорт данных из SQLite в JSON для веб-панели skidki-dashboard."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .config import DB_PATH, GROUPS
from .models import Product
from .storage import connect, current_deals, last_successful_crawl, previous_item_count


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
    }


def _shop_label(shop: str) -> str:
    labels = {
        "mechta": "Мечта",
        "evrika": "Эврика",
        "shopkz": "Shop.kz",
        "sulpak": "Сулпак",
        "technodom": "Технодом",
        "alser": "Алсер",
    }
    return labels.get(shop, shop)


def export_dashboard(conn: sqlite3.Connection, out_dir: Path) -> None:
    """Главный JSON для дашборда: топ-скидки, статус магазинов."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # Топ скидки по всем магазинам
    deals = []
    for shop in ("mechta", "evrika", "shopkz", "sulpak", "technodom", "alser"):
        for p in current_deals(conn, min_pct=15, min_price=10000, max_pct=90, limit=20, shop=shop):
            deals.append({
                "product": _product_to_dict(p),
                "signal": "deal",
                "drop_pct": p.shop_discount_pct,
            })

    # Сортировка по глубине скидки
    deals.sort(key=lambda d: d["drop_pct"] or 0, reverse=True)
    deals = deals[:50]  # топ-50

    # Статус магазинов
    shops = []
    now = datetime.now(UTC)
    for shop in ("mechta", "evrika", "shopkz", "sulpak", "technodom", "alser"):
        last = last_successful_crawl(conn, shop)
        count = previous_item_count(conn, shop) or 0
        
        if last is None:
            status = "error"
        elif (now - last).total_seconds() > 6 * 3600:
            status = "warning"
        else:
            status = "ok"

        shops.append({
            "name": shop,
            "label": _shop_label(shop),
            "last_crawl": last.isoformat() if last else now.isoformat(),
            "item_count": count,
            "status": status,
        })

    # Статистика
    total_products = sum(s["item_count"] for s in shops)
    total_deals = len(deals)
    avg_discount = sum(d["drop_pct"] or 0 for d in deals) / max(total_deals, 1)

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


def export_history(conn: sqlite3.Connection, out_dir: Path, days: int = 90) -> None:
    """История цен по товарам (для страницы товара)."""
    history_dir = out_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    # Получаем все товары с историей
    cursor = conn.execute("""
        SELECT DISTINCT identity FROM spans 
        WHERE last_seen >= datetime('now', ?)
    """, (f"-{days} days",))

    for (identity,) in cursor.fetchall():
        shop, sku = identity.split(":", 1)
        
        # История цен
        spans = conn.execute("""
            SELECT first_seen, last_seen, price, old_price
            FROM spans
            WHERE identity = ? AND in_stock = 1
            ORDER BY first_seen
        """, (identity,)).fetchall()

        if not spans:
            continue

        # Текущие данные товара
        product_row = conn.execute("""
            SELECT shop, title, brand, category, url, grp
            FROM products WHERE identity = ?
        """, (identity,)).fetchone()

        if not product_row:
            continue

        shop_name, title, brand, category, url, grp = product_row

        # Формируем точки для графика (семплируем если много)
        points = []
        for first_seen, last_seen, price, old_price in spans[::max(1, len(spans) // 50)]:
            points.append({
                "date": first_seen[:10],
                "price": price,
                "old_price": old_price,
            })

        prices = [p["price"] for p in points]
        stats = {
            "min_90d": min(prices) if prices else 0,
            "median_30d": sorted(prices)[len(prices) // 2] if prices else 0,
            "days_at_current": 1,  # упрощённо
        }

        product_data = {
            "product": {
                "shop": shop_name,
                "sku": sku,
                "title": title,
                "price": prices[-1] if prices else 0,
                "url": url,
                "brand": brand,
                "category": category,
                "group": grp,
            },
            "history": points,
            "stats": stats,
        }

        # Сохраняем по пути /history/{shop}/{sku}.json
        shop_dir = history_dir / shop
        shop_dir.mkdir(exist_ok=True)
        with open(shop_dir / f"{sku}.json", "w", encoding="utf-8") as f:
            json.dump(product_data, f, ensure_ascii=False, indent=2)


def export_for_web(db_path: Path | None = None, out_dir: Path | None = None) -> Path:
    """Генерирует все JSON для веб-панели."""
    out = out_dir or Path("web/static/data")
    
    with connect(db_path) as conn:
        export_dashboard(conn, out)
        export_history(conn, out)
    
    return out


if __name__ == "__main__":
    export_for_web()
    print(f"Экспортировано в {Path('web/static/data')}")
