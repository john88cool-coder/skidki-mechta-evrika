import json

import pytest
from conftest import FIXTURES

from skidki.config import ALSER_GROUPS, EVRIKA_ROOTS, SHOPKZ_SECTIONS, SULPAK_CATEGORIES, TECHNODOM_ROOTS
from skidki.parsers import alser, evrika, mechta, shopkz, sulpak, technodom


@pytest.fixture(scope="module")
def mechta_data():
    return json.loads((FIXTURES / "mechta_products.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def evrika_data():
    return evrika.next_data((FIXTURES / "evrika_category.html").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def technodom_data():
    return json.loads((FIXTURES / "technodom_products.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def shopkz_html():
    return (FIXTURES / "shopkz_listing.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sulpak_html():
    return (FIXTURES / "sulpak_listing.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sulpak_ajax():
    return json.loads((FIXTURES / "sulpak_ajax.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def alser_data():
    return json.loads((FIXTURES / "alser_catalog.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def alser_sitemap():
    return (FIXTURES / "alser_categories.xml").read_text(encoding="utf-8")


def test_mechta_parse(mechta_data):
    products = mechta.parse(mechta_data)
    raw = mechta_data["products"]
    assert len(products) == len(raw)
    first = products[0]
    assert first.shop == "mechta"
    assert first.sku == raw[0]["code"]
    assert first.price == raw[0]["prices"]["finalPrice"]
    assert first.url == f"https://www.mechta.kz/product/{raw[0]['slug']}/"
    assert first.brand and first.category
    assert all(p.old_price is None or p.old_price > p.price for p in products)
    assert any(p.old_price for p in products)
    assert mechta.total_pages(mechta_data) == mechta_data["meta"]["totalPages"]


def test_mechta_image_from_images(mechta_data):
    """Миниатюра — images[0] с ресайзом CDN (?w=400: 17 КБ вместо 115 КБ)."""
    products = mechta.parse(mechta_data)
    with_image = [p for p in products if p.image]
    assert with_image, "ни у одной позиции фикстуры нет картинки"
    first = with_image[0]
    assert first.image.startswith("https://pi.mdev.kz/")
    assert first.image.endswith("?w=400")


def test_evrika_image_from_images(evrika_data):
    """Миниатюра — первый medium/webp из images (cdn.evrika.com)."""
    products, _ = evrika.parse_products(evrika_data)
    with_image = [p for p in products if p.image]
    assert with_image, "ни у одной позиции фикстуры нет картинки"
    assert with_image[0].image.startswith("https://cdn.evrika.com/storage/products/images/medium/")


def test_technodom_image_built_from_images(technodom_data):
    """Миниатюра — api.technodom.kz/f3/api/v1/images/<id>.webp (разведка 2026-09-18)."""
    products = technodom.parse(technodom_data)
    with_image = [p for p in products if p.image]
    assert with_image, "ни у одной позиции фикстуры нет картинки"
    assert with_image[0].image.startswith("https://api.technodom.kz/f3/api/v1/images/")
    assert with_image[0].image.endswith(".webp")


def test_shopkz_image_from_data_product(shopkz_html):
    """Миниатюра — поле image из JSON data-product (static.shop.kz)."""
    products = shopkz.parse_cards(shopkz_html, "phones")
    with_image = [p for p in products if p.image]
    assert with_image, "ни у одной карточки фикстуры нет картинки"
    assert with_image[0].image.startswith("https://static.shop.kz/")


def test_sulpak_image_from_block(sulpak_html):
    """Миниатюра — первый webp из srcset/source (object.pscloud.io)."""
    products = sulpak.parse_blocks(sulpak_html, "phones")
    with_image = [p for p in products if p.image]
    assert with_image, "ни у одной карточки фикстуры нет картинки"
    assert with_image[0].image.startswith("https://object.pscloud.io/")
    assert with_image[0].image.endswith(".webp")


def test_alser_image_from_field(alser_data):
    """Миниатюра — поле image (s3s.alser.kz, уже -w160.webp)."""
    products = alser.parse(alser_data, "computers")
    with_image = [p for p in products if p.image]
    assert with_image, "ни у одной позиции фикстуры нет картинки"
    assert with_image[0].image.startswith("https://s3s.alser.kz/")


def test_mechta_stock_flags(mechta_data):
    item = dict(mechta_data["products"][0], availability="not_available", lowStock=True)
    [parsed] = mechta.parse({"products": [item]})
    assert not parsed.in_stock
    assert parsed.stock_note == "осталось мало"


def test_mechta_skips_broken_items():
    assert mechta.parse({"products": [{"name": "без цены"}]}) == []


def test_mechta_api_url_respects_page_size_limit():
    assert "pageSize=50" in mechta.api_url("tv-audio-video", 3)
    assert "sort=" not in mechta.api_url("tv-audio-video", 3)  # robots.txt: Disallow *sort=*


def test_evrika_parse(evrika_data):
    products, last_page = evrika.parse_products(evrika_data)
    assert last_page == 2
    assert len(products) == 4
    first = products[0]
    assert first.shop == "evrika"
    assert first.url.startswith("https://evrika.com/catalog/") and f"/p{first.sku}" in first.url
    assert "\xa0" not in first.title
    discounted = [p for p in products if p.old_price]
    assert discounted and all(p.old_price > p.price for p in discounted)
    assert all(p.in_stock for p in products)


def test_evrika_leaf_categories_from_live_tree(evrika_data):
    leaves = evrika.leaf_categories(evrika.menu_tree(evrika_data), {cid for cid, _ in EVRIKA_ROOTS})
    assert len(leaves) == 150  # разведка 2026-09-13
    assert (310, "smart-chasy") in leaves


def test_evrika_leaf_categories_synthetic():
    tree = [
        {"id": 1, "parent_id": 0, "slug": "root"},
        {"id": 2, "parent_id": 1, "slug": "mid"},
        {"id": 3, "parent_id": 2, "slug": "leaf-a"},
        {"id": 4, "parent_id": 1, "slug": "leaf-b"},
        {"id": 5, "parent_id": 0, "slug": "other-root"},
        {"id": 6, "parent_id": 5, "slug": "other-leaf"},
    ]
    assert evrika.leaf_categories(tree, {1}) == [(3, "leaf-a"), (4, "leaf-b")]


def test_evrika_category_url():
    assert evrika.category_url(310, "smart-chasy") == "https://evrika.com/catalog/smart-chasy/c310"
    assert evrika.category_url(310, "smart-chasy", 2).endswith("/c310?page=2")


def test_evrika_challenge_page_is_an_error():
    with pytest.raises(ValueError):
        evrika.next_data("<html><title>Just a moment...</title></html>")


def test_technodom_parse(technodom_data):
    products = technodom.parse(technodom_data)
    raw = technodom_data["payload"]
    assert len(products) == len(raw)
    first = products[0]
    assert first.shop == "technodom"
    assert first.sku == raw[0]["sku"]
    assert first.price == int(raw[0]["price"])
    assert first.url == f"https://www.technodom.kz/product/{raw[0]['uri']}"
    assert first.brand == raw[0]["brand"]
    assert all(p.old_price is None or p.old_price > p.price for p in products)
    assert any(p.old_price for p in products)


def test_technodom_api_url_sorts_by_discount():
    url = technodom.api_url("smart-chasy", 2)
    assert url.startswith("https://api.technodom.kz/katalog/api/v2/products/category/smart-chasy?")
    assert "limit=50" in url and "page=2" in url
    assert "sorting=discount:desc" in url  # разрешённая сортировка API


def test_technodom_roots_map_to_groups():
    assert set(TECHNODOM_ROOTS.values()) <= {"phones", "computers", "tv", "home", "kitchen", "beauty"}
    assert len(TECHNODOM_ROOTS) == 6


def test_shopkz_parse_cards(shopkz_html):
    products = shopkz.parse_cards(shopkz_html, "phones")
    assert len(products) == 2
    first = products[0]
    assert first.shop == "shopkz"
    assert first.url.startswith("https://shop.kz/offer/")
    assert first.title.startswith("Ноутбук")
    assert first.old_price is None or first.old_price > first.price
    assert first.in_stock


def test_shopkz_section_url_pagination():
    assert shopkz.section_url("noutbuki", 1) == "https://shop.kz/offers/noutbuki/"
    assert shopkz.section_url("noutbuki", 3) == "https://shop.kz/offers/noutbuki/?PAGEN_1=3"


def test_shopkz_sections_cover_all_groups():
    assert set(SHOPKZ_SECTIONS.values()) <= {"phones", "computers", "tv", "home", "kitchen", "beauty"}


def test_sulpak_parse_blocks(sulpak_html):
    products = sulpak.parse_blocks(sulpak_html, "phones")
    assert len(products) == 3
    first = products[0]
    assert first.shop == "sulpak"
    assert first.sku.isdigit()
    assert first.url.startswith("https://www.sulpak.kz/g/")
    assert first.title.startswith("Смартфон")
    # В фикстуре первая карточка: 749 890 зачёркнутая, 699 890 текущая.
    assert first.old_price == 749_890
    assert first.price == 699_890
    assert all(p.old_price is None or p.old_price > p.price for p in products)


def test_sulpak_pages_count(sulpak_ajax):
    assert sulpak.pages_count(sulpak_ajax["paginator"]) == 45


def test_sulpak_dedupe_doubles(sulpak_html):
    # AJAX дублирует каждый блок (список + плитка) — _dedupe оставляет первые.
    parsed = sulpak.parse_blocks(sulpak_html, "phones")
    doubled = parsed + parsed
    unique = sulpak._dedupe(doubled)
    assert len(unique) == len(parsed)


def test_sulpak_categories_cover_all_groups():
    assert set(SULPAK_CATEGORIES.values()) <= {"phones", "computers", "tv", "home", "kitchen", "beauty"}


def test_alser_parse_categories(alser_sitemap):
    keywords = alser.parse_categories(alser_sitemap)
    # 173 /c/-URL сайтмапа минус 3 бренд-страницы /c/<kw>/f/brend/... (разведка 2026-09-15)
    assert len(keywords) == 170
    assert "vse-smartfony" in keywords
    # Бренд-страницы /f/brend/... в ключи категорий не попадают
    assert all("/f/" not in k for k in keywords)


def test_alser_group_mapping():
    assert alser._group("vse-smartfony") == "phones"
    assert alser._group("noutbuki") == "computers"
    assert alser._group("kofemashiniy") == "kitchen"
    assert alser._group("naushniki") == "phones"
    assert alser._group("aksessuariy_dlya_kofemashin") == "kitchen"  # подстрока
    unknown = alser._group("podarochniye_sertifikatiy")
    assert unknown == "other"


def test_alser_parse(alser_data):
    products = alser.parse(alser_data, "computers")
    raw = alser_data["data"]["products"]
    assert len(products) == len(raw)
    first = products[0]
    assert first.shop == "alser"
    assert first.sku == raw[0]["sku"]
    assert first.price == int(raw[0]["price"])
    assert first.url == raw[0]["link_url"]
    assert all(p.old_price is None or p.old_price > p.price for p in products)
    assert any(p.old_price for p in products)


def test_alser_groups_cover_all_groups():
    assert {g for _, g in ALSER_GROUPS} <= {"phones", "computers", "tv", "home", "kitchen", "beauty"}
