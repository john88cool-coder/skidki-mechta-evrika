"""Проверка миграции: старая база без колонки image → connect() её добавляет.

    python probe/migrate_smoke.py <путь к старой базе>

В CI база приходит из кэша Actions со старой схемой: без ALTER TABLE парсер
не смог бы записать image и обход падал бы на «no such column».
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from skidki import storage  # noqa: E402


def columns(db: Path) -> list[str]:
    conn = sqlite3.connect(db)
    try:
        return [row[1] for row in conn.execute("PRAGMA table_info(products)")]
    finally:
        conn.close()


OLD_SCHEMA = """
CREATE TABLE products (
    identity    TEXT PRIMARY KEY,
    shop        TEXT NOT NULL,
    title       TEXT NOT NULL,
    brand       TEXT,
    category    TEXT,
    url         TEXT NOT NULL,
    grp         TEXT,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL
);
"""


def make_old_db(path: Path) -> None:
    """База старой схемы: без колонки image (как в кэше Actions до 2026-09-19)."""
    conn = sqlite3.connect(path)
    try:
        conn.executescript(OLD_SCHEMA)
        conn.execute(
            "INSERT INTO products (identity, shop, title, url, first_seen, last_seen) "
            "VALUES ('mechta:1', 'mechta', 'Тест', 'https://example.kz/1', '2026-09-01', '2026-09-01')"
        )
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "old.sqlite3"
        source = Path(sys.argv[1]) if len(sys.argv) > 1 else None
        if source and source.exists():
            shutil.copy2(source, copy)
        else:
            make_old_db(copy)

        before = columns(copy)
        print("до миграции: image =", "image" in before)

        with storage.connect(copy) as conn:
            rows = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
            # Запись позиции с картинкой в базу старой схемы — то, что делает обход.
            from skidki.models import Product

            storage.save_products(conn, [Product(
                shop="mechta", sku="1", title="Тест", price=1000,
                url="https://example.kz/1", image="https://pi.mdev.kz/abc?w=400",
            )])
            image = conn.execute("SELECT image FROM products WHERE identity='mechta:1'").fetchone()[0]
            print("строк products:", rows, "| image записан:", image)

        after = columns(copy)
        print("после connect(): image =", "image" in after)
        assert "image" in after, "миграция не добавила колонку image"

    # Основной путь: указанная база (прод) тоже должна переживать connect().
    if source and source.exists():
        with tempfile.TemporaryDirectory() as tmp2:
            copy = Path(tmp2) / "prod-copy.sqlite3"
            shutil.copy2(source, copy)
            with storage.connect(copy) as conn:
                print("прод-копия: products =", conn.execute("SELECT COUNT(*) FROM products").fetchone()[0])


if __name__ == "__main__":
    main()