import sqlite3
from datetime import datetime, timedelta, timezone

from skidki.models import Product
from skidki.storage import connect, enqueue, price_drop_candidates, save_products, take_queue


def test_product_optional_metadata_fields_and_queue_roundtrip(tmp_path):
    db = tmp_path / "roundtrip.sqlite3"
    t0 = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
    item = Product(
        shop="technodom",
        sku="273887",
        title="Смарт-часы Huawei Watch GT4",
        price=49_990,
        old_price=99_990,
        url="https://www.technodom.kz/p/watch-gt4",
        brand="HUAWEI",
        category="Смарт часы",
        group="phones",
        image="https://api.technodom.kz/f3/api/v1/images/gt4.webp",
        mpn="Phoinix-B19L",
        rating=4.95,
        reviews_count=77,
    )
    with connect(db) as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0].lower()
        assert mode == "wal"
        save_products(conn, [item], at=t0)
        enqueue(conn, item.identity, item.price, '[{"signal": "скидка магазина", "base": 99990}]', at=t0)
        queued = take_queue(conn, since=t0 - timedelta(hours=1))

    assert len(queued) == 1
    got = queued[0].product
    assert got.image == "https://api.technodom.kz/f3/api/v1/images/gt4.webp"
    assert got.mpn == "Phoinix-B19L"
    assert got.rating == 4.95
    assert got.reviews_count == 77


def test_legacy_db_migrates_new_columns_and_watches_table(tmp_path):
    db = tmp_path / "legacy.sqlite3"
    raw = sqlite3.connect(db)
    raw.executescript(
        """
        CREATE TABLE products (
            identity TEXT PRIMARY KEY,
            shop TEXT NOT NULL,
            title TEXT NOT NULL,
            brand TEXT,
            category TEXT,
            url TEXT NOT NULL,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL
        );
        """
    )
    raw.commit()
    raw.close()

    with connect(db) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(products)")}
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"grp", "image", "mpn", "rating", "reviews_count"} <= cols
    assert "watches" in tables


def test_price_drop_candidates_normalizes_non_utc_since(tmp_path):
    db = tmp_path / "tz.sqlite3"
    t0 = datetime(2026, 11, 10, 20, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 11, 10, 22, 0, tzinfo=timezone.utc)
    almaty = timezone(timedelta(hours=5))
    # 2026-11-10 21:00 UTC == 2026-11-11 02:00 +05:00.
    # Без _iso() строка "2026-11-11T02:00:00+05:00" лексикографически БОЛЬШЕ
    # "2026-11-10T20:00:00+00:00" и ошибочно отбрасывает пик в 20:00 UTC!
    since_local = datetime(2026, 11, 11, 0, 30, tzinfo=almaty)  # 19:30 UTC

    high = Product(shop="mechta", sku="1", title="TV", price=200_000, url="https://x/1")
    low = Product(shop="mechta", sku="1", title="TV", price=150_000, url="https://x/1")
    with connect(db) as conn:
        save_products(conn, [high], at=t0)
        save_products(conn, [low], at=t1)
        found = price_drop_candidates(conn, since=since_local, min_pct=15, min_price=10_000, limit=10)
    assert [p.identity for p in found] == ["mechta:1"]
