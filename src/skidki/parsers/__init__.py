"""Парсеры магазинов. У каждого модуля: SHOP и async fetch(context, config)."""

from . import evrika, mechta

REGISTRY = {mechta.SHOP: mechta, evrika.SHOP: evrika}
