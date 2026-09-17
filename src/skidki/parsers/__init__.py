"""Парсеры магазинов. У каждого модуля: SHOP и async fetch(context, config)."""

from . import alser, evrika, mechta, shopkz, sulpak, technodom

REGISTRY = {
    mechta.SHOP: mechta,
    evrika.SHOP: evrika,
    shopkz.SHOP: shopkz,
    sulpak.SHOP: sulpak,
    technodom.SHOP: technodom,
    alser.SHOP: alser,
}
