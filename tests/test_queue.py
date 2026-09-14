"""Очередь находок и защита от «мигающих» скидок (ночь 2026-09-14)."""

from datetime import timedelta

import pytest
from conftest import T0, product

from skidki import crawler, storage
from skidki.config import Rules, Thresholds
from skidki.evaluate import Signal, evaluate

TH = Thresholds()


def deal(price: int, sku: str = "1", **kwargs):
    return product(price, sku=sku, old_price=100_000, **kwargs)


# 12 новых скидок: −25% … −36%, самые глубокие — у старших sku.
DEALS = [deal(75_000 - i * 1_000, sku=str(i)) for i in range(12)]


class Notifier:
    confirms_delivery = True

    def __init__(self, fail_after: int | None = None) -> None:
        self.texts: list[str] = []
        self.urls: list[str] = []
        self.fail_after = fail_after

    def send(self, text, buttons=None):
        if self.fail_after is not None and len(self.urls) >= self.fail_after and buttons:
            raise RuntimeError("telegram down")
        self.texts.append(text)
        if buttons:
            self.urls.append(buttons[0][0][1])


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "db.sqlite3"
    # Прошлый обход без скидок — это база, а не холодный старт.
    baseline = [product(100_000, sku=str(i)) for i in range(12)]
    with storage.connect(path) as conn:
        crawler.process(conn, [("mechta", baseline, None)], Rules(), TH,
                        storage.now() - timedelta(hours=2))
    return path


def _run(db, monkeypatch, items, notifier) -> int:
    async def fake_collect(shops, config):
        return [("mechta", items, None)]

    monkeypatch.setattr(crawler, "collect", fake_collect)
    monkeypatch.setattr(crawler, "load_rules", lambda: Rules())
    return crawler.run_once(notifier, shops=["mechta"], db_path=db)


def test_flapping_deal_is_not_news_again(conn):
    storage.save_products(conn, [deal(75_000)], T0)
    storage.save_products(conn, [product(100_000)], T0 + timedelta(hours=2))  # скидку сняли
    verdict = evaluate(conn, deal(75_000), Rules(), TH, at=T0 + timedelta(hours=4))
    assert not verdict.has(Signal.DEAL)


def test_deeper_than_any_recent_deal_is_news(conn):
    storage.save_products(conn, [deal(75_000)], T0)
    storage.save_products(conn, [product(100_000)], T0 + timedelta(hours=2))
    assert evaluate(conn, deal(70_000), Rules(), TH, at=T0 + timedelta(hours=4)).has(Signal.DEAL)


def test_findings_beyond_limit_are_shown_next_crawl(db, monkeypatch):
    first = Notifier()
    assert _run(db, monkeypatch, DEALS, first) == 12
    assert len(first.urls) == 8 and "ещё 4 находки" in first.texts[-1]
    # Самые глубокие — первыми.
    assert first.urls[0].endswith("/product/11/")

    second = Notifier()
    assert _run(db, monkeypatch, DEALS, second) == 0  # новых нет — только очередь
    assert len(second.urls) == 4 and not any("ещё" in text for text in second.texts)
    assert not set(first.urls) & set(second.urls)

    third = Notifier()
    _run(db, monkeypatch, DEALS, third)
    assert third.texts == []


def test_queue_drops_items_that_lost_the_deal_or_sold_out(db, monkeypatch):
    _run(db, monkeypatch, DEALS, Notifier())  # показаны sku 11…4, в очереди 0…3
    changed = list(DEALS)
    changed[0] = product(100_000, sku="0")                 # скидку сняли
    changed[1] = deal(74_000, sku="1", in_stock=False)     # закончился
    second = Notifier()
    _run(db, monkeypatch, changed, second)
    assert sorted(second.urls) == ["https://www.mechta.kz/product/2/",
                                   "https://www.mechta.kz/product/3/"]


def test_queue_expires_after_a_day(db, monkeypatch):
    _run(db, monkeypatch, DEALS, Notifier())
    with storage.connect(db) as conn:
        stale = storage._iso(storage.now() - timedelta(hours=TH.queue_hours + 1))
        conn.execute("UPDATE queue SET found_at = ?", (stale,))
    second = Notifier()
    _run(db, monkeypatch, DEALS, second)
    assert second.texts == []


def test_telegram_failure_mid_batch_neither_loses_nor_repeats(db, monkeypatch):
    flaky = Notifier(fail_after=3)
    with pytest.raises(RuntimeError):
        _run(db, monkeypatch, DEALS, flaky)
    assert len(flaky.urls) == 3

    second = Notifier()
    _run(db, monkeypatch, DEALS, second)
    assert len(second.urls) == 8 and "ещё 1 находка" in second.texts[-1]
    assert not set(flaky.urls) & set(second.urls)


def test_console_dry_run_does_not_consume_queue(db, monkeypatch):
    class Console(Notifier):
        confirms_delivery = False

    _run(db, monkeypatch, DEALS, Console())
    real = Notifier()
    _run(db, monkeypatch, DEALS, real)
    assert len(real.urls) == 8
