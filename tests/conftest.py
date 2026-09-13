from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from skidki import storage
from skidki.models import Product

FIXTURES = Path(__file__).parent / "fixtures"
T0 = datetime(2026, 9, 1, 6, 0, tzinfo=UTC)


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
) -> Product:
    return Product(
        shop=shop,
        sku=sku,
        title=title,
        price=price,
        url=f"https://www.mechta.kz/product/{sku}/",
        category=category,
        in_stock=in_stock,
    )


def seed(conn, item: Product, hours: int, start: datetime = T0, step: int = 2) -> None:
    """Обходы каждые `step` часов с одной ценой — `hours` часов подряд."""
    for hour in range(0, hours + 1, step):
        storage.save_products(conn, [item], start + timedelta(hours=hour))
