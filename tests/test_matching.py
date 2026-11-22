from datetime import datetime, timezone

from skidki.matching import exact_offer_key, extract_mpn, marketplace_medians, model_key
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


def test_exact_offer_key_same_model_in_two_sources_shares_key():
    """Одна модель в двух источниках — один ключ: полный код с вариантным
    хвостом подтверждает комплектацию сам; регистр нормирован."""
    mechta = Product(
        shop="mechta",
        sku="1",
        title="Смартфон Samsung Galaxy S24 Ultra 12/256GB Titanium Black (SM-S928BZKDSKZ)",
        price=490_000,
        url="https://mechta.kz/1",
        brand="Samsung",
    )
    shopkz = Product(
        shop="shopkz",
        sku="2",
        title="Смартфон Samsung Galaxy S24 Ultra 256GB Black",
        price=510_000,
        url="https://shop.kz/2",
        brand="SAMSUNG",
        mpn="sm-s928bzkdskz",
    )
    assert exact_offer_key(mechta) == exact_offer_key(shopkz) == "samsung:SM-S928BZKDSKZ"
    # Другой вариантный хвост (другой цвет) — другая комплектация, ключ другой:
    gray = Product(
        shop="technodom",
        sku="3",
        title="Смартфон Samsung Galaxy S24 Ultra 256GB Gray",
        price=530_000,
        url="https://technodom.kz/3",
        brand="Samsung",
        mpn="SM-S928BZADSKZ",
    )
    gray_key = exact_offer_key(gray)
    assert gray_key == "samsung:SM-S928BZADSKZ"
    assert gray_key != exact_offer_key(mechta)


def test_exact_offer_key_differs_for_different_storage_on_shared_base_code():
    """Разные объёмы памяти при общем базовом коде семейства — разные ключи:
    базовый код без варианта не подтверждает конкретную комплектацию."""
    a = Product(
        shop="mechta",
        sku="1",
        title="Смартфон Samsung Galaxy S25 256GB (SM-S931B)",
        price=400_000,
        url="https://mechta.kz/1",
        brand="Samsung",
    )
    b = Product(
        shop="shopkz",
        sku="2",
        title="Смартфон Samsung Galaxy S25 512GB (SM-S931B)",
        price=480_000,
        url="https://shop.kz/2",
        brand="Samsung",
    )
    a_key, b_key = exact_offer_key(a), exact_offer_key(b)
    assert a_key is not None and b_key is not None
    assert a_key != b_key


def test_exact_offer_key_regional_suffix_preserved():
    """Региональный суффикс значим: полные коды с разными суффиксами не склеиваются."""
    a = Product(
        shop="mechta",
        sku="1",
        title="Ноутбук ASUS ROG Strix G16 (G614JV-N4071)",
        price=700_000,
        url="https://mechta.kz/1",
        brand="ASUS",
        mpn="G614JV-N4071",
    )
    b = Product(
        shop="shopkz",
        sku="2",
        title="Ноутбук ASUS ROG Strix G16 (G614JV-N5101)",
        price=750_000,
        url="https://shop.kz/2",
        brand="ASUS",
        mpn="G614JV-N5101",
    )
    a_key, b_key = exact_offer_key(a), exact_offer_key(b)
    assert a_key is not None and b_key is not None
    assert a_key != b_key
    # Тот же артикул в другом магазине и регистре — тот же ключ.
    c = Product(
        shop="alser",
        sku="3",
        title="Ноутбук ASUS ROG Strix G16",
        price=720_000,
        url="https://alser.kz/3",
        brand="asus",
        mpn="g614jv-n4071",
    )
    assert exact_offer_key(c) == a_key


def test_exact_offer_key_laptops_with_different_configs_differ():
    """Ноутбуки одной линейки с разной конфигурацией: одинаковый бренд и серия,
    но разные артикулы — разные ключи; одиночный CPU-суффикс без полного
    артикула модель не подтверждает."""
    a = Product(
        shop="mechta",
        sku="1",
        title="Ноутбук ASUS TUF Gaming F15 FX506LHB-HN323W",
        price=450_000,
        url="https://mechta.kz/1",
        brand="ASUS",
    )
    b = Product(
        shop="shopkz",
        sku="2",
        title="Ноутбук ASUS TUF Gaming F15 FX506LHB-HN324W",
        price=470_000,
        url="https://shop.kz/2",
        brand="ASUS",
    )
    a_key, b_key = exact_offer_key(a), exact_offer_key(b)
    assert a_key is not None and b_key is not None
    assert a_key != b_key


def test_exact_offer_key_class_tokens_like_gpu_do_not_merge_laptops():
    """Класс-токен железа (RTX-3050) — не артикул производителя: два разных
    ноутбука ASUS с одной видеокартой не должны склеиваться в одну модель.
    При сомнении ключа нет (блок скрывается), а не рискованная склейка."""
    tuf = Product(
        shop="mechta",
        sku="1",
        title="Ноутбук ASUS TUF Gaming RTX-3050 144Hz",
        price=450_000,
        url="https://mechta.kz/1",
        brand="ASUS",
    )
    vivobook = Product(
        shop="shopkz",
        sku="2",
        title="Ноутбук ASUS VivoBook RTX-3050 Silver",
        price=430_000,
        url="https://shop.kz/2",
        brand="ASUS",
    )
    tuf_key, vivo_key = exact_offer_key(tuf), exact_offer_key(vivobook)
    # Склейки нет: разные ключи или оба None (блок скрыт — «при сомнении None»).
    assert tuf_key != vivo_key or (tuf_key is None and vivo_key is None)
    assert not (tuf_key is not None and tuf_key == vivo_key)
    # И по отдельности ключа у «модели», названной только классом GPU, нет:
    assert exact_offer_key(
        Product(
            shop="mechta",
            sku="3",
            title="Ноутбук ASUS RTX-3050",
            price=440_000,
            url="https://mechta.kz/3",
            brand="ASUS",
        )
    ) is None


def test_exact_offer_key_wifi_class_tokens_do_not_merge_routers():
    """Класс-токен WiFi-стандарта (AX-3000, AX1800) — не артикул: два разных
    роутера Xiaomi/Redmi с одинаковым классом не склеиваются; mpn-путь тоже
    не превращает стандарт в артикул."""
    redmi = Product(
        shop="mechta",
        sku="1",
        title="Роутер Xiaomi Redmi Router AX-3000",
        price=30_000,
        url="https://mechta.kz/1",
        brand="Redmi",
    )
    aiot = Product(
        shop="shopkz",
        sku="2",
        title="Роутер Xiaomi AIoT Router AX-3000",
        price=35_000,
        url="https://shop.kz/2",
        brand="Xiaomi",
    )
    redmi_key, aiot_key = exact_offer_key(redmi), exact_offer_key(aiot)
    # Склейки нет: разные ключи или оба None (блок скрыт — «при сомнении None»).
    assert redmi_key != aiot_key or (redmi_key is None and aiot_key is None)
    assert not (redmi_key is not None and redmi_key == aiot_key)
    # Стандарт связи в mpn-поле артикулом не становится:
    assert exact_offer_key(
        Product(
            shop="technodom",
            sku="3",
            title="Роутер Xiaomi",
            price=32_000,
            url="https://technodom.kz/3",
            brand="Xiaomi",
            mpn="AX-3000",
        )
    ) is None


def test_exact_offer_key_accessory_without_identifiers_is_none():
    """Аксессуар без бренд-артикула (одноимённый чехол) — ключа нет: блок скрыт."""
    case = Product(
        shop="mechta",
        sku="CASE01",
        title="Чехол Demo Phone",
        price=4_990,
        url="https://mechta.kz/CASE01",
        brand=None,
    )
    assert exact_offer_key(case) is None


def test_exact_offer_key_missing_mpn_and_seller_sku_alone_is_none():
    """Без подтверждённого артикула производителя ключа нет: обычный SKU
    продавца (числовой SKU shop.kz) сам по себе модель не подтверждает."""
    no_id = Product(
        shop="mechta",
        sku="GONE5",
        title="Demo Phone 512 GB",
        price=160_000,
        url="https://mechta.kz/GONE5",
        brand="Demo",
    )
    seller_sku_only = Product(
        shop="shopkz",
        sku="1741739",
        title="Bluetooth гарнитура Rombica MySound BH-T031, Echo White",
        price=25_000,
        url="https://shop.kz/1741739",
        brand="Rombica",
        mpn="BH-T031",
    )
    assert exact_offer_key(no_id) is None
    # MPN из варианта магазина подтверждается только вместе с брендом и полным кодом:
    # у Rombica это партномер — ключ допустим, а числовой SKU им не заменяется.
    assert exact_offer_key(seller_sku_only) is not None
    bare_sku = Product(
        shop="shopkz",
        sku="1741739",
        title="Bluetooth гарнитура Rombica MySound, Echo White",
        price=25_000,
        url="https://shop.kz/1741739",
        brand="Rombica",
    )
    assert exact_offer_key(bare_sku) is None


def test_exact_offer_key_requires_variant_match_for_shared_family_code():
    """Семейство с общим артикулом и вариантом (цвет/регион) в MPN: ключ даёт
    только совпадение полного кода; конфликт вариантов — None."""
    a = Product(
        shop="mechta",
        sku="1",
        title='Планшет Samsung Galaxy Tab A11+ 11" 128GB SM-X236BZAASKZ (GRAY)',
        price=120_000,
        url="https://mechta.kz/1",
        brand="Samsung",
    )
    b = Product(
        shop="evrika",
        sku="2",
        title='Планшет Samsung Galaxy Tab A11+ 11" 128GB Silver (SM-X236BZSASKZ)',
        price=125_000,
        url="https://evrika.kz/2",
        brand="Samsung",
    )
    assert exact_offer_key(a) == "samsung:SM-X236BZAASKZ"
    assert exact_offer_key(b) == "samsung:SM-X236BZSASKZ"
    assert exact_offer_key(a) != exact_offer_key(b)
    # Конфликт характеристик: заголовок называет один код, поле mpn — другой.
    conflicting = Product(
        shop="sulpak",
        sku="3",
        title='Планшет Samsung Galaxy Tab A11+ 11" 128GB (SM-X236BZAASKZ)',
        price=122_000,
        url="https://sulpak.kz/3",
        brand="Samsung",
        mpn="SM-X236BZSASKZ",
    )
    assert exact_offer_key(conflicting) is None
