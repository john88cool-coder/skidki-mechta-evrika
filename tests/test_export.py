import json
from datetime import timedelta

from conftest import T0, product, seed

from skidki import export, storage


def _export(conn, tmp_path):
    """Срез в tmp_path: тесты не должны писать в web/static/data."""
    out = tmp_path / "data"
    export.export_dashboard(conn, out)
    export.export_history(conn, out)
    return out


def _json(out, name):
    return json.loads((out / name).read_text(encoding="utf-8"))


def test_dashboard_lists_deals_and_shop_status(conn, tmp_path):
    cheap = product(50_000, sku="1", old_price=100_000)  # −50%
    shallow = product(90_000, sku="2", old_price=100_000)  # −10%, ниже порога
    seed(conn, cheap, hours=4)
    seed(conn, shallow, hours=4)

    data = _json(_export(conn, tmp_path), "latest.json")

    assert data["stats"]["total_deals"] == 1
    assert data["stats"]["avg_discount"] == 50
    deal = data["deals"][0]
    assert deal["product"]["sku"] == "1"
    assert deal["drop_pct"] == 50
    assert deal["product"]["title"] == cheap.title


def test_dashboard_shop_status_marks_stale_and_broken(conn, tmp_path):
    storage.record_crawl(conn, "mechta", 1_000, True, None, T0)
    shops = {row["name"]: row for row in _json(_export(conn, tmp_path), "latest.json")["shops"]}

    # Обход был 5 суток назад (T0 фикстуры в прошлом) — магазин «устарел».
    assert shops["mechta"]["item_count"] == 1_000
    assert shops["mechta"]["status"] == "warning"
    # Обхода не было вовсе — «сломан».
    assert shops["evrika"]["status"] == "error"
    assert shops["evrika"]["item_count"] == 0


def test_history_keeps_points_and_stats(conn, tmp_path):
    seed(conn, product(100_000, old_price=200_000), hours=24)
    row = _json(_export(conn, tmp_path), "history.json")["history"]["mechta:1"]

    assert row["min"] == row["median"] == 100_000
    assert row["points"][0]["price"] == 100_000
    assert row["points"][-1]["price"] == 100_000


def test_history_survives_price_change(conn, tmp_path):
    """Точки идут по отрезкам: график должен показать обе цены."""
    storage.save_products(conn, [product(100_000, old_price=200_000)], T0)
    storage.save_products(conn, [product(80_000, old_price=200_000)], T0 + timedelta(hours=2))

    row = _json(_export(conn, tmp_path), "history.json")["history"]["mechta:1"]
    prices = [point["price"] for point in row["points"]]

    assert prices[0] == 100_000 and prices[-1] == 80_000
    assert row["min"] == 80_000


def test_recent_prices_keep_exact_tail_despite_chart_downsampling(conn, tmp_path):
    prices = [100_000 - i * 100 for i in range(125)]
    for i, price in enumerate(prices):
        storage.save_products(conn, [product(price, old_price=200_000)], T0 + timedelta(minutes=i))

    row = _json(_export(conn, tmp_path), "history.json")["history"]["mechta:1"]
    assert [point["price"] for point in row["recent_points"]] == prices[-6:]
    assert "T" in row["recent_points"][-1]["date"]
    assert len(row["points"]) < len(prices)


def test_recent_prices_do_not_pad_short_history(conn, tmp_path):
    seed(conn, product(50_000, old_price=100_000), hours=4)
    row = _json(_export(conn, tmp_path), "history.json")["history"]["mechta:1"]
    assert len(row["recent_points"]) == 1
    assert row["recent_points"][0]["price"] == 50_000
