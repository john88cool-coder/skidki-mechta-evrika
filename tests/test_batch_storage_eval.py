import sqlite3
from datetime import datetime, timedelta, timezone

from skidki.config import Rules, Thresholds
from skidki.evaluate import Signal, evaluate, should_send
from skidki.models import Product
from skidki.storage import (
    connect,
    first_seen_map,
    histories_for_shop,
    last_alerts_for_shop,
    last_spans_for_shop,
    mark_alerts_delivered,
    record_alert,
    save_products,
)


class _CountingConn:
    """Считает диспетчи SQL (execute/executemany), а не трейс-события:
    set_trace_callback срабатывает на каждую строку executemany."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self.statements: list[str] = []

    def execute(self, sql, *args):
        self.statements.append(sql)
        return self._conn.execute(sql, *args)

    def executemany(self, sql, *args):
        self.statements.append(sql)
        return self._conn.executemany(sql, *args)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def test_batch_save_products_and_preloaded_evaluate_eliminate_n_plus_one(tmp_path):
    db = tmp_path / "batch.sqlite3"
    t0 = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(days=5)
    t2 = t1 + timedelta(hours=2)

    initial = [
        Product(
            shop="sulpak",
            sku=str(i),
            title=f"Смартфон Model {i}",
            price=100_000,
            old_price=110_000,
            url=f"https://www.sulpak.kz/g/{i}",
            group="phones",
        )
        for i in range(200)
    ]
    dropped = [
        Product(
            shop="sulpak",
            sku=str(i),
            title=f"Смартфон Model {i}",
            price=80_000 if i < 5 else 100_000,
            old_price=120_000 if i < 5 else 110_000,
            url=f"https://www.sulpak.kz/g/{i}",
            group="phones",
        )
        for i in range(200)
    ]

    th = Thresholds()
    rules = Rules()

    with connect(db) as conn:
        save_products(conn, initial, at=t0)
        save_products(conn, initial, at=t1)
        record_alert(conn, "sulpak:0", Signal.DROP.value, 85_000, at=t1)
        mark_alerts_delivered(conn, ["sulpak:0"], at=t1)

        # Считаем число SQL-выражений на пакетном проходе по 200 товарам
        counting = _CountingConn(conn)
        low_since = t2 - timedelta(days=max(th.trend_window_days, th.low_window_days))
        alert_since = t2 - timedelta(days=th.trend_window_days)
        spans_by_id = histories_for_shop(counting, "sulpak", low_since)
        last_by_id = last_spans_for_shop(counting, "sulpak")
        alerts_by_id = last_alerts_for_shop(counting, "sulpak", alert_since)

        batch_hits: list[tuple[str, list[Signal], bool]] = []
        for p in dropped:
            v = evaluate(
                counting,
                p,
                rules,
                th,
                at=t2,
                preloaded_spans=spans_by_id.get(p.identity, []),
                preloaded_last_span=last_by_id.get(p.identity),
            )
            send = should_send(
                counting,
                v,
                th,
                at=t2,
                preloaded_last_alert=alerts_by_id.get(p.identity),
            )
            if v.signals:
                batch_hits.append((p.identity, [s.signal for s in v.signals], send))

        written = save_products(counting, dropped, at=t2)

        assert written == 200
        # Вместо >800 поштучных SELECT/INSERT/UPDATE укладываемся менее чем в 15 выражений!
        # Старый поштучный код на этом же сценарии даёт ~1210 диспетчей SQL
        # (замер до пакета), так что граница <15 срабатывает при любом возврате N+1.
        assert len(counting.statements) < 15

        # Сравниваем с эталонным поштучным вызовом на свежей проверке до записи?
        # Проверим совпадение first_seen_map и результатов сигналов:
        fmap = first_seen_map(conn, ["sulpak:0", "sulpak:199"])
        assert fmap["sulpak:0"].startswith("2026-11-01T10:00:00")
        assert len(batch_hits) == 5
        assert all(Signal.DROP in sigs for _, sigs, _ in batch_hits)
        assert all(send is True for _, _, send in batch_hits)
