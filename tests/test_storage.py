from datetime import timedelta

from conftest import T0, product, seed

from skidki import storage

ID = "mechta:1"


def test_same_price_extends_one_span(conn):
    seed(conn, product(100_000), hours=24)
    spans = storage.history(conn, ID, T0 - timedelta(days=1))
    assert len(spans) == 1
    assert spans[0].first_seen == T0
    assert spans[0].last_seen == T0 + timedelta(hours=24)


def test_price_change_starts_new_span(conn):
    storage.save_products(conn, [product(100_000)], T0)
    storage.save_products(conn, [product(90_000)], T0 + timedelta(hours=2))
    assert [span.price for span in storage.history(conn, ID, T0)] == [100_000, 90_000]


def test_stock_change_starts_new_span(conn):
    storage.save_products(conn, [product(100_000)], T0)
    storage.save_products(conn, [product(100_000, in_stock=False)], T0 + timedelta(hours=2))
    spans = storage.history(conn, ID, T0)
    assert [span.in_stock for span in spans] == [True, False]


def test_gap_in_observations_starts_new_span(conn):
    storage.save_products(conn, [product(100_000)], T0)
    storage.save_products(conn, [product(100_000)], T0 + timedelta(hours=10))
    assert len(storage.history(conn, ID, T0)) == 2


def test_prune_drops_old_history_and_alerts(conn):
    storage.save_products(conn, [product(100_000)], T0)
    storage.record_alert(conn, ID, "упало", 100_000, T0)
    removed = storage.prune(conn, days=30, at=T0 + timedelta(days=31))
    assert removed == 1
    assert storage.history(conn, ID, T0 - timedelta(days=1)) == []
    assert conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0] == 0


def test_last_alert_counts_only_delivered_and_fresh(conn):
    storage.record_alert(conn, ID, "упало", 90_000, T0)
    assert storage.last_alert(conn, ID, T0 - timedelta(days=1)) is None
    storage.mark_alerts_delivered(conn, [ID], T0)
    assert storage.last_alert(conn, ID, T0 - timedelta(days=1)) == 90_000
    # Алерт старше окна дедупликацию не держит.
    assert storage.last_alert(conn, ID, T0 + timedelta(days=1)) is None
