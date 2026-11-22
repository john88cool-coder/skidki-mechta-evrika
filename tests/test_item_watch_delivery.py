"""Задача 9: доставка личных оповещений по данным опубликованных индексов.

Проверяется наблюдаемое поведение движка доставки: golden-путь цен (ровно два
оповещения), правило выбора стороны (local с last_crawl побеждает — то же,
что в задаче 3), свежесть/устаревание, ошибки сети и отсутствие магазина,
переход «отсутствие → наличие», уникальность события, восстановление после
рестарта, повтор после сбоя отправки и то, что /groups не ждёт сетевых
тайм-аутов обслуживающего цикла. Всё — на fake clock, fake HTTP и FakeApi.
"""

import hashlib
import json
import threading
import time
from datetime import UTC, datetime, timedelta

import httpx

from skidki import bot, item_watch, storage

OWNER = "366256716"
PANEL = "https://panel.example/"
SKU = "A:17"
T0 = datetime(2026, 11, 21, 8, 0, tzinfo=UTC)


class FakeApi:
    """Telegram API с управляемым сбоем sendMessage (fail_first)."""

    def __init__(self, fail_first: int = 0) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.fail_first = fail_first

    def call(self, method, http_timeout=None, **params):
        if method == "sendMessage" and self.fail_first > 0:
            self.fail_first -= 1
            raise httpx.ConnectError("telegram недоступен")
        self.calls.append((method, params))
        return {"ok": True, "result": []}

    @property
    def messages(self) -> list[dict]:
        return [params for method, params in self.calls if method == "sendMessage"]


class Clock:
    def __init__(self, start: datetime) -> None:
        self.moment = start

    def __call__(self) -> datetime:
        return self.moment

    def advance(self, **kwargs) -> None:
        self.moment += timedelta(**kwargs)


def _z(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _row(sku: str, price: int, *, in_stock: bool = True) -> dict:
    return {
        "product": {
            "shop": "ignored",
            "sku": sku,
            "title": "Demo Phone",
            "price": price,
            "url": f"https://shop.example/{sku}",
            "in_stock": in_stock,
        },
        "last_seen": None,
        "base_price": None,
        "fair_discount": None,
        "pump_price": None,
        "exact_model": None,
    }


def _manifest(shops: dict) -> bytes:
    return json.dumps({"schema": 2, "shops": shops}, separators=(",", ":")).encode("utf-8")


class FakePanel:
    """Fake HTTP: фиксированный корень панели, манифесты обеих сторон и индексы."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.index_bodies: dict[tuple[str, str], bytes] = {}
        self.entries: dict[str, dict[str, dict]] = {"cloud": {}, "local": {}}
        self.fail_urls: set[str] = set()
        self.requests: list[str] = []
        self.entered = threading.Event()
        self.block: threading.Event | None = None

    def put_price(self, shop: str, sku: str, price: int, *, side: str = "cloud",
                  in_stock: bool = True, last_crawl: datetime | None = None) -> None:
        body = json.dumps(
            {"schema": 2, "shop": shop, "rows": [_row(sku, price, in_stock=in_stock)]},
            ensure_ascii=False,
        ).encode("utf-8")
        self.index_bodies[(side, shop)] = body
        self.entries[side][shop] = {
            "last_crawl": _z(last_crawl or self.clock()),
            "count": 1,
            "index_sha256": hashlib.sha256(body).hexdigest(),
            "history_sha256": hashlib.sha256(b"").hexdigest(),
            "quality": {},
        }

    def drop(self, shop: str, side: str = "cloud") -> None:
        self.entries[side].pop(shop, None)
        self.index_bodies.pop((side, shop), None)

    def __call__(self, url: str) -> bytes | None:
        self.requests.append(url)
        if self.block is not None:
            self.entered.set()
            self.block.wait(10)
        if url in self.fail_urls:
            raise httpx.ConnectError("сеть недоступна")
        if url == PANEL + "data/catalog-v2/manifest.json":
            return _manifest(self.entries["cloud"])
        if url == PANEL + "data/local/catalog-v2/manifest.json":
            return _manifest(self.entries["local"])
        prefix = PANEL + "data/"
        if url.startswith(prefix + "local/catalog-v2/"):
            side, rest = "local", url[len(prefix) + len("local/catalog-v2/"):]
        elif url.startswith(prefix + "catalog-v2/"):
            side, rest = "cloud", url[len(prefix) + len("catalog-v2/"):]
        else:
            return None
        shop, _, name = rest.partition("/")
        if name != "index.json":
            return None
        return self.index_bodies.get((side, shop))


def make_reader(panel: FakePanel) -> item_watch.PublicationReader:
    return item_watch.PublicationReader(
        PANEL, http_get=panel, attempts=2, retry_delay=0.0
    )


def _tick(db, panel: FakePanel, clock: Clock, api: FakeApi) -> int:
    return item_watch.maintenance_tick(db, make_reader(panel), api, OWNER, clock=clock)


# ==================== Golden-сценарий ====================


def test_golden_price_path_exactly_two_notifications(tmp_path):
    db = tmp_path / "golden.sqlite3"
    clock = Clock(T0)
    with storage.connect(db) as conn:
        storage.upsert_item_watch(conn, "mechta", SKU, 120_000)
    panel = FakePanel(clock)
    api = FakeApi()
    counts = []
    for price in (125_000, 119_000, 118_000, 123_000, 117_000):
        panel.put_price("mechta", SKU, price, side="local")
        clock.advance(hours=2)
        _tick(db, panel, clock, api)
        counts.append(len(api.messages))
    assert counts == [0, 1, 1, 1, 2]  # 125k — выше; 119k — цель; 118k — дубликат;
    # 123k — снова выше (разрешает новое оповещение); 117k — второе оповещение
    assert "119 000" in api.messages[0]["text"]
    assert "117 000" in api.messages[1]["text"]
    # повторный тик на той же версии не добавляет сообщений
    _tick(db, panel, clock, api)
    assert len(api.messages) == 2


# ==================== Выбор стороны (правило задачи 3) ====================


def test_local_with_last_crawl_wins_and_cloud_only_shop_visible(tmp_path):
    db = tmp_path / "sides.sqlite3"
    clock = Clock(T0)
    with storage.connect(db) as conn:
        storage.upsert_item_watch(conn, "mechta", SKU, 120_000)
        storage.upsert_item_watch(conn, "shopkz", "77", 120_000)
    panel = FakePanel(clock)
    # Облако обновило mechta позже локального среза — но local с last_crawl побеждает.
    panel.put_price("mechta", SKU, 125_000, side="cloud", last_crawl=T0 + timedelta(hours=1))
    panel.put_price("mechta", SKU, 119_000, side="local", last_crawl=T0)
    # shopkz обошлён только в облаке — домашний слушатель видит его без целей в облаке.
    panel.put_price("shopkz", "77", 115_000, side="cloud", last_crawl=T0)
    api = FakeApi()
    _tick(db, panel, clock, api)
    assert len(api.messages) == 2
    texts = [m["text"] for m in api.messages]
    mechta = next(t for t in texts if "A:17" in t)
    shopkz = next(t for t in texts if "77" in t)
    assert "119 000" in mechta and "125 000" not in mechta  # local, а не cloud
    assert "115 000" in shopkz  # cloud-only магазин
    assert any(r.endswith("catalog-v2/shopkz/index.json") for r in panel.requests)


def test_version_switch_processes_new_snapshot_same_version_ignored(tmp_path):
    db = tmp_path / "versions.sqlite3"
    clock = Clock(T0)
    with storage.connect(db) as conn:
        storage.upsert_item_watch(conn, "mechta", SKU, 120_000)
    panel = FakePanel(clock)
    api = FakeApi()
    # v1: цена ниже цели — одно оповещение
    panel.put_price("mechta", SKU, 119_000, side="local")
    _tick(db, panel, clock, api)
    assert len(api.messages) == 1
    # та же версия с тем же содержимым — не дублирует
    _tick(db, panel, clock, api)
    assert len(api.messages) == 1
    # новая версия (новый last_crawl) с той же ценой — тоже без дубля
    clock.advance(hours=2)
    panel.put_price("mechta", SKU, 119_000, side="local")
    _tick(db, panel, clock, api)
    assert len(api.messages) == 1
    # новая версия выше порога — перевзводит, следующая ниже даёт второе
    clock.advance(hours=2)
    panel.put_price("mechta", SKU, 123_000, side="local")
    _tick(db, panel, clock, api)
    clock.advance(hours=2)
    panel.put_price("mechta", SKU, 117_000, side="local")
    _tick(db, panel, clock, api)
    assert len(api.messages) == 2


# ==================== Свежесть и ошибки измерения ====================


def test_stale_shop_is_not_a_measurement(tmp_path):
    db = tmp_path / "stale.sqlite3"
    clock = Clock(T0)
    with storage.connect(db) as conn:
        storage.upsert_item_watch(conn, "mechta", SKU, 120_000)
    panel = FakePanel(clock)
    api = FakeApi()
    # last_crawl старше порога панели (6 часов) — измерения нет, состояние не пишется
    panel.put_price("mechta", SKU, 119_000, side="local", last_crawl=T0 - timedelta(hours=7))
    _tick(db, panel, clock, api)
    assert api.messages == []
    with storage.connect(db) as conn:
        assert storage.get_item_watch_state(conn, "mechta", SKU) is None
    # свежий обход того же товара даёт ровно одно оповещение
    panel.put_price("mechta", SKU, 119_000, side="local", last_crawl=T0)
    _tick(db, panel, clock, api)
    assert len(api.messages) == 1


def test_http_error_unknown_price_absent_shop_do_not_rearm(tmp_path):
    db = tmp_path / "errors.sqlite3"
    clock = Clock(T0)
    with storage.connect(db) as conn:
        storage.upsert_item_watch(conn, "mechta", SKU, 120_000)
    panel = FakePanel(clock)
    api = FakeApi()
    index_url = PANEL + "data/local/catalog-v2/mechta/index.json"

    panel.put_price("mechta", SKU, 119_000, side="local")  # v1: ниже цели
    _tick(db, panel, clock, api)
    assert len(api.messages) == 1

    clock.advance(hours=2)
    panel.fail_urls.add(index_url)  # ошибка HTTP — не измерение
    _tick(db, panel, clock, api)
    panel.fail_urls.clear()

    clock.advance(hours=2)
    panel.put_price("mechta", SKU, 119_000, side="local", in_stock=True)
    panel.index_bodies[("local", "mechta")] = json.dumps(
        {"schema": 2, "shop": "mechta", "rows": []}, separators=(",", ":")
    ).encode("utf-8")  # v: SKU отсутствует в срезе — неизвестная цена
    _tick(db, panel, clock, api)

    clock.advance(hours=2)
    panel.drop("mechta", side="local")  # магазин исчез из манифеста — не измерение
    _tick(db, panel, clock, api)

    # ошибки не считались подорожанием: версия состояния не изменилась
    with storage.connect(db) as conn:
        state = storage.get_item_watch_state(conn, "mechta", SKU)
    assert state.version.startswith("local:")

    clock.advance(hours=2)
    panel.put_price("mechta", SKU, 121_000, side="local", last_crawl=T0 - timedelta(hours=7))
    # устаревшее значение ВЫШЕ порога — тоже не перевзводит
    _tick(db, panel, clock, api)
    clock.advance(hours=2)
    panel.put_price("mechta", SKU, 118_000, side="local")  # всё ещё ниже — без дубля
    _tick(db, panel, clock, api)
    assert len(api.messages) == 1

    clock.advance(hours=2)
    panel.put_price("mechta", SKU, 123_000, side="local")  # достоверное выше — перевзвод
    _tick(db, panel, clock, api)
    clock.advance(hours=2)
    panel.put_price("mechta", SKU, 117_000, side="local")  # второе оповещение
    _tick(db, panel, clock, api)
    assert len(api.messages) == 2


def test_restock_transition_marks_return(tmp_path):
    db = tmp_path / "restock.sqlite3"
    clock = Clock(T0)
    with storage.connect(db) as conn:
        storage.upsert_item_watch(conn, "mechta", SKU, 120_000)
    panel = FakePanel(clock)
    api = FakeApi()
    panel.put_price("mechta", SKU, 119_000, side="local")
    _tick(db, panel, clock, api)
    assert len(api.messages) == 1
    clock.advance(hours=2)
    panel.put_price("mechta", SKU, 119_000, side="local", in_stock=False)  # кончился
    _tick(db, panel, clock, api)
    assert len(api.messages) == 1
    clock.advance(hours=2)
    panel.put_price("mechta", SKU, 118_000, side="local", in_stock=True)  # возврат
    _tick(db, panel, clock, api)
    assert len(api.messages) == 2
    assert "Снова в наличии" in api.messages[1]["text"]
    assert "Цель достигнута" in api.messages[0]["text"]


# ==================== События: уникальность, удаление, рестарт ====================


def test_event_key_is_unique(tmp_path):
    db = tmp_path / "unique.sqlite3"
    with storage.connect(db) as conn:
        watch = storage.upsert_item_watch(conn, "mechta", SKU, 120_000)
        assert storage.record_item_watch_event(conn, watch.id, "local:t1", "price", 119_000, at=T0)
        assert not storage.record_item_watch_event(conn, watch.id, "local:t1", "price", 119_000, at=T0)
        assert storage.record_item_watch_event(conn, watch.id, "local:t1", "restock", 119_000, at=T0)
        assert storage.record_item_watch_event(conn, watch.id, "local:t2", "price", 118_000, at=T0)
        assert len(storage.pending_item_watch_events(conn)) == 3


def test_deleted_watch_stops_delivery_and_drops_pending(tmp_path):
    db = tmp_path / "deleted.sqlite3"
    clock = Clock(T0)
    with storage.connect(db) as conn:
        watch = storage.upsert_item_watch(conn, "mechta", SKU, 120_000)
    panel = FakePanel(clock)
    api = FakeApi()
    panel.put_price("mechta", SKU, 119_000, side="local")
    with storage.connect(db) as conn:
        item_watch.poll_item_watches(conn, make_reader(panel), clock=clock)
        assert len(storage.pending_item_watch_events(conn)) == 1  # событие ждёт доставки
    # цель удалена (unwi:): событие снимается, доставки нет
    with storage.connect(db) as conn:
        assert storage.remove_item_watch(conn, watch.id)
        assert storage.pending_item_watch_events(conn) == []
    with storage.connect(db) as conn:
        item_watch.deliver_item_watch_events(conn, api, OWNER, clock=clock)
    assert api.messages == []


def test_restart_between_event_and_send_delivers_once(tmp_path):
    db = tmp_path / "restart.sqlite3"
    clock = Clock(T0)
    with storage.connect(db) as conn:
        storage.upsert_item_watch(conn, "mechta", SKU, 120_000)
    panel = FakePanel(clock)
    api = FakeApi()
    panel.put_price("mechta", SKU, 119_000, side="local")
    # «краш» после создания события, до отправки: оценка прошла, доставки не было
    with storage.connect(db) as conn:
        item_watch.poll_item_watches(conn, make_reader(panel), clock=clock)
    assert api.messages == []
    with storage.connect(db) as conn:
        assert len(storage.pending_item_watch_events(conn)) == 1
    # рестарт: новый reader и новый api — ожидающее событие доставлено ровно один раз
    _tick(db, panel, clock, api)
    _tick(db, panel, clock, api)
    assert len(api.messages) == 1
    with storage.connect(db) as conn:
        assert storage.pending_item_watch_events(conn) == []


def test_send_failure_keeps_event_for_retry(tmp_path):
    db = tmp_path / "sendfail.sqlite3"
    clock = Clock(T0)
    with storage.connect(db) as conn:
        storage.upsert_item_watch(conn, "mechta", SKU, 120_000)
    panel = FakePanel(clock)
    api = FakeApi(fail_first=1)
    panel.put_price("mechta", SKU, 119_000, side="local")
    _tick(db, panel, clock, api)  # событие создано, отправка упала
    assert api.messages == []
    with storage.connect(db) as conn:
        assert len(storage.pending_item_watch_events(conn)) == 1
    _tick(db, panel, clock, api)  # повтор в следующем тике — доставлено
    assert len(api.messages) == 1
    _tick(db, panel, clock, api)  # и больше не дублируется
    assert len(api.messages) == 1


# ==================== /groups не ждёт сеть; адаптер задачи 8 ====================


def test_groups_answers_while_reader_blocks_on_network(tmp_path):
    db = tmp_path / "groups.sqlite3"
    clock = Clock(T0)
    with storage.connect(db) as conn:
        storage.upsert_item_watch(conn, "mechta", SKU, 120_000)
    panel = FakePanel(clock)
    panel.block = threading.Event()
    api = FakeApi()
    worker = threading.Thread(
        target=lambda: item_watch.maintenance_tick(db, make_reader(panel), api, OWNER, clock=clock)
    )
    worker.start()
    assert panel.entered.wait(5)  # обслуживающий цикл упёрся в сеть
    started = time.monotonic()
    bot.handle({"update_id": 1, "message": {"message_id": 2, "chat": {"id": int(OWNER)}, "text": "/groups"}}, api, OWNER, db)
    elapsed = time.monotonic() - started
    panel.block.set()
    worker.join(timeout=10)
    assert elapsed < 0.5  # /groups ответил, не дожидаясь сетевого тайм-аута
    assert any(method == "sendMessage" for method, _ in api.calls)


def test_reader_lookup_serves_task8_adapter(tmp_path):
    clock = Clock(T0)
    panel = FakePanel(clock)
    panel.put_price("mechta", SKU, 119_000, side="local")
    reader = make_reader(panel)
    product = reader.lookup("mechta", SKU)
    assert product is not None
    assert product.price == 119_000 and product.in_stock
    assert reader.lookup("mechta", "unknown") is None
