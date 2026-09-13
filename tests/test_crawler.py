import asyncio
from datetime import timedelta

import pytest
from conftest import T0, product, seed

from skidki import crawler, storage
from skidki.config import Rules, Thresholds
from skidki.models import PartialCrawl

TH = Thresholds()


def test_process_finds_drop_once(conn):
    seed(conn, product(100_000), hours=5 * 24)
    at = T0 + timedelta(days=5, hours=2)
    findings, breakages = crawler.process(conn, [("mechta", [product(90_000)], None)], Rules(), TH, at)
    assert len(findings) == 1 and breakages == []
    storage.record_alert(conn, "mechta:1", "упало", 90_000, at)
    storage.mark_alerts_delivered(conn, ["mechta:1"], at)
    again, _ = crawler.process(
        conn, [("mechta", [product(90_000)], None)], Rules(), TH, at + timedelta(hours=2)
    )
    assert again == []


def test_breakage_alerts_once_per_outage(conn):
    storage.record_crawl(conn, "evrika", 5_000, True, None, T0)
    _, first = crawler.process(conn, [("evrika", [], "TimeoutError")], Rules(), TH, T0 + timedelta(hours=2))
    _, second = crawler.process(conn, [("evrika", [], "TimeoutError")], Rules(), TH, T0 + timedelta(hours=4))
    assert len(first) == 1 and second == []


def test_collapse_in_item_count_is_breakage(conn):
    storage.record_crawl(conn, "mechta", 100, True, None, T0)
    items = [product(1_000 * i, sku=str(i)) for i in range(1, 11)]
    _, breakages = crawler.process(conn, [("mechta", items, None)], Rules(), TH, T0 + timedelta(hours=2))
    assert len(breakages) == 1


class FakeNotifier:
    confirms_delivery = True

    def __init__(self, fail: bool = False) -> None:
        self.sent: list[str] = []
        self.buttons: list = []
        self.fail = fail

    def send(self, text, buttons=None):
        if self.fail:
            raise RuntimeError("telegram down")
        self.sent.append(text)
        self.buttons.append(buttons)


def test_run_once_resends_after_telegram_failure(tmp_path, monkeypatch):
    db = tmp_path / "db.sqlite3"
    with storage.connect(db) as conn:
        start = storage.now() - timedelta(days=5, hours=2)
        seed(conn, product(100_000), hours=5 * 24, start=start)

    async def fake_collect(shops, config):
        return [("mechta", [product(90_000)], None)]

    monkeypatch.setattr(crawler, "collect", fake_collect)
    monkeypatch.setattr(crawler, "load_rules", lambda: Rules())

    with pytest.raises(RuntimeError):
        crawler.run_once(FakeNotifier(fail=True), shops=["mechta"], db_path=db)

    delivered = FakeNotifier()
    assert crawler.run_once(delivered, shops=["mechta"], db_path=db) == 1
    assert len(delivered.sent) == 1 and "90 000 ₸" in delivered.sent[0]
    assert delivered.buttons[0] == [[("🛒 Открыть в Мечте", "https://www.mechta.kz/product/1/")]]

    repeat = FakeNotifier()
    crawler.run_once(repeat, shops=["mechta"], db_path=db)
    assert repeat.sent == []


def test_cards_beyond_limit_get_a_summary(tmp_path, monkeypatch):
    db = tmp_path / "db.sqlite3"
    items = [product(75_000 - i * 1_000, sku=str(i), old_price=100_000) for i in range(10)]
    with storage.connect(db) as conn:
        # Прошлый обход без скидок — это база, а не холодный старт.
        crawler.process(conn, [("mechta", [product(100_000, sku=str(i)) for i in range(10)], None)],
                        Rules(), TH, storage.now() - timedelta(hours=2))

    async def fake_collect(shops, config):
        return [("mechta", items, None)]

    monkeypatch.setattr(crawler, "collect", fake_collect)
    monkeypatch.setattr(crawler, "load_rules", lambda: Rules())
    notifier = FakeNotifier()
    assert crawler.run_once(notifier, shops=["mechta"], db_path=db) == 10
    assert len(notifier.sent) == 9  # 8 карточек + «и ещё 2 находки»
    assert "ещё 2 находки" in notifier.sent[-1]
    assert all(b for b in notifier.buttons[:8])


def test_sample_sends_cards_from_db(tmp_path, monkeypatch):
    db = tmp_path / "db.sqlite3"
    with storage.connect(db) as conn:
        storage.save_products(conn, [product(60_000, old_price=100_000)], T0)
    monkeypatch.setattr(crawler, "load_rules", lambda: Rules())
    notifier = FakeNotifier()
    assert crawler.send_sample(notifier, db_path=db) == 1
    assert "Пример оформления" in notifier.sent[0]
    assert notifier.sent[1].startswith("🏷 <b>Скидка −40%</b>")


def test_fetch_shop_keeps_partial_products(monkeypatch):
    class HalfBroken:
        @staticmethod
        async def fetch(context, config):
            raise PartialCrawl([product(1_000)], "не загрузились разделы: tv-audio-video")

    monkeypatch.setitem(crawler.REGISTRY, "half", HalfBroken)
    name, products, error = asyncio.run(crawler._fetch_shop(None, "half", None))
    assert name == "half" and len(products) == 1
    assert error == "не загрузились разделы: tv-audio-video"


def test_partial_crawl_saves_products_and_alerts(conn):
    storage.record_crawl(conn, "mechta", 7_000, True, None, T0)
    items = [product(1_000 * i, sku=str(i)) for i in range(1, 51)]
    results = [("mechta", items, "не загрузились разделы: tv-audio-video")]
    _, breakages = crawler.process(conn, results, Rules(), TH, T0 + timedelta(hours=2))
    assert len(breakages) == 1 and "tv-audio-video" in breakages[0]
    assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 50
    assert storage.last_crawl_ok(conn, "mechta") is False
