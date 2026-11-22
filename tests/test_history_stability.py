"""Стабильность байтов history.json: байты файла не зависят от времени выпуска.

Замер 12 экспортов суток (день с обходами каждые 2 часа, полночь между
6-м и 7-м) показал: при обходах без изменений переписывались все шесть
history.json — единственное поле, зависящее от часов экспортёра, было
coverage_days от момента выпуска. После задачи в байтах
catalog-v2/<shop>/history.json нет ни одного поля от момента выпуска:
первое наблюдение в наличии пишется меткой first_stocked из той же выборки
отрезков, что построила график, а покрытие карточки фронтенд считает от
времени оценки среза. Допустимые причины изменения байтов между выпусками —
данные: смена цены магазина, новая дневная точка после реального обхода
(полночь), границы окна. Экспорт — производственный путь export_for_web,
без monkeypatch: момент выпуска выводится из данных (export_moment).
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from skidki import catalog_export
from skidki.export import SHOPS, export_for_web
from skidki.models import Product
from skidki.storage import connect, record_crawl, save_products

N = 400  # позиций на магазин
SEED_DAYS = 40  # дневной сид до суток наблюдения
D0 = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)  # последний ночной обход-сида
HOURS = [13, 15, 17, 19, 21, 23, 1, 3, 5, 7, 9, 11]  # полночь между 6-м и 7-м
CHANGED_FROM = 2  # с экспорта 2 (15:00) mechta/P0000 персистентно держит 110 000


def _products(shop: str, changed: bool) -> list[Product]:
    out = []
    for i in range(N):
        price = 120_000 if (shop == "mechta" and i == 0) else 90_000 + i * 37
        if changed and shop == "mechta" and i == 0:
            price = 110_000
        out.append(
            Product(
                shop=shop,
                sku=f"P{i:04d}",
                title=f"Товар {shop} {i}",
                price=price,
                old_price=price + 40_000 if i % 9 == 0 else None,
                url=f"https://www.{shop}.kz/product/p{i}/",
                brand="Demo",
                group=f"g{i % 7}",
                in_stock=True,
                mpn=f"DP{i:04d}-KZ" if i % 5 == 0 else None,
            )
        )
    return out


def _seed(db: Path) -> None:
    with connect(db) as conn:
        for d in range(SEED_DAYS - 1, -1, -1):
            t = D0 - timedelta(days=d)
            for shop in SHOPS:
                save_products(conn, _products(shop, changed=False), at=t)
                record_crawl(conn, shop, N, True, None, at=t)


def _run_day(
    db: Path, out: Path, keep: tuple[int, ...] = ()
) -> tuple[list[dict[str, str]], dict[int, dict[str, bytes]]]:
    """Сутки из 12 экспортов с обходами каждые 2 часа. Возвращает SHA-256
    history.json каждого магазина по экспортам и байты выбранных экспортов
    (для байтового диффа). Часы машины не подменяются: момент выпуска —
    export_moment из данных, как в производстве."""
    out.mkdir(parents=True, exist_ok=True)
    hashes: list[dict[str, str]] = []
    kept: dict[int, dict[str, bytes]] = {}
    for idx, hour in enumerate(HOURS, 1):
        day = 20 if hour >= 13 else 21
        t = datetime(2026, 11, day, hour, 0, tzinfo=UTC)
        with connect(db) as conn:
            for shop in SHOPS:
                save_products(conn, _products(shop, changed=idx >= CHANGED_FROM), at=t)
                record_crawl(conn, shop, N, True, None, at=t)
        export_for_web(db_path=db, out_dir=out)
        bodies = {
            shop: (out / "catalog-v2" / shop / "history.json").read_bytes()
            for shop in SHOPS
        }
        hashes.append({shop: hashlib.sha256(body).hexdigest() for shop, body in bodies.items()})
        if idx in keep:
            kept[idx] = bodies
    return hashes, kept


def _changed(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return [shop for shop in SHOPS if before[shop] != after[shop]]


def test_no_change_exports_keep_history_bytes_stable(tmp_path):
    """Обходы без изменений не переписывают history.json: байты и SHA-256 шести
    файлов одинаковы между экспортами 3–5 и 8–12 (после полночи). До задачи
    каждые 2 часа переписывались все магазины: coverage_days считалось от
    момента выпуска, который двигает каждый успешный обход."""
    db = tmp_path / "day.sqlite3"
    _seed(db)
    hashes, _kept = _run_day(db, tmp_path / "pub")

    for n in (3, 4, 5, 8, 9, 10, 11, 12):
        rewritten = _changed(hashes[n - 2], hashes[n - 1])
        assert not rewritten, (
            f"экспорт {n:02d} ({HOURS[n - 1]:02d}:00 UTC) переписал history.json: {rewritten}"
        )


def test_single_persistent_sku_change_rewrites_only_that_shop(tmp_path):
    """Персистентная смена цены одного SKU (mechta/P0000, 15:00) меняет только
    history.json соответствующего магазина, и только строку этого SKU; остальные
    пять магазинов байт в байт те же."""
    db = tmp_path / "day.sqlite3"
    _seed(db)
    hashes, kept = _run_day(db, tmp_path / "pub", keep=(1, 2))

    assert _changed(hashes[0], hashes[1]) == ["mechta"]
    before = json.loads(kept[1]["mechta"])["items"]
    after = json.loads(kept[2]["mechta"])["items"]
    assert [sku for sku in before if before[sku] != after[sku]] == ["P0000"]


def test_midnight_adds_one_day_point_after_real_crawl(tmp_path):
    """Полночь сама по себе не переписывает историю: экспорт 7 (01:00) меняет
    history.json только новой дневной точкой после реального обхода — у каждой
    позиции в наличии появляется одна хвостовая точка 2026-11-21, прочие поля
    (recent_points, min, median, days_at_current, first_stocked) те же. Шесть
    магазинов сценария все с позициями, поэтому переписаны все шесть — и только
    по этой объяснимой причине."""
    db = tmp_path / "day.sqlite3"
    _seed(db)
    hashes, kept = _run_day(db, tmp_path / "pub", keep=(6, 7))

    rewritten = _changed(hashes[5], hashes[6])
    assert rewritten == list(SHOPS)
    for shop in rewritten:
        before = json.loads(kept[6][shop])["items"]
        after = json.loads(kept[7][shop])["items"]
        assert set(before) == set(after)
        for sku, old in before.items():
            new = after[sku]
            assert new["points"] == old["points"] + [
                {
                    "date": "2026-11-21",
                    "price": old["points"][-1]["price"],
                    "old_price": old["points"][-1]["old_price"],
                }
            ], f"{shop}/{sku}: точки изменились не на одну дневную"
            assert new["recent_points"] == old["recent_points"], f"{shop}/{sku}: recent_points"
            for field in ("min", "median", "days_at_current", "first_stocked"):
                assert new[field] == old[field], f"{shop}/{sku}: {field}"


def test_no_in_stock_observations_writes_null_first_stocked(tmp_path):
    """Отсутствие наблюдений в наличии: first_stocked — null, точки пустые, а
    байты файла не зависят от момента выпуска (два экспорта с разным at)."""
    anchor = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
    db = tmp_path / "oos.sqlite3"
    product = Product(
        shop="mechta",
        sku="OOS1",
        title="Снятый товар",
        price=118_000,
        url="https://www.mechta.kz/product/oos1/",
        in_stock=False,
    )
    with connect(db) as conn:
        save_products(conn, [product], at=anchor - timedelta(days=1))
        save_products(conn, [product], at=anchor)
        record_crawl(conn, "mechta", 1, True, None, at=anchor)

    first_out, second_out = tmp_path / "first", tmp_path / "second"
    with connect(db) as conn:
        catalog_export.export_catalog(conn, first_out, at=anchor)
        catalog_export.export_catalog(conn, second_out, at=anchor + timedelta(hours=2))

    row = json.loads((first_out / "catalog-v2" / "mechta" / "history.json").read_text("utf-8"))[
        "items"
    ]["OOS1"]
    assert row["points"] == []
    assert row["first_stocked"] is None
    assert (first_out / "catalog-v2" / "mechta" / "history.json").read_bytes() == (
        second_out / "catalog-v2" / "mechta" / "history.json"
    ).read_bytes()


def test_first_stocked_is_windowed_sample_not_all_time_first_seen(tmp_path):
    """first_stocked — из той же выборки отрезков, что построила график (окно
    retention), а не дата первого появления товара за всё время: 40 дней
    наблюдений при окне 35 дней — метка совпадает с первой точкой графика и
    обе позже first_seen каталога. В новых файлах числового coverage_days нет."""
    anchor = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
    db = tmp_path / "window.sqlite3"

    def _product() -> Product:
        return Product(
            shop="mechta",
            sku="W1",
            title="Длинная история",
            price=90_000,
            url="https://www.mechta.kz/product/w1/",
        )

    with connect(db) as conn:
        for d in range(39, -1, -1):
            save_products(conn, [_product()], at=anchor - timedelta(days=d))
        record_crawl(conn, "mechta", 1, True, None, at=anchor)
        out = tmp_path / "out"
        catalog_export.export_catalog(conn, out, at=anchor)

    index_row = next(
        r
        for r in json.loads((out / "catalog-v2" / "mechta" / "index.json").read_text("utf-8"))["rows"]
        if r["product"]["sku"] == "W1"
    )
    row = json.loads((out / "catalog-v2" / "mechta" / "history.json").read_text("utf-8"))["items"][
        "W1"
    ]
    assert index_row["product"]["first_seen"] == "2026-10-13T12:00:00Z"  # всё время
    assert row["first_stocked"] == "2026-10-17T12:00:00Z"  # окно retention (35 дней)
    assert row["first_stocked"][:10] == row["points"][0]["date"]
    assert "coverage_days" not in row
