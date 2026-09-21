"""Быстрая сводка по локальной базе: свежие обходы и очередь находок."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "data" / "skidki.sqlite3"


def main() -> None:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        for row in conn.execute(
            "SELECT shop, MAX(started_at), item_count, ok FROM crawls GROUP BY shop ORDER BY shop"
        ):
            print(f"  {row[0]:<10} последний: {row[1]} позиций: {row[2]} ok={row[3]}")
        print("  queue:", conn.execute("SELECT COUNT(*) FROM queue").fetchone()[0])
        print("  muted:", [row[0] for row in conn.execute("SELECT grp FROM muted")])
    finally:
        conn.close()


if __name__ == "__main__":
    main()
