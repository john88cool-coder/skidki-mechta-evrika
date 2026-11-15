from datetime import datetime, timezone

from skidki.matching import extract_mpn, marketplace_medians, model_key
from skidki.models import Product
from skidki.storage import active_catalog_products, connect, save_products


def test_extract_mpn_handles_samsung_apple_and_asus_codes_without_false_positives():
    assert extract_mpn("Смартфон Samsung Galaxy S24 Ultra 256GB (SM-S928BZKDSKZ)") == "SM-S928B"
    assert extract_mpn("Смартфон Apple iPhone 16 Pro 256GB MYNF3HX/A Black") == "MYNF3"
    assert extract_mpn("Ноутбук ASUS ROG Strix G16", explicit_mpn="G614JV-N4071") == "G614JV-N4071"
    # Объёмы памяти и стандарты связи не должны приниматься за заводской артикул:
    assert extract_mpn("Смартфон 128GB WIFI6 120HZ IP68") is None


def test_marketplace_medians_clusters_across_at_least_two_shops():
    items = [
        Product(
            shop="mechta",
            sku="1",
            title="Смартфон Samsung Galaxy S24 Ultra 12/256GB Titanium Black (SM-S928BZKDSKZ)",
            price=490_000,
            url="https://mechta.kz/1",
            brand="Samsung",
        ),
        Product(
            shop="shopkz",
            sku="2",
            title="Смартфон Samsung Galaxy S24 Ultra 256GB Gray",
            price=510_000,
            url="https://shop.kz/2",
            brand="SAMSUNG",
            mpn="SM-S928BZADSKZ",
        ),
        Product(
            shop="technodom",
            sku="3",
            title="Смартфон Samsung Galaxy S24 Ultra 256GB (SM-S928B)",
            price=530_000,
            url="https://technodom.kz/3",
            brand="Samsung",
        ),
        # Одиночный товар только в одном магазине — медианы рынка нет:
        Product(
            shop="alser",
            sku="99",
            title="Эксклюзивный чехол Alser Case 9000X",
            price=5_000,
            url="https://alser.kz/99",
            brand="Alser",
        ),
    ]
    keys = [model_key(p) for p in items[:3]]
    assert keys[0] == keys[1] == keys[2] == "samsung:mpn:SM-S928B"

    medians = marketplace_medians(items)
    assert medians["mechta:1"] == 510_000
    assert medians["shopkz:2"] == 510_000
    assert medians["technodom:3"] == 510_000
    assert "alser:99" not in medians


def test_signature_fallback_matches_clean_model_and_storage_without_mpn():
    a = Product(
        shop="evrika",
        sku="10",
        title="Смартфон Apple iPhone 16 Pro 256GB Black Titanium",
        price=619_990,
        url="https://evrika.com/10",
        brand="Apple",
    )
    b = Product(
        shop="sulpak",
        sku="20",
        title="Смартфон Apple iPhone 16 Pro 256 ГБ Синий Титановый",
        price=639_990,
        url="https://sulpak.kz/20",
        brand="APPLE",
    )
    assert model_key(a) == model_key(b)
    medians = marketplace_medians([a, b])
    assert medians["evrika:10"] == 629_990


def test_active_catalog_products_returns_in_stock_items(tmp_path):
    db = tmp_path / "cat.sqlite3"
    t0 = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)
    with connect(db) as conn:
        save_products(
            conn,
            [
                Product(shop="mechta", sku="1", title="A", price=50_000, url="https://x/1", in_stock=True),
                Product(shop="mechta", sku="2", title="B", price=60_000, url="https://x/2", in_stock=False),
            ],
            at=t0,
        )
        active = active_catalog_products(conn)
    assert [p.identity for p in active] == ["mechta:1"]
