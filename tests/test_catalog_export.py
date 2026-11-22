"""Stage 2: каталог и история по магазинам (catalog-v2).

Набор данных для приёмки — tests/fixtures/stage2/expected.json: позиция без
скидки, та же комплектация в других магазинах, одноимённый чехол, выбывший
товар, снятое наличие, одна точка наблюдения, магазин с пустым успехом и
магазин без успешного обхода. Момент фикстуры — UTC 2026-11-21T12:00:00Z,
часы экспортёра заморожены: хеши и вердикты не зависят от времени запуска
тестов, а независимость от времени запуска отдельно проверяется тестом
с явным `at`.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from conftest import FIXTURES

from skidki import catalog_export, export, storage
from skidki.models import Product

ANCHOR = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
SPEC = json.loads((FIXTURES / "stage2" / "expected.json").read_text(encoding="utf-8"))


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _product(rec: dict, price: int, in_stock: bool) -> Product:
    return Product(
        shop=rec["shop"],
        sku=rec["sku"],
        title=rec["title"],
        price=price,
        url=rec["url"],
        brand=rec.get("brand"),
        category=rec.get("category"),
        old_price=rec.get("old_price"),
        in_stock=in_stock,
        mpn=rec.get("mpn"),
    )


def _build_db(tmp_path, extra: list[Product] | None = None) -> Path:
    """Временная БД с набором stage2; `extra` — позиции последнего обхода."""
    db = tmp_path / "stage2.sqlite3"
    with storage.connect(db) as conn:
        for rec in SPEC["products"]:
            for moment, price, in_stock in zip(
                rec["observed"], rec["prices"], rec["in_stock"], strict=True
            ):
                storage.save_products(conn, [_product(rec, price, in_stock)], at=_utc(moment))
        for crawl in SPEC["crawls"]:
            storage.record_crawl(
                conn, crawl["shop"], crawl["item_count"], crawl["ok"], crawl.get("error"), at=_utc(crawl["at"])
            )
        if extra:
            storage.save_products(conn, extra, at=ANCHOR)
    return db


def _export_for_web(db: Path, out: Path, *, moment: datetime = ANCHOR) -> Path:
    """export_for_web с заданным «временем запуска» вместо часов машины:
    разные `moment` имитируют разные запуски экспортёра на одних данных."""
    original = export.datetime

    class _Frozen(original):
        @classmethod
        def now(cls, tz=None):
            return moment if tz is None else moment.astimezone(tz)

    export.datetime = _Frozen
    try:
        return export.export_for_web(db_path=db, out_dir=out)
    finally:
        export.datetime = original


def test_legacy_export_keeps_latest_and_history_cards(tmp_path):
    """Регрессия Stage 1: export_for_web пишет загружаемые latest.json и
    history.json, существующие карточки читаются по паре (shop, sku)."""
    db = _build_db(tmp_path)
    out = _export_for_web(db, tmp_path / "web")

    latest = json.loads((out / "latest.json").read_text(encoding="utf-8"))
    history = json.loads((out / "history.json").read_text(encoding="utf-8"))["history"]

    assert [d["product"]["shop"] for d in latest["deals"]]  # витрина не пуста
    for deal in latest["deals"]:
        identity = f"{deal['product']['shop']}:{deal['product']['sku']}"
        assert history[identity]["points"], identity
    # Реальное снижение доступно карточке: сигнал, база и график на месте.
    drop = next(d for d in latest["deals"] if d["product"]["sku"] == "DROP1")
    assert drop["signal"] == "drop"
    assert drop["base_price"] == 300_000
    assert history["mechta:DROP1"]["min"] == 150_000


def test_export_writes_catalog_v2_manifest(tmp_path):
    """Тот же вызов export_for_web публикует catalog-v2/manifest.json."""
    db = _build_db(tmp_path)
    out = _export_for_web(db, tmp_path / "web")
    assert (out / "catalog-v2" / "manifest.json").is_file()


def test_manifest_lists_successful_shops_with_counts_and_hashes(tmp_path):
    """Запись манифеста — для каждого магазина с успешным обходом: last_crawl,
    число строк и хеши ресурсов; хеши считаются по записанным байтам."""
    db = _build_db(tmp_path)
    out = _export_for_web(db, tmp_path / "web")
    manifest = json.loads((out / "catalog-v2" / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["schema"] == 2
    assert list(manifest["shops"]) == SPEC["expected"]["manifest_shops"]
    for shop, entry in manifest["shops"].items():
        assert entry["last_crawl"] == SPEC["expected"]["last_crawl"]
        body = (out / "catalog-v2" / shop / "index.json").read_bytes()
        hist = (out / "catalog-v2" / shop / "history.json").read_bytes()
        assert entry["index_sha256"] == hashlib.sha256(body).hexdigest()
        assert entry["history_sha256"] == hashlib.sha256(hist).hexdigest()
        index = json.loads(body)
        assert index["schema"] == 2
        assert index["shop"] == shop
        assert entry["count"] == len(index["rows"]) == SPEC["expected"]["counts"][shop]


def test_index_serves_no_discount_position_exactly(tmp_path):
    """Позиция без скидки присутствует; SKU «A:17» возвращается целиком."""
    db = _build_db(tmp_path)
    out = _export_for_web(db, tmp_path / "web")
    manifest = json.loads((out / "catalog-v2" / "manifest.json").read_text(encoding="utf-8"))
    body = (out / "catalog-v2" / "mechta" / "index.json").read_bytes()
    assert hashlib.sha256(body).hexdigest() == manifest["shops"]["mechta"]["index_sha256"]

    rows = json.loads(body)["rows"]
    row = next(r for r in rows if r["product"]["sku"] == "A:17")
    assert row["product"]["old_price"] is None
    assert row["product"]["price"] == 120_000
    assert row["product"]["url"] == "https://www.mechta.kz/product/demo-a17/"
    assert row["product"]["mpn"] == "DP256-KZ"
    # История короче min_history_days — вердикта нет, поля отсутствия — null.
    assert row["fair_discount"] is None
    assert row["base_price"] is None
    assert row["pump_price"] is None
    assert row["exact_model"] == SPEC["expected"]["mechta_A17"]["exact_model"]
    # Одноимённый чехол тоже в каталоге, но без подтверждённого артикула.
    case = next(r for r in rows if r["product"]["sku"] == "CASE01")
    assert case["exact_model"] is None


def test_same_configuration_across_shops_shares_exact_model(tmp_path):
    """Контроль fixture (задача 6): mechta/A:17 и shopkz/77 — одна комплектация
    (DP256-KZ) и один exact_model; alser/78 (DP128-KZ) — другой; позиции без
    подтверждённого артикула получают null. Блок офферов по этим ключам
    покажет shopkz/77 (115000) для mechta/A:17 (120000), а 128 GB и чехол
    не войдут."""
    db = _build_db(tmp_path)
    out = _export_for_web(db, tmp_path / "web")

    indexes = {
        shop: json.loads((out / "catalog-v2" / shop / "index.json").read_text(encoding="utf-8"))
        for shop in ("mechta", "shopkz", "alser")
    }
    rows = {
        shop: {r["product"]["sku"]: r for r in index["rows"]}
        for shop, index in indexes.items()
    }
    a17 = rows["mechta"]["A:17"]["exact_model"]
    s77 = rows["shopkz"]["77"]["exact_model"]
    a78 = rows["alser"]["78"]["exact_model"]
    assert a17 == s77 == "demo:DP256-KZ"
    assert a78 == "demo:DP128-KZ"
    assert a78 != a17
    # Позиции без артикула производителя — блока офферов не будет.
    for sku in ("GONE5", "OOS3", "ONE9", "DROP1"):
        assert rows["mechta"][sku]["exact_model"] is None


def test_disappeared_product_keeps_last_known_price_and_dates(tmp_path):
    """Выбывший товар остаётся в каталоге с «последней известной ценой»,
    историей и датами; снятое наличие — отдельная причина недоступности."""
    db = _build_db(tmp_path)
    out = _export_for_web(db, tmp_path / "web")
    rows = {
        r["product"]["sku"]: r
        for r in json.loads((out / "catalog-v2" / "mechta" / "index.json").read_text(encoding="utf-8"))["rows"]
    }
    hist = json.loads((out / "catalog-v2" / "mechta" / "history.json").read_text(encoding="utf-8"))["items"]

    gone = rows["GONE5"]
    assert gone["product"]["in_stock"] is False  # предложения недоступны
    assert gone["product"]["price"] == 160_000  # последняя известная цена
    assert gone["last_seen"] == SPEC["expected"]["gone5"]["last_seen"]
    assert gone["product"]["first_seen"] == SPEC["expected"]["gone5"]["first_seen"]
    assert [p["price"] for p in hist["GONE5"]["points"]] == [160_000, 160_000]

    assert rows["OOS3"]["product"]["in_stock"] is False
    # Последнее ИСХОДНОЕ наблюдение в наличии — база сравнения карточки.
    assert hist["OOS3"]["recent_points"][-1]["price"] == 118_000


def test_empty_shop_listed_but_shop_without_successful_crawl_absent(tmp_path):
    """Пустой магазин с успешным обходом — валидный пустой индекс; магазин
    без успешного обхода не получает ни записи манифеста, ни файлов."""
    db = _build_db(tmp_path)
    out = _export_for_web(db, tmp_path / "web")
    manifest = json.loads((out / "catalog-v2" / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["shops"]["evrika"]["count"] == 0
    empty_index = json.loads((out / "catalog-v2" / "evrika" / "index.json").read_text(encoding="utf-8"))
    assert empty_index["rows"] == []
    assert manifest["shops"]["evrika"]["index_sha256"] == hashlib.sha256(
        (out / "catalog-v2" / "evrika" / "index.json").read_bytes()
    ).hexdigest()

    for shop in SPEC["expected"]["absent_shops"]:
        assert shop not in manifest["shops"]
    assert not (out / "catalog-v2" / "technodom").exists()


def test_history_file_keeps_daily_chart_and_raw_tail(tmp_path):
    """График — последняя цена за день и конец последнего отрезка; хвост —
    исходные наблюдения; первое наблюдение в наличии — метка first_stocked из
    той же выборки отрезков, что построила график (в байтах файла нет поля
    от момента выпуска)."""
    db = _build_db(tmp_path)
    out = _export_for_web(db, tmp_path / "web")
    items = json.loads((out / "catalog-v2" / "shopkz" / "history.json").read_text(encoding="utf-8"))["items"]
    expected = SPEC["expected"]["shopkz_77_history"]
    row = items["77"]

    assert [p["date"] for p in row["points"]] == expected["dates"]
    assert [p["price"] for p in row["points"]] == expected["prices"]
    assert [p["price"] for p in row["recent_points"]] == expected["recent_prices"]
    assert all("T" in p["date"] for p in row["recent_points"])
    assert row["min"] == expected["min"]
    assert row["median"] == expected["median"]
    assert row["first_stocked"] == expected["first_stocked"]
    assert row["first_stocked"][:10] == expected["dates"][0]
    assert "coverage_days" not in row
    assert row["days_at_current"] == 0


def test_reexport_of_unchanged_data_produces_same_hashes(tmp_path):
    """Повторный экспорт одних данных даёт те же хеши: экспортёр не ставит в
    файлы отметку о собственном запуске, и два прогона с теми же данными и
    тем же моментом экспорта совпадают байт в байт. Момент экспорта — явный
    параметр at: содержимое, зависящее от данных обхода (окна вердиктов),
    меняется вместе с данными, а не с запуском экспортёра."""
    db = _build_db(tmp_path)
    first, second = tmp_path / "first", tmp_path / "second"
    with storage.connect(db) as conn:
        catalog_export.export_catalog(conn, first, at=ANCHOR)
        catalog_export.export_catalog(conn, second, at=ANCHOR)

    assert (first / "catalog-v2" / "manifest.json").read_bytes() == (
        second / "catalog-v2" / "manifest.json"
    ).read_bytes()
    for shop in SPEC["expected"]["manifest_shops"]:
        for name in ("index.json", "history.json"):
            assert (first / "catalog-v2" / shop / name).read_bytes() == (
                second / "catalog-v2" / shop / name
            ).read_bytes()
    assert not list((first / "catalog-v2").glob("*.tmp"))  # атомарная замена без мусора


def _counted_export(db: Path, out: Path) -> int:
    statements = 0

    def _count(statement):
        nonlocal statements
        statements += 1

    with storage.connect(db) as conn:
        conn.set_trace_callback(_count)
        catalog_export.export_catalog(conn, out, at=ANCHOR)
        conn.set_trace_callback(None)
    return statements


def test_query_count_does_not_scale_with_shop_size(tmp_path):
    """Каталог и история читаются пакетами: 500 позиций магазина не умножают
    число запросов к SQLite (set_trace_callback меряет только export_catalog)."""
    small = _build_db(tmp_path / "small")
    big = _build_db(
        tmp_path / "big",
        extra=[
            Product(
                shop="mechta",
                sku=f"N{i:03d}",
                title=f"Товар номер {i}",
                price=10_000 + i,
                url=f"https://www.mechta.kz/product/n{i}/",
            )
            for i in range(500)
        ],
    )
    q_small = _counted_export(small, tmp_path / "out_small")
    q_big = _counted_export(big, tmp_path / "out_big")

    # Линейный рост добавил бы сотни запросов: SQL на позицию и на её историю.
    assert q_big - q_small < 50


def test_concurrent_crawl_completion_keeps_consistent_snapshot(tmp_path):
    """Обход, завершившийся посреди экспорта, не рвёт выпуск: экспорт читает
    один снимок, параллельные данные попадают в следующий запуск."""
    db = _build_db(tmp_path)
    out = tmp_path / "web"
    late = Product(
        shop="mechta",
        sku="LATE1",
        title="Поздний товар",
        price=99_000,
        url="https://www.mechta.kz/product/late/",
    )

    def _skus():
        body = json.loads((out / "catalog-v2" / "mechta" / "index.json").read_text(encoding="utf-8"))
        return {r["product"]["sku"] for r in body["rows"]}

    def _manifest():
        return json.loads((out / "catalog-v2" / "manifest.json").read_text(encoding="utf-8"))

    with storage.connect(db) as conn:
        conn.execute("BEGIN")
        # Первый читающий запрос фиксирует снимок WAL до параллельного обхода.
        conn.execute("SELECT COUNT(*) FROM products").fetchone()
        with storage.connect(db) as writer:
            storage.save_products(writer, [late], at=ANCHOR + timedelta(minutes=30))
            storage.record_crawl(writer, "mechta", 6, True, None, at=ANCHOR + timedelta(minutes=30))
        catalog_export.export_catalog(conn, out, at=ANCHOR)
        # Файлы и манифест согласованы: состояние до завершения параллельного обхода.
        assert "LATE1" not in _skus()
        assert _manifest()["shops"]["mechta"]["last_crawl"] == "2026-11-21T12:00:00Z"

    # Следующий экспорт (новый снимок) включает завершённый параллельно обход.
    with storage.connect(db) as fresh:
        catalog_export.export_catalog(fresh, out, at=ANCHOR)
    assert "LATE1" in _skus()
    assert _manifest()["shops"]["mechta"]["last_crawl"] == "2026-11-21T12:30:00Z"


def test_production_export_hashes_stable_between_runs(tmp_path):
    """Производственный путь: два выпуска export_for_web на неизменённой БД,
    запущенные в разное время, дают байт-в-байт одинаковые файлы catalog-v2 —
    момент экспорта выводится из данных (последний успешный обход), а не из
    часов запуска. Новый обход двигает момент — хеши меняются (детектором
    изменений манифест остаётся)."""

    def _catalog_files(out: Path) -> dict[str, bytes]:
        root = out / "catalog-v2"
        return {
            p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*"))
            if p.is_file()
        }

    db = _build_db(tmp_path)
    first = _export_for_web(db, tmp_path / "run1", moment=ANCHOR)
    second = _export_for_web(db, tmp_path / "run2", moment=ANCHOR + timedelta(hours=1))
    assert _catalog_files(first) == _catalog_files(second)

    late = Product(
        shop="mechta",
        sku="LATE1",
        title="Поздний товар",
        price=99_000,
        url="https://www.mechta.kz/product/late/",
    )
    with storage.connect(db) as conn:
        storage.save_products(conn, [late], at=ANCHOR + timedelta(hours=2))
        storage.record_crawl(conn, "mechta", 6, True, None, at=ANCHOR + timedelta(hours=2))
    third = _export_for_web(db, tmp_path / "run3", moment=ANCHOR + timedelta(hours=2))
    assert _catalog_files(third) != _catalog_files(second)


def test_v2_verdict_matches_legacy_for_band_between_windows(tmp_path):
    """Полоса 30–35 дней: окно fair-reference — low_window_days, как в legacy,
    поэтому отрезок в этой полосе не влияет на вердикт v2. Сценарий: уровень
    200 000 был 32 дня назад (вне low-окна), затем накрутка до 300 000 и
    возврат на 200 000 — с retention-окном «возврат к прежнему уровню» видел
    бы старый отрезок и обнулил вердикт вместо снижения от 300 000."""
    db = tmp_path / "band.sqlite3"
    levels = [
        (ANCHOR - timedelta(days=32), 200_000),  # вне low_window_days, внутри retention
        (ANCHOR - timedelta(days=29), 300_000),  # прежний уровень до окна тренда
        (ANCHOR - timedelta(days=22), 300_000),
        (ANCHOR - timedelta(days=15), 300_000),
        (ANCHOR - timedelta(days=8), 300_000),
        (ANCHOR - timedelta(days=1), 300_000),
        (ANCHOR, 200_000),
    ]
    def _band(price: int) -> Product:
        return Product(
            shop="mechta",
            sku="BAND1",
            title="Demo Phone 256 GB Ultra",
            price=price,
            url="https://www.mechta.kz/product/band/",
        )

    product = _band(200_000)
    out = tmp_path / "web"
    with storage.connect(db) as conn:
        for moment, price in levels:
            storage.save_products(conn, [_band(price)], at=moment)
        storage.record_crawl(conn, "mechta", 1, True, None, at=ANCHOR)
        catalog_export.export_catalog(conn, out, at=ANCHOR)

        row = next(
            r
            for r in json.loads((out / "catalog-v2" / "mechta" / "index.json").read_text(encoding="utf-8"))["rows"]
            if r["product"]["sku"] == "BAND1"
        )
        legacy_fair, legacy_ref, _age, legacy_pump = export._fair_reference_and_age(conn, product, ANCHOR)

    assert row["fair_discount"] == legacy_fair == 33.3
    assert row["base_price"] == legacy_ref == 300_000
    assert row["pump_price"] == legacy_pump is None


def test_export_for_web_reads_single_snapshot(tmp_path, monkeypatch):
    """BEGIN открывается до первого чтения legacy: latest.json, history.json и
    catalog-v2 выпускаются из одного снимка, а не из соседних."""
    db = _build_db(tmp_path)
    out = tmp_path / "web"
    phases: list[bool] = []
    original_history = export.export_history
    original_catalog = catalog_export.export_catalog

    def _spying_history(conn, out_dir, **kwargs):
        phases.append(conn.in_transaction)  # снапшот открыт ещё до legacy-фазы
        return original_history(conn, out_dir, **kwargs)

    def _spying_catalog(conn, out_dir, **kwargs):
        phases.append(conn.in_transaction)
        return original_catalog(conn, out_dir, **kwargs)

    monkeypatch.setattr(export, "export_history", _spying_history)
    monkeypatch.setattr(catalog_export, "export_catalog", _spying_catalog)
    _export_for_web(db, out)

    assert phases == [True, True]


# ===== Задача 7: счётчики качества покрытия в манифесте (quality) =====

# Зазор завышения — тот же, что в интерфейсе (web/src/lib/utils/verdict.ts).
INFLATION_GAP_PCT = 15

QUALITY_FIELDS = {
    "catalog_rows",
    "available_rows",
    "available_with_baseline",
    "available_with_rating",
    "advertised_rows",
    "advertised_checked",
    "advertised_painted",
}


def _quality_db(tmp_path) -> Path:
    """Общая фикстура качества: один экспорт несёт все проверяемые состояния.

    - mechta: заявленные скидки со всеми пятью вердиктами интерфейса
      (honest, inflated, pumped, painted, unknown) плюс позиция без скидки;
    - shopkz: «0 из 5» — пять заявленных скидок, истории не хватает ни одной;
    - alser: «3 из 5» — три проверенные (одна нарисованная), две без истории;
    - evrika: «0/0» — успешный обход без позиций, пустая выборка.
    """
    db = tmp_path / "quality.sqlite3"
    step = timedelta(hours=2)  # меньше GAP: наблюдения продлевают отрезок

    def _levels(shop: str, sku: str, title: str, periods, *, old_price=None, rating=None):
        with storage.connect(db) as conn:
            for start, end, price in periods:
                moment = start
                while moment <= end:
                    storage.save_products(
                        conn,
                        [
                            Product(
                                shop=shop,
                                sku=sku,
                                title=title,
                                price=price,
                                url=f"https://example.kz/product/{sku.lower()}/",
                                old_price=old_price,
                                rating=rating,
                                in_stock=True,
                            )
                        ],
                        at=moment,
                    )
                    moment += step

    def _one(shop: str, sku: str, title: str, price: int, *, old_price=None):
        _levels(shop, sku, title, [(ANCHOR, ANCHOR, price)], old_price=old_price)

    # mechta: все пять вердиктов + позиция без заявленной скидки.
    _levels("mechta", "HON", "Честная история", [(ANCHOR - timedelta(days=20), ANCHOR - timedelta(hours=2), 100_000), (ANCHOR, ANCHOR, 90_000)], old_price=100_000, rating=4.5)
    _levels("mechta", "INF", "Завышенная скидка", [(ANCHOR - timedelta(days=20), ANCHOR - timedelta(hours=2), 100_000), (ANCHOR, ANCHOR, 90_000)], old_price=150_000)
    _levels(
        "mechta",
        "PUMP",
        "Накрутка перед скидкой",
        [
            (ANCHOR - timedelta(days=20), ANCHOR - timedelta(days=12), 100_000),
            (ANCHOR - timedelta(days=12) + step, ANCHOR - timedelta(days=3), 150_000),
            (ANCHOR - timedelta(days=3) + step, ANCHOR, 90_000),
        ],
        old_price=300_000,
        rating=4.0,
    )
    _levels("mechta", "PAINT", "Нарисованная скидка", [(ANCHOR - timedelta(days=20), ANCHOR, 100_000)], old_price=120_000, rating=3.0)
    _one("mechta", "UNK", "Без истории", 80_000, old_price=100_000)
    _levels("mechta", "PLAIN", "Без скидки", [(ANCHOR - timedelta(days=10), ANCHOR, 50_000)])

    # shopkz: пять заявленных скидок, каждая видена один раз — все unknown.
    for i, (price, old) in enumerate(
        [(90_000, 100_000), (80_000, 120_000), (50_000, 60_000), (30_000, 40_000), (21_000, 30_000)], start=1
    ):
        _one("shopkz", f"S{i}", f"Новинка {i}", price, old_price=old)

    # alser: три проверенные (honest, painted, honest) + две без истории.
    _levels("alser", "A1", "Алсер честная", [(ANCHOR - timedelta(days=10), ANCHOR - timedelta(hours=2), 100_000), (ANCHOR, ANCHOR, 90_000)], old_price=100_000, rating=4.0)
    _levels("alser", "A2", "Алсер нарисованная", [(ANCHOR - timedelta(days=10), ANCHOR, 100_000)], old_price=120_000)
    _levels("alser", "A3", "Алсер снижение", [(ANCHOR - timedelta(days=10), ANCHOR - timedelta(hours=2), 60_000), (ANCHOR, ANCHOR, 52_000)], old_price=60_000)
    _one("alser", "A4", "Алсер новинка 1", 40_000, old_price=50_000)
    _one("alser", "A5", "Алсер новинка 2", 25_000, old_price=30_000)

    with storage.connect(db) as conn:
        for shop in ("mechta", "evrika", "shopkz", "alser"):
            storage.record_crawl(conn, shop, 0, True, None, at=ANCHOR)
    return db


def _verdict_kind(claimed, fair, pump):
    """Тот же критерий вердикта, что verdictOf в интерфейсе (verdict.ts)."""
    if fair is None:
        return "unknown"
    if fair <= 0:
        return "painted"
    if pump:
        return "pumped"
    if claimed is not None and claimed - fair >= INFLATION_GAP_PCT:
        return "inflated"
    return "honest"


def _recount_advertised(rows):
    """Пересчёт advertised-счётчиков из строк индекса тем же критерием."""
    kinds = []
    advertised = checked = painted = 0
    for row in rows:
        product = row["product"]
        if not product.get("discount_pct"):
            continue
        advertised += 1
        kind = _verdict_kind(product["discount_pct"], row["fair_discount"], row["pump_price"])
        kinds.append(kind)
        if kind != "unknown":
            checked += 1
        if kind == "painted":
            painted += 1
    return advertised, checked, painted, kinds


def _export_quality(tmp_path):
    db = _quality_db(tmp_path)
    out = tmp_path / "web"
    with storage.connect(db) as conn:
        catalog_export.export_catalog(conn, out, at=ANCHOR)
    manifest = json.loads((out / "catalog-v2" / "manifest.json").read_text(encoding="utf-8"))
    return out, manifest


def test_quality_counts_whole_v2_catalog_with_same_set_pairs(tmp_path):
    """Счётчики считаются по всему v2 каталогу; числитель и знаменатель каждой
    пары — один набор строк: available_* — из доступных, advertised_* — из
    заявленных скидок; ключи не меняются от магазина к магазину."""
    out, manifest = _export_quality(tmp_path)
    quality = manifest["shops"]["mechta"]["quality"]
    assert set(quality) == QUALITY_FIELDS

    rows = json.loads((out / "catalog-v2" / "mechta" / "index.json").read_text(encoding="utf-8"))["rows"]
    assert quality["catalog_rows"] == len(rows) == 6
    assert quality["available_rows"] == sum(1 for r in rows if r["product"]["in_stock"]) == 6
    assert quality["available_with_baseline"] == sum(
        1 for r in rows if r["product"]["in_stock"] and r["base_price"] is not None
    ) == 5  # у позиции без истории (UNK) обычной цены нет
    assert quality["available_with_rating"] == sum(
        1 for r in rows if r["product"]["in_stock"] and (r["product"]["rating"] or 0) > 0
    ) == 3  # HON, PUMP, PAINT


def test_quality_verdict_parity_for_all_five_verdicts(tmp_path):
    """Для checked/painted применяется тот же критерий вердикта, что в
    интерфейсе: на общей фикстуре присутствуют все пять вердиктов, и счётчики
    манифеста совпадают с пересчётом по строкам индекса."""
    out, manifest = _export_quality(tmp_path)
    rows = json.loads((out / "catalog-v2" / "mechta" / "index.json").read_text(encoding="utf-8"))["rows"]
    advertised, checked, painted, kinds = _recount_advertised(rows)
    assert set(kinds) == {"honest", "inflated", "pumped", "painted", "unknown"}

    quality = manifest["shops"]["mechta"]["quality"]
    assert quality["advertised_rows"] == advertised == 5
    assert quality["advertised_checked"] == checked == 4  # все, кроме unknown
    assert quality["advertised_painted"] == painted == 1  # только PAINT


def test_quality_three_distinct_states_zero_zero_zero_of_five_three_of_five(tmp_path):
    """0/0, «0 из 5» и «3 из 5» — три разных состояния на одной фикстуре:
    пустая выборка (evrika), заявленные скидки без истории (shopkz) и
    проверенные из заявленных (alser)."""
    _out, manifest = _export_quality(tmp_path)
    shops = manifest["shops"]

    assert shops["evrika"]["quality"] == {field: 0 for field in QUALITY_FIELDS}

    shopkz = shops["shopkz"]["quality"]
    assert shopkz["advertised_rows"] == 5
    assert shopkz["advertised_checked"] == 0
    assert shopkz["advertised_painted"] == 0

    alser = shops["alser"]["quality"]
    assert alser["advertised_rows"] == 5
    assert alser["advertised_checked"] == 3
    assert alser["advertised_painted"] == 1


def test_quality_stable_between_runs_and_absent_without_crawl(tmp_path):
    """Качество детерминировано (те же данные — тот же манифест) и не ломает
    контракт манифеста: магазин без успешного обхода записи не получает."""
    db = _quality_db(tmp_path)
    first, second = tmp_path / "first", tmp_path / "second"
    with storage.connect(db) as conn:
        catalog_export.export_catalog(conn, first, at=ANCHOR)
        catalog_export.export_catalog(conn, second, at=ANCHOR)
    assert (
        (first / "catalog-v2" / "manifest.json").read_bytes()
        == (second / "catalog-v2" / "manifest.json").read_bytes()
    )
    manifest = json.loads((first / "catalog-v2" / "manifest.json").read_text(encoding="utf-8"))
    assert "technodom" not in manifest["shops"]
