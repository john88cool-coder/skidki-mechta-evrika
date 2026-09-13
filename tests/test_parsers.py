import json

import pytest
from conftest import FIXTURES

from skidki.config import EVRIKA_ROOTS
from skidki.parsers import evrika, mechta


@pytest.fixture(scope="module")
def mechta_data():
    return json.loads((FIXTURES / "mechta_products.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def evrika_data():
    return evrika.next_data((FIXTURES / "evrika_category.html").read_text(encoding="utf-8"))


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
