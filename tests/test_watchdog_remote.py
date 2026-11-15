from datetime import UTC, datetime, timedelta

import httpx

from skidki import crawler, storage
from skidki.config import Rules, Settings
from skidki.models import Product


class FakeNotifier:
    confirms_delivery = False

    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, text, buttons=None):
        self.sent.append(text)


def test_watchdog_checks_remote_local_snapshot_for_mechta(tmp_path, monkeypatch):
    db = tmp_path / "wd.sqlite3"
    now = datetime.now(UTC)
    with storage.connect(db) as conn:
        storage.record_crawl(conn, "evrika", 3_000, True, None, now - timedelta(hours=1))

    stale_crawl = (now - timedelta(hours=11)).isoformat(timespec="seconds")

    def fake_get(url, **kwargs):
        payload = {
            "updated_at": stale_crawl,
            "shops": [{"name": "mechta", "last_crawl": stale_crawl, "item_count": 7500, "status": "ok"}],
            "deals": [],
            "stats": {"total_products": 7500, "total_deals": 0, "avg_discount": 0},
        }
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(httpx, "get", fake_get)
    notifier = FakeNotifier()
    alerted = crawler.send_watchdog(
        notifier,
        max_age_hours=6.0,
        shops=["evrika"],
        db_path=db,
        remote_url="https://example.github.io/skidki/data/local/latest.json",
        remote_shops=["mechta"],
    )
    assert alerted is True
    assert len(notifier.sent) == 1
    assert "Мечта" in notifier.sent[0]


def test_run_once_imports_remote_prefs_before_evaluating_and_filtering_muted(tmp_path, monkeypatch):
    db = tmp_path / "cloud_sync.sqlite3"

    def fake_get(url, **kwargs):
        return httpx.Response(
            200,
            json={
                "muted": ["tv"],
                "watches": [{"id": 1, "query": "PlayStation 5", "max_price": 260_000, "shop": None, "created_at": "2026-11-12T00:00:00Z"}],
            },
        )

    async def fake_collect(shops, config):
        return [
            (
                "shopkz",
                [
                    Product(shop="shopkz", sku="ps5", title="Игровая приставка Sony PlayStation 5 Slim", price=249_990, url="https://shop.kz/ps5", group="other"),
                    Product(shop="shopkz", sku="tv1", title="Телевизор LG OLED55", price=400_000, old_price=600_000, url="https://shop.kz/tv1", group="tv"),
                ],
                None,
            )
        ]

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(crawler, "collect", fake_collect)
    monkeypatch.setattr(crawler, "load_rules", lambda: Rules())

    notifier = FakeNotifier()
    cfg = Settings(prefs_url="https://example.github.io/skidki/data/local/prefs.json")
    count = crawler.run_once(notifier, shops=["shopkz"], config=cfg, db_path=db)
    assert count >= 1
    assert len(notifier.sent) == 1
    # PS5 по watch попала в сводку, а выключенная группа tv отфильтрована!
    assert "PlayStation 5" in notifier.sent[0]
    assert "OLED55" not in notifier.sent[0]
