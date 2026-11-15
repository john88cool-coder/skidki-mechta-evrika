import asyncio
from datetime import timedelta

from conftest import T0, product

from skidki import crawler, storage
from skidki.config import Rules, Settings, Thresholds


def test_collapsed_crawl_marks_crawl_not_ok_and_preserves_baseline(conn):
    storage.record_crawl(conn, "mechta", 100, True, None, T0)
    collapsed = [product(10_000 * i, sku=str(i)) for i in range(1, 11)]  # 10 < 100 * 0.5

    _, breakages_1 = crawler.process(
        conn, [("mechta", collapsed, None)], Rules(), Thresholds(), T0 + timedelta(hours=2)
    )
    assert len(breakages_1) == 1
    assert storage.last_crawl_ok(conn, "mechta") is False
    # Эталон 100 позиций НЕ должен затереться значением 10!
    assert storage.previous_item_count(conn, "mechta") == 100

    # Пока обход остаётся схлопнутым (12 позиций < 100 * 0.5), повторной тревоги нет,
    # и эталон всё ещё 100 (раньше 12 >= 10 * 0.5 молча считалось «нормой»!).
    still_collapsed = [product(10_000 * i, sku=str(i)) for i in range(1, 13)]
    _, breakages_2 = crawler.process(
        conn, [("mechta", still_collapsed, None)], Rules(), Thresholds(), T0 + timedelta(hours=4)
    )
    assert breakages_2 == []
    assert storage.last_crawl_ok(conn, "mechta") is False
    assert storage.previous_item_count(conn, "mechta") == 100


def test_fetch_shop_enforces_per_shop_timeout_and_redacts_bot_token(monkeypatch):
    class HangingShop:
        @staticmethod
        async def fetch(context, config):
            await asyncio.sleep(5)
            return []

    class LeakingShop:
        @staticmethod
        async def fetch(context, config):
            raise RuntimeError("GET https://api.telegram.org/bot123456789:AAH_secretToken-99/sendMessage failed")

    monkeypatch.setitem(crawler.REGISTRY, "hang", HangingShop)
    monkeypatch.setitem(crawler.REGISTRY, "leak", LeakingShop)

    cfg = Settings(shop_timeout_s=0.05)
    name, items, err = asyncio.run(crawler._fetch_shop(None, "hang", cfg))
    assert name == "hang" and items == []
    assert err is not None and "TimeoutError" in err

    _, _, leak_err = asyncio.run(crawler._fetch_shop(None, "leak", cfg))
    assert leak_err is not None
    assert "AAH_secretToken" not in leak_err
    assert "bot<REDACTED>" in leak_err


def test_run_once_skips_compact_when_nothing_pruned(tmp_path, monkeypatch):
    db = tmp_path / "nocompact.sqlite3"
    compact_calls: list[object] = []

    async def fake_collect(shops, config):
        return [("mechta", [product(100_000)], None)]

    class DummyNotifier:
        confirms_delivery = False

        def send(self, text, buttons=None):
            pass

    monkeypatch.setattr(crawler, "collect", fake_collect)
    monkeypatch.setattr(crawler, "load_rules", lambda: Rules())
    monkeypatch.setattr(crawler, "compact", lambda path=None: compact_calls.append(path) or 0)

    crawler.run_once(DummyNotifier(), shops=["mechta"], db_path=db)
    assert compact_calls == []
