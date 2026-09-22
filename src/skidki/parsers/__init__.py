"""Парсеры магазинов. У каждого модуля: SHOP и async fetch(context, config).

REGISTRY — только включённые парсеры. Каркасы с ENABLED=False (kaspi, wb, ozon,
satu, dns) возвращают пустой список; в реестре они засчитывались бы обходом
как поломка («0 позиций»), а /status и сторож показывали бы их как
«обходов не было».
"""

from . import alser, dns, evrika, kaspi, mechta, ozon, satu, shopkz, sulpak, technodom, wb

ALL_PARSERS = {
    module.SHOP: module
    for module in (mechta, evrika, shopkz, sulpak, technodom, alser, kaspi, wb, ozon, satu, dns)
}
REGISTRY = {name: module for name, module in ALL_PARSERS.items() if getattr(module, "ENABLED", True)}
