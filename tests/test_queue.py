"""Очередь находок, выключенные группы и защита от «мигающих» скидок."""

import re
from datetime import timedelta

import pytest
from conftest import T0, product

from skidki import crawler, storage
from skidki.config import Rules, Settings, Thresholds
from skidki.evaluate import Signal, evaluate

TH = Thresholds()


def deal(price: int, sku: str = "1", **kwargs):
    return product(price, sku=sku, old_price=100_000, **kwargs)


# 12 новых скидок: −25% … −36%, самые глубокие — у старших sku.
# sku 0–5 — смартфоны, 6–11 — ТВ.
DEALS = [
    deal(75_000 - i * 1_000, sku=str(i), group="phones" if i < 6 else "tv") for i in range(12)
]


class Notifier:
    confirms_delivery = True

    def __init__(self, fail: bool = False) -> None:
        self.texts: list[str] = []
        self.urls: list[str] = []
        self.fail = fail

    def send(self, text, buttons=None):
        if self.fail:
            raise RuntimeError("telegram down")
        self.texts.append(text)
        self.urls += re.findall(r'href="([^"]+)"', text)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "db.sqlite3"
    # Прошлый обход без скидок — это база, а не холодный старт.
    baseline = [product(100_000, sku=str(i)) for i in range(12)]
    with storage.connect(path) as conn:
        crawler.process(conn, [("mechta", baseline, None)], Rules(), TH,
                        storage.now() - timedelta(hours=2))
    return path


def _run(db, monkeypatch, items, notifier, limit: int = 8) -> int:
    async def fake_collect(shops, config):
        return [("mechta", items, None)]

    monkeypatch.setattr(crawler, "collect", fake_collect)
    monkeypatch.setattr(crawler, "load_rules", lambda: Rules())
    config = Settings(thresholds=Thresholds(max_alerts=limit))
    return crawler.run_once(notifier, shops=["mechta"], config=config, db_path=db)


def _sku(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[1]


def test_flapping_deal_is_not_news_again(conn):
    storage.save_products(conn, [deal(75_000)], T0)
    storage.save_products(conn, [product(100_000)], T0 + timedelta(hours=2))  # скидку сняли
    verdict = evaluate(conn, deal(75_000), Rules(), TH, at=T0 + timedelta(hours=4))
    assert not verdict.has(Signal.DEAL)


def test_deeper_than_any_recent_deal_is_news(conn):
    storage.save_products(conn, [deal(75_000)], T0)
    storage.save_products(conn, [product(100_000)], T0 + timedelta(hours=2))
    assert evaluate(conn, deal(70_000), Rules(), TH, at=T0 + timedelta(hours=4)).has(Signal.DEAL)


def test_one_digest_per_crawl_and_rest_next_time(db, monkeypatch):
    first = Notifier()
    assert _run(db, monkeypatch, DEALS, first) == 12
    assert len(first.texts) == 1  # одна сводка, а не 8 сообщений
    assert len(first.urls) == 8 and "ещё 4 находки" in first.texts[0]
    assert sorted(map(_sku, first.urls)) == sorted(str(i) for i in range(4, 12))

    second = Notifier()
    assert _run(db, monkeypatch, DEALS, second) == 0  # новых нет — только очередь
    assert sorted(map(_sku, second.urls)) == ["0", "1", "2", "3"]
    assert "ещё" not in second.texts[0]

    third = Notifier()
    _run(db, monkeypatch, DEALS, third)
    assert third.texts == []


def test_queue_drops_items_that_lost_the_deal_or_sold_out(db, monkeypatch):
    _run(db, monkeypatch, DEALS, Notifier())  # показаны sku 4–11, в очереди 0–3
    changed = list(DEALS)
    changed[0] = product(100_000, sku="0")                                 # скидку сняли
    changed[1] = deal(74_000, sku="1", in_stock=False, group="phones")     # закончился
    second = Notifier()
    _run(db, monkeypatch, changed, second)
    assert sorted(map(_sku, second.urls)) == ["2", "3"]


def test_queue_expires_after_a_day(db, monkeypatch):
    _run(db, monkeypatch, DEALS, Notifier())
    with storage.connect(db) as conn:
        stale = storage._iso(storage.now() - timedelta(hours=TH.queue_hours + 1))
        conn.execute("UPDATE queue SET found_at = ?", (stale,))
    second = Notifier()
    _run(db, monkeypatch, DEALS, second)
    assert second.texts == []


def test_telegram_failure_keeps_everything_for_next_crawl(db, monkeypatch):
    with pytest.raises(RuntimeError):
        _run(db, monkeypatch, DEALS, Notifier(fail=True))
    second = Notifier()
    _run(db, monkeypatch, DEALS, second)
    assert len(second.urls) == 8 and "ещё 4 находки" in second.texts[0]


def test_console_dry_run_does_not_consume_queue(db, monkeypatch):
    class Console(Notifier):
        confirms_delivery = False

    _run(db, monkeypatch, DEALS, Console())
    real = Notifier()
    _run(db, monkeypatch, DEALS, real)
    assert len(real.urls) == 8


def test_muted_group_is_not_sent_but_waits(db, monkeypatch):
    with storage.connect(db) as conn:
        storage.toggle_group(conn, "tv")
    first = Notifier()
    _run(db, monkeypatch, DEALS, first, limit=40)
    assert sorted(map(_sku, first.urls)) == ["0", "1", "2", "3", "4", "5"]
    assert "ТВ" not in first.texts[0]

    with storage.connect(db) as conn:
        storage.toggle_group(conn, "tv")  # включили обратно
    second = Notifier()
    _run(db, monkeypatch, DEALS, second, limit=40)
    assert sorted(map(_sku, second.urls)) == sorted(str(i) for i in range(6, 12))
