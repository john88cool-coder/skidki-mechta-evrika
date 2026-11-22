import base64
import json
from datetime import datetime, timezone

from skidki import bot, crawler, item_watch, storage
from skidki.catalog_export import export_catalog
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

    # Регрессия: цена в формате, который печатает сам бот (tenge) — «450 000 ₸»
    api2 = FakeApi()
    bot.handle(_msg("/watch iPhone 16 450 000 ₸"), api2, OWNER, db)
    assert "Подписка" in api2.calls[-1][1]["text"]
    with storage.connect(db) as conn:
        added = storage.list_watches(conn)[-1]
        assert added.query == "iPhone 16"
        assert added.max_price == 450_000


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


# ==================== Точная цель из карточки (задача 8) ====================

# Общие Python↔TS векторы (фронтенд: web/src/lib/utils/watch-link.ts):
# w2_<base64url(UTF8(JSON.stringify([shop, sku, max_price])))> без padding.
V1_PAYLOAD = "w2_WyJtZWNodGEiLCJBOjE3Iiw0NzAwMDBd"  # ["mechta","A:17",470000]
V2_PAYLOAD = "w2_WyJtZWNodGEiLCLQlcyB0LvQutCwLfCfjoQtOSIsMTI5OTBd"  # ["mechta","Е́лка-🎄-9",12990]
V2_SKU = "Е\u0301лка-\U0001F384-9"  # комбинируемое ударение + эмодзи
V3_PAYLOAD = "w2_WyJtZWNodGEiLCJYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYIiw0NzAwMDBd"  # ["mechta","X"*25,470000]


def _raw_payload(json_text: str) -> str:
    """Тестовый кодировщик произвольного JSON — для векторов с невалидными значениями."""
    return "w2_" + base64.urlsafe_b64encode(json_text.encode("utf-8")).rstrip(b"=").decode("ascii")


def _draft_button(api: FakeApi) -> str:
    """callback_data inline-кнопки последнего сообщения."""
    markup = api.calls[-1][1]["reply_markup"]["inline_keyboard"]
    return markup[0][0]["callback_data"]


def test_item_payload_shared_vectors():
    vectors = [
        ("mechta", "A:17", 470_000, V1_PAYLOAD),
        ("mechta", V2_SKU, 12_990, V2_PAYLOAD),
        ("mechta", "X" * 25, 470_000, V3_PAYLOAD),
    ]
    for shop, sku, price, payload in vectors:
        assert item_watch.encode_payload(shop, sku, price) == payload
        target = item_watch.decode_payload(payload)
        assert target == item_watch.ItemTarget(shop=shop, sku=sku, max_price=price)
        assert item_watch.encode_payload(target.shop, target.sku, target.max_price) == payload
    # максимально длинный случай помещается в лимит /start
    assert len(V3_PAYLOAD) == 63
    over = item_watch.encode_payload("mechta", "X" * 26, 470_000)
    assert over and len(over) == 65  # не помещается в start — передаётся командой
    assert item_watch.decode_payload(over) == item_watch.ItemTarget("mechta", "X" * 26, 470_000)


def test_item_payload_rejects_invalid():
    # encode: строгий список магазинов, непустой SKU, безопасная цена 1..999999999
    assert item_watch.encode_payload("kaspi", "1", 100) is None
    assert item_watch.encode_payload("", "1", 100) is None
    assert item_watch.encode_payload("mechta", "", 100) is None
    assert item_watch.encode_payload("mechta", "   ", 100) is None
    assert item_watch.encode_payload("mechta", "A:17", 0) is None
    assert item_watch.encode_payload("mechta", "A:17", -1) is None
    assert item_watch.encode_payload("mechta", "A:17", 1_000_000_000) is None
    assert item_watch.encode_payload("mechta", "A:17", 1.5) is None
    assert item_watch.encode_payload("mechta", "A:17", True) is None
    assert item_watch.decode_payload(item_watch.encode_payload("mechta", "A:17", 999_999_999)).max_price == 999_999_999
    # decode: префикс, алфавит base64url без padding, типы и границы
    assert item_watch.decode_payload("WyJtZWNodGE") is None  # без префикса
    assert item_watch.decode_payload("w1_WyJtZWNodGE") is None
    assert item_watch.decode_payload("w2_") is None
    assert item_watch.decode_payload("w2_WyJtZWNodGE=") is None  # padding запрещён
    assert item_watch.decode_payload("w2_WyJtZWNodG+/") is None  # не base64url-алфавит
    assert item_watch.decode_payload("w2_%%%") is None
    assert item_watch.decode_payload("w2__w") is None  # невалидный UTF-8
    assert item_watch.decode_payload(_raw_payload('{"shop":"mechta"}')) is None  # не массив
    assert item_watch.decode_payload(_raw_payload('["mechta","A:17"]')) is None  # не 3 элемента
    assert item_watch.decode_payload(_raw_payload('["mechta","A:17",1,"x"]')) is None
    assert item_watch.decode_payload(_raw_payload('["kaspi","1",5]')) is None
    assert item_watch.decode_payload(_raw_payload('["Mechta","A:17",5]')) is None
    assert item_watch.decode_payload(_raw_payload('["mechta","",5]')) is None
    assert item_watch.decode_payload(_raw_payload('["mechta","A:17",0]')) is None
    assert item_watch.decode_payload(_raw_payload('["mechta","A:17",1000000000]')) is None
    assert item_watch.decode_payload(_raw_payload('["mechta","A:17",1.5]')) is None
    assert item_watch.decode_payload(_raw_payload('["mechta","A:17",true]')) is None
    assert item_watch.decode_payload(_raw_payload('["mechta","A:17","470000"]')) is None
    assert item_watch.decode_payload(_raw_payload('[1,"A:17",5]')) is None
    # команда /watchitem обязана помещаться в лимит сообщения Telegram
    assert item_watch.encode_payload("mechta", "X" * 5000, 470_000) is None


def test_start_w2_creates_draft_before_generic_start(tmp_path):
    db = tmp_path / "start.sqlite3"
    api = FakeApi()
    bot.handle(_msg("/start " + V1_PAYLOAD), api, OWNER, db)
    assert api.calls[-1][0] == "sendMessage"
    text = api.calls[-1][1]["text"]
    assert "Мечта" in text and "A:17" in text and "470 000" in text
    cb = _draft_button(api)
    assert cb.startswith("wi:")
    with storage.connect(db) as conn:
        drafts = conn.execute(
            "SELECT shop, sku, max_price, created_at, expires_at FROM item_watch_drafts"
        ).fetchall()
        assert len(drafts) == 1
        assert drafts[0]["shop"] == "mechta"
        assert drafts[0]["sku"] == "A:17"
        assert drafts[0]["max_price"] == 470000
        ttl = (
            datetime.fromisoformat(drafts[0]["expires_at"]) - datetime.fromisoformat(drafts[0]["created_at"])
        ).total_seconds()
        assert ttl == 900  # TTL 15 минут
        assert storage.list_item_watches(conn) == []  # ссылка открыта, но цель ещё не подтверждена

    # общий /start (без w2_) ведёт себя как раньше и не создаёт черновиков
    api2 = FakeApi()
    bot.handle(_msg("/start"), api2, OWNER, db)
    assert api2.calls and api2.calls[-1][0] == "sendMessage"
    bot.handle(_msg("/start hello"), api2, OWNER, db)
    assert all("Артикул" not in c[1].get("text", "") for c in api2.calls)
    with storage.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM item_watch_drafts").fetchone()[0] == 1


def test_watchitem_command_same_validation(tmp_path):
    db = tmp_path / "wi.sqlite3"
    api = FakeApi()
    bot.handle(_msg("/watchitem " + V1_PAYLOAD), api, OWNER, db)
    assert "A:17" in api.calls[-1][1]["text"]
    with storage.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM item_watch_drafts").fetchone()[0] == 1

    api2 = FakeApi()
    bot.handle(_msg("/watchitem w2_garbage!!"), api2, OWNER, db)
    assert "разобрать" in api2.calls[-1][1]["text"]
    bot.handle(_msg("/watchitem"), api2, OWNER, db)
    assert "разобрать" in api2.calls[-1][1]["text"]
    with storage.connect(db) as conn:
        # после неверной команды черновик не появился
        assert conn.execute("SELECT COUNT(*) FROM item_watch_drafts").fetchone()[0] == 1


def test_foreign_chat_is_silent(tmp_path):
    db = tmp_path / "foreign.sqlite3"
    api = FakeApi()
    bot.handle(_msg("/start " + V1_PAYLOAD, chat="999"), api, OWNER, db)
    bot.handle(_msg("/watchitem " + V1_PAYLOAD, chat="999"), api, OWNER, db)
    bot.handle(_cb("wi:abcd1234", chat="999"), api, OWNER, db)
    bot.handle(_cb("unwi:1", chat="999"), api, OWNER, db)
    assert api.calls == []


def test_draft_confirm_idempotent_and_threshold_update(tmp_path):
    db = tmp_path / "confirm.sqlite3"
    t0 = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)
    with storage.connect(db) as conn:
        storage.save_products(
            conn,
            [Product(shop="mechta", sku="A:17", title="Demo Phone", price=489_990, url="https://mechta.kz/a17")],
            at=t0,
        )
    api = FakeApi()
    bot.handle(_msg("/watchitem " + V1_PAYLOAD), api, OWNER, db)
    cb = _draft_button(api)
    draft_id = cb.removeprefix("wi:")
    assert len(draft_id) == 8  # короткий случайный ID

    bot.handle(_cb(cb), api, OWNER, db)
    edits = [c for c in api.calls if c[0] == "editMessageText"]
    assert any("сохранена" in c[1]["text"] for c in edits)
    answers = [c for c in api.calls if c[0] == "answerCallbackQuery"]
    assert any("сохранена" in (c[1].get("text") or "") for c in answers)
    with storage.connect(db) as conn:
        items = storage.list_item_watches(conn)
        assert len(items) == 1
        assert items[0].shop == "mechta" and items[0].sku == "A:17" and items[0].max_price == 470000
        assert conn.execute("SELECT COUNT(*) FROM item_watch_drafts").fetchone()[0] == 0

    # двойной callback — идемпотентно: без повторного редактирования и дублей
    before = len(api.calls)
    bot.handle(_cb(cb), api, OWNER, db)
    assert all(c[0] != "editMessageText" for c in api.calls[before:])
    answers2 = [c for c in api.calls[before:] if c[0] == "answerCallbackQuery"]
    assert any("Уже подтверждено" in (c[1].get("text") or "") for c in answers2)
    with storage.connect(db) as conn:
        assert len(storage.list_item_watches(conn)) == 1

    # повторная осознанная установка той же пары обновляет порог
    api2 = FakeApi()
    upd = item_watch.encode_payload("mechta", "A:17", 500_000)
    assert upd
    bot.handle(_msg("/watchitem " + upd), api2, OWNER, db)
    bot.handle(_cb(_draft_button(api2)), api2, OWNER, db)
    with storage.connect(db) as conn:
        items = storage.list_item_watches(conn)
        assert len(items) == 1 and items[0].max_price == 500_000


def test_draft_expired_shows_reason_and_no_watch(tmp_path):
    db = tmp_path / "expired.sqlite3"
    past = datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc)
    with storage.connect(db) as conn:
        draft = storage.create_item_watch_draft(conn, "mechta", "A:17", 470_000, at=past)
    api = FakeApi()
    bot.handle(_cb("wi:" + draft.id), api, OWNER, db)
    edits = [c for c in api.calls if c[0] == "editMessageText"]
    assert any("истёк" in c[1]["text"] for c in edits)
    assert any("повторите" in c[1]["text"].lower() for c in edits)
    with storage.connect(db) as conn:
        assert storage.list_item_watches(conn) == []
        assert storage.get_item_watch_draft(conn, draft.id) is None  # истёкший удалён


def test_confirm_without_local_product_keeps_draft_for_retry(tmp_path):
    db = tmp_path / "empty.sqlite3"
    api = FakeApi()
    bot.handle(_msg("/watchitem " + V1_PAYLOAD), api, OWNER, db)
    cb = _draft_button(api)
    bot.handle(_cb(cb), api, OWNER, db)
    edits = [c for c in api.calls if c[0] == "editMessageText"]
    assert any("не удалось найти" in c[1]["text"] for c in edits)
    assert any(
        btn["callback_data"] == cb and "Повторить" in btn["text"]
        for c in edits
        for row in c[1]["reply_markup"]["inline_keyboard"]
        for btn in row
    )
    draft_id = cb.removeprefix("wi:")
    with storage.connect(db) as conn:
        assert storage.list_item_watches(conn) == []
        assert storage.get_item_watch_draft(conn, draft_id) is not None  # черновик жив для повтора

    # товар появился — тот же callback подтверждает цель
    t0 = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)
    with storage.connect(db) as conn:
        storage.record_crawl(conn, "mechta", 1, True, at=t0)
        storage.save_products(
            conn,
            [Product(shop="mechta", sku="A:17", title="Demo Phone", price=489_990, url="https://mechta.kz/a17")],
            at=t0,
        )
    bot.handle(_cb(cb), api, OWNER, db)
    with storage.connect(db) as conn:
        items = storage.list_item_watches(conn)
        assert len(items) == 1 and items[0].max_price == 470000


def test_confirm_via_adapter_lookup(tmp_path):
    db = tmp_path / "adapter.sqlite3"
    api = FakeApi()

    class FakeLookup:
        def __init__(self) -> None:
            self.calls = []

        def lookup(self, shop, sku):
            self.calls.append((shop, sku))
            return Product(shop=shop, sku=sku, title="Из индекса магазина", price=470_000, url="https://mechta.kz/x")

    lookup = FakeLookup()
    bot.handle(_msg("/watchitem " + V1_PAYLOAD), api, OWNER, db)
    cb = _draft_button(api)
    bot.handle(_cb(cb), api, OWNER, db, item_lookup=lookup)
    assert lookup.calls == [("mechta", "A:17")]  # обращение только к источнику выбранного магазина
    edits = [c for c in api.calls if c[0] == "editMessageText"]
    assert any("сохранена" in c[1]["text"] for c in edits)
    with storage.connect(db) as conn:
        items = storage.list_item_watches(conn)
        assert len(items) == 1 and items[0].sku == "A:17"


def test_adapter_failure_keeps_draft_and_shows_reason(tmp_path):
    db = tmp_path / "adapter_fail.sqlite3"
    api = FakeApi()

    class BoomLookup:
        def lookup(self, shop, sku):
            raise RuntimeError("источник недоступен")

    bot.handle(_msg("/watchitem " + V1_PAYLOAD), api, OWNER, db)
    cb = _draft_button(api)
    bot.handle(_cb(cb), api, OWNER, db, item_lookup=BoomLookup())
    edits = [c for c in api.calls if c[0] == "editMessageText"]
    assert any("не удалось найти" in c[1]["text"] for c in edits)
    draft_id = cb.removeprefix("wi:")
    with storage.connect(db) as conn:
        assert storage.list_item_watches(conn) == []
        assert storage.get_item_watch_draft(conn, draft_id) is not None


def test_watches_mixed_list_and_item_delete_prefix(tmp_path):
    db = tmp_path / "mixed.sqlite3"
    t0 = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)
    with storage.connect(db) as conn:
        storage.save_products(
            conn,
            [Product(shop="mechta", sku="A:17", title="Demo Phone", price=489_990, url="https://mechta.kz/a17")],
            at=t0,
        )
    api = FakeApi()
    bot.handle(_msg("/watch iPhone 16 450к"), api, OWNER, db)
    bot.handle(_msg("/watchitem " + V1_PAYLOAD), api, OWNER, db)
    bot.handle(_cb(_draft_button(api)), api, OWNER, db)

    bot.handle(_msg("/watches"), api, OWNER, db)
    watches_msg = api.calls[-1][1]
    assert "iPhone 16" in watches_msg["text"]
    assert "A:17" in watches_msg["text"]
    assert "Мечта" in watches_msg["text"]
    datas = [btn["callback_data"] for row in watches_msg["reply_markup"]["inline_keyboard"] for btn in row]
    assert any(d.startswith("unwatch:") for d in datas)  # текстовые цели
    unwi = [d for d in datas if d.startswith("unwi:")]
    assert len(unwi) == 1  # точные цели — свой префикс удаления

    bot.handle(_cb(unwi[0]), api, OWNER, db)
    answers = [c for c in api.calls if c[0] == "answerCallbackQuery"]
    assert any("удалена" in (c[1].get("text") or "") for c in answers)
    with storage.connect(db) as conn:
        assert storage.list_item_watches(conn) == []
        assert [w.query for w in storage.list_watches(conn)] == ["iPhone 16"]  # текстовая осталась


def test_item_watches_not_in_export_prefs_index_manifest(tmp_path):
    db = tmp_path / "local.sqlite3"
    t0 = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)
    stamp = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
    with storage.connect(db) as conn:
        storage.record_crawl(conn, "mechta", 1, True, at=t0)
        storage.save_products(
            conn,
            [Product(shop="mechta", sku="REAL1", title="Real product", price=100_000, url="https://mechta.kz/real1")],
            at=t0,
        )
        storage.toggle_group(conn, "tv")
        storage.add_watch(conn, "Galaxy S24 Ultra", 480_000)
        storage.upsert_item_watch(conn, "mechta", "WATCH-EXACT-777", 777_777, at=stamp)
        storage.create_item_watch_draft(conn, "mechta", "WATCH-EXACT-777", 777_777, at=stamp)
        payload = storage.export_prefs(conn)

    text = json.dumps(payload, ensure_ascii=False)
    assert "WATCH-EXACT-777" not in text
    assert "777777" not in text

    # import_prefs тоже не создаёт точные цели и черновики
    cloud = tmp_path / "cloud.sqlite3"
    with storage.connect(cloud) as conn:
        storage.import_prefs(conn, payload)
        assert storage.list_item_watches(conn) == []
        assert conn.execute("SELECT COUNT(*) FROM item_watch_drafts").fetchone()[0] == 0

    # индекс и манифест catalog-v2 собираются из products/spans — цели там нет
    catalog_dir = None
    with storage.connect(db) as conn:
        catalog_dir = export_catalog(conn, tmp_path / "out", at=stamp)
    for path in catalog_dir.rglob("*.json"):
        body = path.read_text(encoding="utf-8")
        assert "WATCH-EXACT-777" not in body
        assert "777777" not in body


def test_legacy_commands_still_work(tmp_path):
    db = tmp_path / "legacy.sqlite3"
    api = FakeApi()
    bot.handle(_msg("/groups"), api, OWNER, db)
    assert api.calls[-1][0] == "sendMessage"
    bot.handle(_msg("/watch iPhone 16 450к"), api, OWNER, db)
    assert "Подписка" in api.calls[-1][1]["text"]
    bot.handle(_msg("/watches"), api, OWNER, db)
    assert "iPhone 16" in api.calls[-1][1]["text"]
