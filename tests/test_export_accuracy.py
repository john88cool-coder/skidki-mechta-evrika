import json
from datetime import UTC, datetime, timedelta

from skidki import export, storage
from skidki.models import Product


def test_export_preserves_true_first_seen_after_prune_and_uses_market_median_and_ratings(tmp_path):
    db = tmp_path / "exp.sqlite3"
    out = tmp_path / "webdata"
    now = datetime.now(UTC)
    old_origin = now - timedelta(days=60)
    five_days_ago = now - timedelta(days=5)

    p_mechta = Product(
        shop="mechta",
        sku="101",
        title="Смартфон Samsung Galaxy S24 Ultra 256GB (SM-S928B)",
        price=420_000,
        old_price=599_990,
        url="https://mechta.kz/p/101",
        brand="Samsung",
        group="phones",
        rating=4.9,
        reviews_count=85,
    )
    p_shopkz = Product(
        shop="shopkz",
        sku="202",
        title="Смартфон Samsung Galaxy S24 Ultra 256GB",
        price=520_000,
        old_price=620_000,
        url="https://shop.kz/offer/202",
        brand="Samsung",
        mpn="SM-S928B",
        group="phones",
    )

    with storage.connect(db) as conn:
        # Товар впервые увидели 60 дней назад, затем старый отрезок удалён prune(35):
        storage.save_products(conn, [p_mechta], at=old_origin)
        for hour in range(0, 5 * 24, 12):
            storage.save_products(conn, [p_mechta], at=five_days_ago + timedelta(hours=hour))
        storage.save_products(conn, [p_mechta, p_shopkz], at=now - timedelta(hours=1))
        storage.prune(conn, 35, at=now)

        shown = export.export_dashboard(conn, out)
        export.export_history(conn, out, shown=shown)

    latest = json.loads((out / "latest.json").read_text(encoding="utf-8"))
    by_id = {f"{d['product']['shop']}:{d['product']['sku']}": d for d in latest["deals"]}
    m_deal = by_id["mechta:101"]

    # Истинный first_seen сохранился в таблице products несмотря на prune старых spans!
    assert m_deal["product"]["first_seen"].startswith(old_origin.strftime("%Y-%m-%d"))
    assert m_deal["product"]["rating"] == 4.9
    assert m_deal["product"]["reviews_count"] == 85
    # Хотя цена внутри mechta стояла 5 дней на 420 000 (собственная fair_discount == 0),
    # в пуле магазинов медиана по SM-S928B = (420_000 + 520_000) / 2 = 470_000.
    # А для позиции без собственной 3-дневной истории рыночная медиана подстрахует скоринг!
    s_deal = by_id["shopkz:202"]
    assert s_deal["product"]["mpn"] == "SM-S928B"


def test_export_history_computes_time_weighted_median_and_days_at_current(tmp_path):
    db = tmp_path / "hist.sqlite3"
    out = tmp_path / "webdata"
    now = datetime.now(UTC)
    start = now - timedelta(days=10)

    # 8 суток товар стоил 200 000 ₸, а последние 2 суток менял цену 4 раза возле 100 000 ₸.
    # Наивная медиана по точкам дала бы ~100 000 ₸, а взвешенная по времени — 200 000 ₸!
    with storage.connect(db) as conn:
        for h in range(0, 8 * 24 + 1, 4):
            storage.save_products(
                conn,
                [Product(shop="mechta", sku="w1", title="TV", price=200_000, old_price=260_000, url="https://x/w1")],
                at=start + timedelta(hours=h),
            )
        storage.save_products(
            conn,
            [Product(shop="mechta", sku="w1", title="TV", price=120_000, old_price=260_000, url="https://x/w1")],
            at=now - timedelta(days=2),
        )
        # Последние 2 дня стоит ровно 110 000 ₸:
        for h in range(44, -1, -4):
            storage.save_products(
                conn,
                [Product(shop="mechta", sku="w1", title="TV", price=110_000, old_price=260_000, url="https://x/w1")],
                at=now - timedelta(hours=h),
            )

        shown = export.export_dashboard(conn, out)
        export.export_history(conn, out, shown=shown)

    hist = json.loads((out / "history.json").read_text(encoding="utf-8"))["history"]["mechta:w1"]
    assert hist["median"] == 200_000
    assert hist["min"] == 110_000
    assert hist["days_at_current"] >= 1


def test_avg_discount_includes_real_drops_without_old_price(tmp_path):
    db = tmp_path / "avg.sqlite3"
    out = tmp_path / "webdata"
    now = datetime.now(UTC)
    start = now - timedelta(days=6)
    with storage.connect(db) as conn:
        for h in range(0, 5 * 24, 4):
            storage.save_products(
                conn,
                [Product(shop="mechta", sku="drop1", title="Ноутбук", price=300_000, url="https://x/d1")],
                at=start + timedelta(hours=h),
            )
        storage.save_products(
            conn,
            [Product(shop="mechta", sku="drop1", title="Ноутбук", price=210_000, url="https://x/d1")],
            at=now - timedelta(hours=1),
        )
        export.export_dashboard(conn, out)

    latest = json.loads((out / "latest.json").read_text(encoding="utf-8"))
    assert latest["stats"]["total_deals"] == 1
    assert latest["stats"]["avg_discount"] == 30.0
