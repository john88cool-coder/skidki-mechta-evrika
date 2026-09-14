"""Настройки: разделы магазинов, пороги сигналов, правила владельца, Telegram."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .models import Product

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path, environ=os.environ) -> None:
    """KEY=VALUE из .env — для запуска на домашнем ПК (Планировщик Windows).

    Переменные окружения важнее файла: заданное явно не перезаписывается.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        if value:
            environ.setdefault(key.strip(), value)


_load_dotenv(ROOT / ".env")

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

# Группы уведомлений — разделы mechta из исходных ссылок владельца. Сводка
# раскладывает находки по ним, каждую группу можно выключить (/groups).
GROUPS: dict[str, str] = {
    "phones": "📱 Смартфоны и гаджеты",
    "computers": "💻 Ноутбуки и компьютеры",
    "tv": "📺 ТВ, аудио и видео",
    "home": "🏠 Техника для дома",
    "kitchen": "🍳 Кухонная техника",
    "beauty": "💄 Красота и здоровье",
}
OTHER_GROUP = "other"
OTHER_LABEL = "🗂 Прочее"

MECHTA_GROUPS: dict[str, str] = {
    "smartfony-i-gadjety": "phones",
    "tehnika-dlya-doma": "home",
    "kuhonnaya-tehnika": "kitchen",
    "tv-audio-video": "tv",
    "noutbuki-i-kompyutery": "computers",
    "krasota-i-zdorove": "beauty",
}

# evrika → те же группы. Ключ — id категории evrika; группа листа — по
# ближайшему предку (или самому листу) из словаря. Раскладка повторяет меню
# mechta (2026-09-14): стиральные и сушильные машины, паровые шкафы, пылесосы,
# климат — «Техника для дома»; холодильники, плиты, посудомойки, встраиваемая
# и мелкая кухонная техника, кофе — «Кухонная».
EVRIKA_GROUPS: dict[int, str] = {
    171: "phones",
    71: "computers",
    106: "tv",
    244: "kitchen",                         # «Бытовая техника»: по умолчанию кухня…
    249: "home", 250: "home", 254: "home",  # …кроме стиральных, сушильных, паровых шкафов
    248: "home",                            # климатическая техника
    355: "home",                            # аксессуары для стиральных машин
    75: "home",                             # «Мелкобытовая»: по умолчанию дом…
    80: "kitchen", 644: "kitchen",          # …кроме мелкой кухонной и кофе
    709: "kitchen",                         # панели для мультипекаря и гриля
    108: "beauty",
}


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
    # Находок в одной сводке (решение владельца 2026-09-14: одна сводка по
    # группам вместо 8 отдельных карточек); остальные — следующими обходами.
    max_alerts: int = 40
    # Сколько находка ждёт в очереди, если в обход не поместилась: сутки —
    # 12 обходов по max_alerts. Старше — уже не новость.
    queue_hours: int = 24
    # «Скидка магазина» (решение владельца 2026-09-13): от −20% к зачёркнутой
    # цене и сама цена от 20 000 ₸. На момент решения таких было ~2 400, в
    # топе — чехлы за 990 ₸ «было 19 990»; фильтр по цене режет эту мелочь.
    deal_pct: float = 20.0
    deal_min_price: int = 20_000
    # Скидка больше — ошибка цены, а не находка: весы за 528 ₸ «было 999 990».
    deal_max_pct: float = 90.0


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
    deal_pct: float | None = None
    deal_min_price: int | None = None
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
        deal_pct=data.get("deal_pct"),
        deal_min_price=int(data["deal_min_price"]) if data.get("deal_min_price") else None,
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
