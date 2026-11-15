from datetime import datetime, timezone

from skidki import bot, crawler, storage
from skidki.config import Rules, Thresholds
from skidki.evaluate import Signal
from skidki.models import Product

OWNER = "366256716"


class FakeApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def call(self, method, http_timeout=None, **params):
        self.calls.append((method, params))
        return {"ok": True, "result": []}


def _msg(text: str, chat: str = OWNER) -> dict:
    return {"update_id": 10, "message": {"message_id": 11, "chat": {"id": int(chat)}, "text": text}}


def _cb(data: str, chat: str = OWNER) -> dict:
    return {
        "update_id": 11,
        "callback_query": {"id": "cb1", "data": data, "message": {"message_id": 12, "chat": {"id": int(chat)}}},
    }


def test_bot_search_finds_in_stock_products_sorted_by_price(tmp_path):
    db = tmp_path / "bot.sqlite3"
    t0 = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)
    with storage.connect(db) as conn:
        storage.save_products(
            conn,
            [
                Product(shop="shopkz", sku="1", title="Смартфон Apple iPhone 16 128GB", price=489_990, url="https://shop.kz/1"),
                Product(shop="mechta", sku="2", title="Смартфон Apple iPhone 16 128GB Black", price=459_990, old_price=529_990, url="https://mechta.kz/2"),
                Product(shop="alser", sku="3", title="Чехол Samsung S24", price=5_990, url="https://alser.kz/3"),
            ],
            at=t0,
        )

    api = FakeApi()
    bot.handle(_msg("/search iphone 16"), api, OWNER, db)
    assert len(api.calls) == 1
    method, params = api.calls[0]
    assert method == "sendMessage"
    # Сначала более дешёвое предложение (459 990 ₸ в Мечте), затем 489 990 ₸
    assert params["text"].index("459 990") < params["text"].index("489 990")


def test_bot_watch_lifecycle_and_crawler_target_signal(tmp_path):
    db = tmp_path / "watch.sqlite3"
    api = FakeApi()

    # Создание подписки с сокращением «470к»
    bot.handle(_msg("/watch iPhone 16 470к"), api, OWNER, db)
    assert "Подписка" in api.calls[-1][1]["text"]

    # Просмотр списка подписок и inline-кнопка удаления
    bot.handle(_msg("/watches"), api, OWNER, db)
    watches_msg = api.calls[-1][1]
    assert "iPhone 16" in watches_msg["text"]
    cb_data = watches_msg["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    assert cb_data.startswith("unwatch:")

    # Проверка срабатывания Signal.TARGET при обходе
    t0 = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
    with storage.connect(db) as conn:
        findings, _ = crawler.process(
            conn,
            [("mechta", [Product(shop="mechta", sku="99", title="Смартфон Apple iPhone 16 128GB", price=459_990, url="https://mechta.kz/99")], None)],
            Rules(),
            Thresholds(),
            at=t0,
        )
    assert len(findings) == 1
    assert findings[0].has(Signal.TARGET)
    assert findings[0].hit(Signal.TARGET).target == 470_000

    # Удаление подписки кнопкой unwatch:<id>
    bot.handle(_cb(cb_data), api, OWNER, db)
    with storage.connect(db) as conn:
        assert storage.list_watches(conn) == []


def test_prefs_export_and_import_syncs_muted_and_watches(tmp_path):
    db_local = tmp_path / "local.sqlite3"
    db_cloud = tmp_path / "cloud.sqlite3"
    with storage.connect(db_local) as conn:
        storage.toggle_group(conn, "tv")
        storage.toggle_group(conn, "beauty")
        storage.add_watch(conn, "Galaxy S24 Ultra", 480_000)
        payload = storage.export_prefs(conn)

    with storage.connect(db_cloud) as conn:
        storage.toggle_group(conn, "phones")  # старая настройка в облаке должна замениться
        storage.import_prefs(conn, payload)
        assert storage.muted_groups(conn) == {"tv", "beauty"}
        watches = storage.list_watches(conn)
        assert len(watches) == 1
        assert watches[0].query == "Galaxy S24 Ultra"
        assert watches[0].max_price == 480_000
