from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from skidki import storage
from skidki.models import Product

FIXTURES = Path(__file__).parent / "fixtures"
T0 = datetime(2026, 9, 1, 6, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _not_in_actions(monkeypatch):
    """Тесты — как на ноутбуке: в CI выставлен GITHUB_ACTIONS, и сводка
    получала бы облачную кнопку вместо кнопки групп."""
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


@pytest.fixture
def conn(tmp_path):
    with storage.connect(tmp_path / "test.sqlite3") as connection:
        yield connection


def product(
    price: int,
    *,
    sku: str = "1",
    shop: str = "mechta",
    in_stock: bool = True,
    title: str = "Смарт-часы Тест",
    category: str = "Смарт-часы",
    old_price: int | None = None,
    group: str | None = None,
) -> Product:
    return Product(
        shop=shop,
        sku=sku,
        title=title,
        price=price,
        url=f"https://www.mechta.kz/product/{sku}/",
        category=category,
        old_price=old_price,
        in_stock=in_stock,
        group=group,
    )


def seed(conn, item: Product, hours: int, start: datetime = T0, step: int = 2) -> None:
    """Обходы каждые `step` часов с одной ценой — `hours` часов подряд."""
    for hour in range(0, hours + 1, step):
        storage.save_products(conn, [item], start + timedelta(hours=hour))
