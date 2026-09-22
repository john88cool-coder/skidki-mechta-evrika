"""Парсеры магазинов. У каждого модуля: SHOP и async fetch(context, config)."""

from . import alser, dns, evrika, kaspi, mechta, ozon, satu, shopkz, sulpak, technodom, wb

REGISTRY = {
    mechta.SHOP: mechta,
    evrika.SHOP: evrika,
    shopkz.SHOP: shopkz,
    sulpak.SHOP: sulpak,
    technodom.SHOP: technodom,
    alser.SHOP: alser,
    kaspi.SHOP: kaspi,
    wb.SHOP: wb,
    ozon.SHOP: ozon,
    satu.SHOP: satu,
    dns.SHOP: dns,
}
