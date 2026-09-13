"""Модель товара — общая для всех магазинов."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    """Одна позиция каталога в момент обхода.

    `old_price` — зачёркнутая цена магазина. Хранится и показывается только
    справочно: сигналом она не является (handoff §5 — магазины рисуют скидку
    от завышенной цены).
    """

    shop: str
    sku: str
    title: str
    price: int
    url: str
    brand: str | None = None
    category: str | None = None
    old_price: int | None = None
    in_stock: bool = True
    stock_note: str | None = None

    @property
    def identity(self) -> str:
        return f"{self.shop}:{self.sku}"

    @property
    def shop_discount_pct(self) -> int | None:
        if self.old_price and self.old_price > self.price:
            return round((self.old_price - self.price) / self.old_price * 100)
        return None


class PartialCrawl(Exception):
    """Магазин обошёлся не целиком: часть разделов или страниц не загрузилась.

    Несёт собранные позиции: они пишутся в историю, а обход помечается
    неуспешным. Иначе 50 позиций вместо 7 600 выглядели бы как «всё хорошо» —
    ровно так прошёл смок mechta 2026-09-13, пока Cloudflare резал запросы.
    """

    def __init__(self, products: list[Product], reason: str) -> None:
        super().__init__(reason)
        self.products = products


def new_products(products: Iterable[Product], seen: set[str]) -> list[Product]:
    """Позиции с ещё не встречавшимся identity; `seen` пополняется на месте.

    Одна позиция — одно наблюдение за обход: товары переставляются между
    страницами во время обхода и приходят дважды (урок gpu-deals, paging.py),
    а evrika к тому же показывает товар в нескольких листовых категориях.
    """
    fresh: list[Product] = []
    for product in products:
        if product.identity in seen:
            continue
        seen.add(product.identity)
        fresh.append(product)
    return fresh
