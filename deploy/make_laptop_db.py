"""Копия прод-базы под ноутбук: история одного магазина + настройки групп.

Гибридная схема: облачный обход (GitHub Actions) ведёт свои магазины в кэше
Actions, ноутбук — mechta в своей базе. Эта утилита берёт копию прод-базы
домашнего ПК и вычищает из неё всё, кроме указанного магазина, чтобы ноутбук
наследовал его историю цен (иначе «упало»/«минимум» молчат первые дни).

    python deploy/make_laptop_db.py --source data/skidki.sqlite3 \
        --target data/laptop/skidki.sqlite3 [--shop mechta]
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

# Таблицы, привязанные к магазину явно или через identity "<shop>:<sku>".
SHOP_TABLES = ("crawls", "products")
IDENTITY_TABLES = ("spans", "alerts", "queue")


def make(source: Path, target: Path, shop: str = "mechta") -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)  # схема + все данные, дальше чистим чужие магазины
        with dst:
            for table in SHOP_TABLES:
                dst.execute(f"DELETE FROM {table} WHERE shop != ?", (shop,))
            for table in IDENTITY_TABLES:
                dst.execute(
                    f"DELETE FROM {table} WHERE identity NOT LIKE ?", (f"{shop}:%",)
                )
            # muted — предпочтения владельца, остаются целиком.
        dst.execute("VACUUM")
        dst.commit()
        counts = {
            table: dst.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in (*SHOP_TABLES, *IDENTITY_TABLES, "muted")
        }
        size_kb = target.stat().st_size // 1024
        print(f"база для ноутбука: {target} ({size_kb} КБ), магазин {shop}")
        for table, count in counts.items():
            print(f"  {table}: {count}")
    finally:
        dst.close()
        src.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="прод-база домашнего ПК")
    parser.add_argument("--target", type=Path, required=True, help="куда положить базу ноутбука")
    parser.add_argument("--shop", default="mechta", help="какой магазин оставить (по умолчанию mechta)")
    args = parser.parse_args()
    if not args.source.exists():
        raise SystemExit(f"нет исходной базы: {args.source}")
    make(args.source, args.target, args.shop)


if __name__ == "__main__":
    main()
