"""Настройки: разделы магазинов, пороги сигналов, правила владельца, Telegram."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .models import Product

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.environ.get("SKIDKI_DB") or ROOT / "data" / "skidki.sqlite3")
RULES_PATH = Path(os.environ.get("SKIDKI_RULES") or ROOT / "rules.toml")

# mechta.kz: разделы каталога (slug из URL /section/<slug>/). Обходятся ВСЕ
# товары раздела, а не только со скидкой: сигналу «ниже медианы» нужна история
# цены до падения (решение владельца 2026-09-13). ~7 600 позиций, 153 запроса.
MECHTA_SECTIONS: tuple[str, ...] = (
    "smartfony-i-gadjety",
    "tehnika-dlya-doma",
    "kuhonnaya-tehnika",
    "tv-audio-video",
    "noutbuki-i-kompyutery",
    "krasota-i-zdorove",
)

# evrika.com: верхние категории-аналоги разделов mechta (id, slug). Товары
# отдают только листовые подкатегории (~150) — их список строится из дерева
# категорий на каждом обходе, новые подкатегории подхватываются сами.
EVRIKA_ROOTS: tuple[tuple[int, str], ...] = (
    (171, "smartfony-i-gadzhety"),
    (71, "noutbuki-i-kompyutery"),
    (106, "televizory-audio-i-video-1"),
    (244, "bytovaya-tehnika"),
    (75, "melkobytovaya-tehnika-4"),
)


@dataclass(frozen=True)
class Thresholds:
    """Пороги сигналов. Режим владельца агрессивный: лучше лишнее, чем пропущенное."""

    trend_window_days: int = 14
    # «Упало» — только при истории не короче стольких дней: медиана из пары
    # наблюдений базой не является.
    min_history_days: float = 3.0
    drop_pct: float = 7.0
    # Абсолютный минимум падения: −50% на чехле за 1 990 ₸ — не находка.
    min_drop_tenge: int = 2_000
    low_window_days: int = 30
    min_low_history_days: float = 7.0
    # «Минимум за 30 дней» — ниже прошлого минимума хотя бы на столько процентов:
    # копеечные подвижки по тысячам позиций иначе засыпали бы чат.
    low_margin_pct: float = 2.0
    # Хранение истории: окно минимума (30 дней) плюс запас.
    retention_days: int = 35
    # Обход дал меньше этой доли от прошлого — тревога о поломке.
    breakage_ratio: float = 0.5
    # Строк находок в сообщении: владелец читает с телефона, всё сообщение ≤ 10 строк.
    max_alert_lines: int = 8


def _matches(needle: str, haystack: str | None) -> bool:
    return bool(haystack) and needle.casefold() in haystack.casefold()


@dataclass(frozen=True)
class CategoryRule:
    """Правило для категории магазина (подстрока названия, без регистра)."""

    match: str
    drop_pct: float | None = None
    max_price: int | None = None


@dataclass(frozen=True)
class WatchItem:
    """Конкретный товар: подстрока названия и цена, при которой владелец берёт."""

    query: str
    max_price: int
    shop: str | None = None


@dataclass(frozen=True)
class Rules:
    """Правила владельца из rules.toml."""

    drop_pct: float | None = None
    categories: tuple[CategoryRule, ...] = ()
    watch: tuple[WatchItem, ...] = ()

    def drop_pct_for(self, category: str | None, default: float) -> float:
        for rule in self.categories:
            if rule.drop_pct is not None and _matches(rule.match, category):
                return rule.drop_pct
        return self.drop_pct if self.drop_pct is not None else default

    def targets_for(self, product: Product) -> list[int]:
        """Целевые цены, которые относятся к позиции (товар и категория)."""
        targets = [
            item.max_price
            for item in self.watch
            if (item.shop is None or item.shop == product.shop)
            and _matches(item.query, product.title)
        ]
        targets += [
            rule.max_price
            for rule in self.categories
            if rule.max_price is not None and _matches(rule.match, product.category)
        ]
        return targets


def load_rules(path: Path | None = None) -> Rules:
    """Читает rules.toml; нет файла — правил нет, работают только пороги."""
    target = path or RULES_PATH
    if not target.exists():
        return Rules()
    with target.open("rb") as handle:
        data = tomllib.load(handle)
    return Rules(
        drop_pct=data.get("drop_pct"),
        categories=tuple(
            CategoryRule(
                match=str(rule["match"]),
                drop_pct=rule.get("drop_pct"),
                max_price=int(rule["max_price"]) if rule.get("max_price") else None,
            )
            for rule in data.get("category", [])
        ),
        watch=tuple(
            WatchItem(
                query=str(item["query"]),
                max_price=int(item["max_price"]),
                shop=item.get("shop"),
            )
            for item in data.get("watch", [])
        ),
    )


def _env(name: str) -> str | None:
    return os.environ.get(name) or None


@dataclass(frozen=True)
class Settings:
    telegram_token: str | None = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: str | None = field(default_factory=lambda: _env("TELEGRAM_CHAT_ID"))
    thresholds: Thresholds = field(default_factory=Thresholds)
    # evrika отвечает 12–35 с на страницу — страницы грузятся параллельно.
    evrika_concurrency: int = field(
        default_factory=lambda: int(os.environ.get("SKIDKI_EVRIKA_CONCURRENCY", "4"))
    )
    # Бюджет времени на evrika: job в Actions ограничен, обход каждые 2 часа.
    evrika_budget_s: float = 50 * 60
    # SSR evrika не укладывается в стандартные 30 с Playwright.
    page_timeout_ms: int = 90_000


settings = Settings()
