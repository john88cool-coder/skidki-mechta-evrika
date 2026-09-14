"""Группы уведомлений: раскладка категорий, хранение, выключение."""

import json
import sqlite3

import pytest
from conftest import FIXTURES, T0, product

from skidki import storage
from skidki.config import EVRIKA_GROUPS, EVRIKA_ROOTS, GROUPS
from skidki.parsers import evrika, mechta


@pytest.fixture(scope="module")
def evrika_data():
    return evrika.next_data((FIXTURES / "evrika_category.html").read_text(encoding="utf-8"))


def test_evrika_groups_follow_mechta_menu(evrika_data):
    tree = evrika.menu_tree(evrika_data)
    groups = evrika.category_groups(tree, EVRIKA_GROUPS)
    leaves = evrika.leaf_categories(tree, {cid for cid, _ in EVRIKA_ROOTS})
    assert all(cid in groups for cid, _ in leaves)
    assert set(groups.values()) <= set(GROUPS)
    expected = {
        249: "home",      # стиральные машины
        254: "home",      # паровые шкафы
        246: "kitchen",   # холодильники
        257: "kitchen",   # варочные панели (встраиваемая)
        269: "home",      # кондиционеры
        160: "home",      # пылесосы
        169: "kitchen",   # кухонные комбайны
        166: "kitchen",   # кофемашины
        709: "kitchen",   # панели для мультипекаря
        307: "home",      # комплектующие для пылесосов
        154: "beauty",    # фены
        310: "phones",    # смарт-часы
        207: "computers", # ноутбуки
        228: "tv",        # телевизоры
    }
    assert {cid: groups[cid] for cid in expected} == expected


def test_parsers_tag_products_with_group(evrika_data):
    items, _ = evrika.parse_products(evrika_data, "phones")
    assert items and all(p.group == "phones" for p in items)
    data = json.loads((FIXTURES / "mechta_products.json").read_text(encoding="utf-8"))
    assert all(p.group == "tv" for p in mechta.parse(data, "tv"))


def test_group_survives_storage(conn):
    storage.save_products(conn, [product(60_000, old_price=100_000, group="kitchen")], T0)
    [found] = storage.current_deals(conn, 20, 20_000, 90, limit=5)
    assert found.group == "kitchen"
    # Наблюдение без группы не стирает известную.
    storage.save_products(conn, [product(60_000, old_price=100_000)], T0)
    [again] = storage.current_deals(conn, 20, 20_000, 90, limit=5)
    assert again.group == "kitchen"


def test_migration_adds_group_column_to_old_db(tmp_path):
    db = tmp_path / "old.sqlite3"
    old = sqlite3.connect(db)
    old.execute("""CREATE TABLE products (identity TEXT PRIMARY KEY, shop TEXT NOT NULL,
                   title TEXT NOT NULL, brand TEXT, category TEXT, url TEXT NOT NULL,
                   first_seen TEXT NOT NULL, last_seen TEXT NOT NULL)""")
    old.commit()
    old.close()
    with storage.connect(db) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(products)")}
        assert "grp" in columns
        storage.save_products(conn, [product(50_000, group="tv")], T0)


def test_toggle_group(conn):
    assert storage.toggle_group(conn, "tv") is True
    assert storage.muted_groups(conn) == {"tv"}
    assert storage.toggle_group(conn, "tv") is False
    assert storage.muted_groups(conn) == set()
