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

# shop.kz: листинги /offers/<slug>/ (Битрикс, 28 карточек на страницу). Разделы —
# аналоги разделов mechta (2026-09-15); каждый замыкается на группу уведомлений.
SHOPKZ_SECTIONS: dict[str, str] = {
    "smartfony": "phones",
    "smart-chasy": "phones",
    "fitnes-braslety": "phones",
    "naushniki-i-garnitury": "phones",
    "noutbuki": "computers",
    "ultrabuki": "computers",
    "planshety": "computers",
    "monobloki": "computers",
    "nastolnye-kompyutery": "computers",
    "televizory": "tv",
    "saundbary": "tv",
    "domashnie-kinoteatry-resivery": "tv",
    "portativnye-kolonki": "tv",
    "akusticheskie-sistemy-i-kolonki": "tv",
    "stiralnye-mashiny": "home",
    "pylesosy": "home",
    "konditsionery": "home",
    "uvlazhniteli-i-ochistiteli-vozdukha": "home",
    "obogrevateli": "home",
    "vodonagrevateli": "home",
    "utyugi-otparivateli": "home",
    "kholodilniki": "kitchen",
    "morozilniki": "kitchen",
    "posudomoechnye-mashiny": "kitchen",
    "kofevarki-kofemashiny": "kitchen",
    "kofemolki": "kitchen",
    "chayniki-termopoty": "kitchen",
    "mikrovolnovye-pechi": "kitchen",
    "blendery-sokovyzhimalki": "kitchen",
    "tostery-gril": "kitchen",
    "vafelnitsy-blinnitsy": "kitchen",
    "plity": "kitchen",
    "vstraivaemye-dukhovki": "kitchen",
    "elektropechi": "kitchen",
    "vytyazhki": "kitchen",
    "elektrobritvy-epilyatory": "beauty",
    "feny-elektroshchiptsy": "beauty",
    "mashinki-dlya-strizhki-trimmery": "beauty",
    "massazhery": "beauty",
}

# sulpak.kz: категории каталога /f/<className>/ (первая страница — SSR, далее
# AJAX /Filter/LoadProducts). Классы — из меню sulpak, аналоги разделов mechta.
SULPAK_CATEGORIES: dict[str, str] = {
    "smartfoniy": "phones",
    "smart_chasiy": "phones",
    "fitnes_brasletiy": "phones",
    "naushniki": "phones",
    "planshetiy": "computers",
    "noutbuki": "computers",
    "monobloki": "computers",
    "sistemniye_bloki": "computers",
    "monitoriy": "computers",
    "led_oled_televizoriy": "tv",
    "saundbariy": "tv",
    "domashnie_kinoteatriy": "tv",
    "smart_kolonki_umniye_kolonki": "tv",
    "kompyuterniye_kolonki": "tv",
    "muziykalniye_centriy": "tv",
    "stiralniye_mashiniy": "home",
    "stiralno_sushilniye_kolonniy": "home",
    "piylesosiy": "home",
    "robotiy_piylesosiy": "home",
    "kondicioneriy": "home",
    "uvlazhniteli": "home",
    "obogrevatelniye_priboriy": "home",
    "protochniye_vodonagrevateli": "home",
    "utyugi": "home",
    "otparivateli": "home",
    "holodilniki": "kitchen",
    "morozilniki_i_lari": "kitchen",
    "posudomoechniye_mashiniy": "kitchen",
    "vstraivaemiye_posudomoechniye_mashiniy": "kitchen",
    "kofemashiniy": "kitchen",
    "kofevarki_espresso": "kitchen",
    "kofevarki_gejzerniye": "kitchen",
    "elektrochajniki": "kitchen",
    "mutivarka": "kitchen",
    "mikrovolnoviye_pechi": "kitchen",
    "kuhonniye_kombajniy": "kitchen",
    "stacionarniye_blenderiy": "kitchen",
    "sokoviyzhimalki": "kitchen",
    "plitiy": "kitchen",
    "vstraivaemiye_gazoviye_poverhnosti": "kitchen",
    "duhoviye_shkafiy": "kitchen",
    "paroviye_shkafiy": "kitchen",
    "viytyazhki": "kitchen",
    "britviy_i_epilyatoriy": "beauty",
    "epilyatoriy": "beauty",
    "fen_shchetki": "beauty",
    "stajleriy": "beauty",
    "strizhka_volos": "beauty",
    "masszh_i_spa": "beauty",
}

# technodom.kz: API каталога отдаёт товары всей ветки по верхнему узлу, поэтому
# обходят 6 корней (разведка 2026-09-15). sort=discount:desc — легальная
# сортировка API (разрешены created_at|price|rating|score|discount), скидочные
# позиции идут первыми.
TECHNODOM_ROOTS: dict[str, str] = {
    "smartfony-i-gadzhety": "phones",
    "noutbuki-i-komp-jutery": "computers",
    "tv-audio-foto-video": "tv",
    "bytovaja-tehnika": "home",
    "tehnika-dlja-kuhni": "kitchen",
    "krasota-i-zdorov-e": "beauty",
}


# kaspi.kz — категории маркетплейса (аналоги разделов mechta).
# Отключены по умолчанию (kaspi.ENABLED=False), включаются для среза «честной цены».
KASPI_CATEGORIES: dict[str, str] = {
    "smartphones": "phones",
    "smart-chasy": "phones",
    "naushniki": "phones",
    "noutbuki": "computers",
    "planshety": "computers",
    "televizory": "tv",
    "stiralnye-mashiny": "home",
    "pylesosy": "home",
    "kholodilniki": "kitchen",
    "mikrovolnovye-pechi": "kitchen",
}

# alser.kz: группы по подстрокам keyword категории (сайтмап отдаёт ~170
# /c/<keyword>/; часть ключей на казахском — покрываются их подстроками).
# Не подошедшие никуда уходят в «Прочее» (услуги, ПО, инструменты…).
ALSER_GROUPS: tuple[tuple[str, str], ...] = (
    ("smartfon", "phones"), ("smart-chasy", "phones"), ("smart-chasi", "phones"),
    ("naushnik", "phones"), ("fitnes-braslet", "phones"),
    ("barlyk-fitnes-bilezikter", "phones"),
    ("mobilny", "phones"), ("chehly-dlja-telefonov", "phones"),
    ("mobilnye-telefony", "phones"), ("smartfony", "phones"), ("klakkaptar", "phones"),
    ("nakladnye", "phones"), ("garnitury", "phones"), ("akkumulyator", "phones"),
    ("noutbuk", "computers"), ("kompyuter", "computers"), ("planshet", "computers"),
    ("monitor", "computers"), ("monoblok", "computers"), ("sistemny", "computers"),
    ("mysh", "computers"), ("klaviatur", "computers"), ("kabel", "computers"),
    ("marshrutizator", "computers"), ("wi-fi", "computers"), ("printery", "computers"),
    ("mfu", "computers"), ("chernila", "computers"), ("proektor", "computers"),
    ("kronshteyn", "computers"), ("usb", "computers"), ("ssd", "computers"),
    ("videokart", "computers"), ("operativnaya-pamyat", "computers"),
    ("igrovye-kresla", "computers"), ("igrovye-stoly", "computers"),
    ("igrovye-myshi", "computers"), ("igrovye-kovriki", "computers"),
    ("televizor", "tv"), ("saundbar", "tv"), ("saunbary", "tv"), ("kinoteatr", "tv"),
    ("kolonk", "tv"), ("pult", "tv"), ("tv-tiuner", "tv"), ("media", "tv"),
    ("lg-tv", "tv"), ("samsung-tv", "tv"), ("tcl-tv", "tv"), ("nastrojka-tv", "tv"),
    ("stiraln", "home"), ("pilesos", "home"), ("pylesos", "home"),
    ("kondicioner", "home"), ("uvlazhnitel", "home"), ("ochistitel", "home"),
    ("obogrevatel", "home"), ("vodonagrevatel", "home"), ("boyler", "home"),
    ("utjug", "home"), ("utyug", "home"), ("otparivatel", "home"), ("shvabr", "home"),
    ("parogenerator", "home"), ("sushil", "home"), ("ventiljator", "home"),
    ("konvektor", "home"), ("zylytkystar", "home"), ("sorgystar", "home"),
    ("mzdatkyspen", "home"), ("dreame", "home"),
    ("holodilnik", "kitchen"), ("morozil", "kitchen"), ("posudomoech", "kitchen"),
    ("kofemashin", "kitchen"), ("kofevark", "kitchen"), ("kofemolk", "kitchen"),
    ("chajnik", "kitchen"), ("elchainik", "kitchen"), ("termopot", "kitchen"),
    ("multivark", "kitchen"), ("multipekar", "kitchen"), ("mikrovolnov", "kitchen"),
    ("kuhon", "kitchen"), ("blender", "kitchen"), ("sokovyzhimalk", "kitchen"),
    ("sokovijzhimalk", "kitchen"), ("plita", "kitchen"), ("plity", "kitchen"),
    ("duhovk", "kitchen"), ("vytyazhk", "kitchen"), ("viytyazhk", "kitchen"),
    ("toster", "kitchen"), ("gril", "kitchen"), ("kazan", "kitchen"),
    ("myasorubk", "kitchen"), ("mjasorubki", "kitchen"), ("hlebopech", "kitchen"),
    ("sushilki-dlya-produktov", "kitchen"), ("toazytkystar", "kitchen"),
    ("ydys-zugystar", "kitchen"), ("poverhnost", "kitchen"),
    ("side-by-side", "kitchen"), ("aksessuary-dlja-kuhni", "kitchen"),
    ("duhovye-shkafy", "kitchen"),
    ("britv", "beauty"), ("epilyator", "beauty"), ("fen-dlya", "beauty"),
    ("feny", "beauty"), ("stajler", "beauty"), ("strizhk", "beauty"),
    ("trimmer", "beauty"), ("massazh", "beauty"), ("masszh", "beauty"),
    ("zubn", "beauty"), ("irrigator", "beauty"), ("vesy", "beauty"),
    ("vyprjamitel", "beauty"),
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
