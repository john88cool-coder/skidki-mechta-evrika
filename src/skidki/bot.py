"""Слушатель Telegram: кнопки и команды настройки групп уведомлений.

Обход (skidki crawl) запускается раз в 2 часа и на нажатия кнопок ответить не
может — это делает отдельный процесс, работающий, пока ПК включён (задача
Планировщика skidki-bot, deploy/install_bot_task.ps1). Принимает только чат
владельца (TELEGRAM_CHAT_ID); остальным не отвечает вовсе.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import time
from html import escape
from pathlib import Path

import httpx

from .config import GROUPS
from .item_watch import ItemLookup, NoLookup, decode_payload
from .notify import inline_keyboard
from .parsers import REGISTRY
from .report import SHOP_LABELS, format_groups_menu, format_status, group_label, tenge
from .storage import (
    WatchEntry,
    add_watch,
    confirm_item_watch_draft,
    connect,
    create_item_watch_draft,
    delete_item_watch_draft,
    find_product,
    get_item_watch_draft,
    last_successful_crawl,
    list_item_watches,
    list_watches,
    muted_groups,
    now,
    previous_item_count,
    queue_size,
    remove_item_watch,
    remove_watch,
    search_products,
    toggle_group,
)

log = logging.getLogger("skidki.bot")

HELP = (
    "Команды:\n"
    "/groups — какие группы присылать в сводках\n"
    "/status — когда были обходы и сколько находок в очереди\n"
    "/search <запрос> — найти товар в базе по лучшей цене\n"
    "/watch <запрос> <макс_цена> — уведомлять при цене не выше порога\n"
    "/watches — список активных подписок на цену"
)
COMMANDS = [
    {"command": "groups", "description": "Группы уведомлений"},
    {"command": "status", "description": "Состояние обходов"},
    {"command": "search", "description": "Поиск товара по базе"},
    {"command": "watch", "description": "Подписка на целевую цену"},
    {"command": "watches", "description": "Активные подписки"},
]

_PRICE_TOKEN_RE = re.compile(r"^(\d[\d_\s]*)(к|k|тыс)?$", re.I)


def _parse_watch_args(raw_arg: str) -> tuple[str, int] | None:
    # tenge() печатает «450 000 ₸» — с пробелом перед ₸ и внутри числа.
    # Хвостовые ₸ снимаем до rsplit, иначе парсер отвергает собственный формат
    # бота. Граница split рвёт число («…450 | 000»): если цена — ровно
    # последний разряд «000», присоединяем предыдущую трёхзначную группу.
    raw_arg = raw_arg.strip().rstrip("₸").strip()
    parts = raw_arg.rsplit(maxsplit=1)
    if len(parts) != 2:
        return None
    query, raw_price = parts[0].strip(), parts[1].strip()
    m = _PRICE_TOKEN_RE.match(raw_price)
    if query and m:
        value = int(re.sub(r"[\s_]", "", m.group(1)))
        if m.group(2):
            value *= 1_000
        if value > 0:
            return (query, value)
    head, _, tail = query.rpartition(" ")
    if head and raw_price == "000" and len(tail) == 3 and tail.isdigit() and int(tail):
        return (head, int(tail) * 1000)
    return None


def _format_watches_view(
    watches: list[WatchEntry], item_watches: list | None = None
) -> tuple[str, list[list[tuple[str, str]]]]:
    item_watches = item_watches or []
    if not watches and not item_watches:
        return (
            "🎯 <b>Подписок пока нет.</b>\n"
            "Пример: <code>/watch iPhone 16 450к</code>",
            [],
        )
    lines = ["🎯 <b>Активные подписки на цену:</b>"]
    buttons: list[list[tuple[str, str]]] = []
    for w in watches:
        lines.append(f"• <b>{escape(w.query)}</b> — до {tenge(w.max_price)}")
        label = w.query if len(w.query) <= 22 else w.query[:21] + "…"
        buttons.append([(f"❌ {label} (≤ {tenge(w.max_price)})", f"unwatch:{w.id}")])
    if item_watches:
        # Точные цели из карточки: свой префикс удаления unwi: (не unwatch:).
        lines.append("🛒 <b>Точные товары:</b>")
        for w in item_watches:
            lines.append(
                f"• [{SHOP_LABELS.get(w.shop, w.shop)}] <code>{escape(w.sku)}</code> — до {tenge(w.max_price)}"
            )
            label = w.sku if len(w.sku) <= 22 else w.sku[:21] + "…"
            buttons.append([(f"❌ {label} (≤ {tenge(w.max_price)})", f"unwi:{w.id}")])
    return "\n".join(lines), buttons


def _format_search_results(query: str, items: list) -> str:
    if not items:
        return f"🔎 По запросу «<b>{escape(query)}</b>» в базе ничего не найдено."
    lines = [f"🔎 <b>Результаты по запросу «{escape(query)}»:</b>"]
    for p in items:
        stock = "" if p.in_stock else " <i>(нет в наличии)</i>"
        old = f" (было {tenge(p.old_price)})" if p.old_price and p.old_price > p.price else ""
        lines.append(
            f"• [{escape(SHOP_LABELS.get(p.shop, p.shop))}] <a href=\"{escape(p.url, quote=True)}\">{escape(p.title)}</a> — "
            f"<b>{tenge(p.price)}</b>{old}{stock}"
        )
    return "\n".join(lines)


def _handle_item_target(
    api: Api, chat_id: int, token: str, db_path: Path | None, lookup: ItemLookup
) -> None:
    """Черновик точной цели из карточки (/watchitem или /start w2_...).

    Подтверждение — только по inline-кнопке; до нажатия цель не создаётся.
    """
    target = decode_payload(token)
    if target is None:
        api.call(
            "sendMessage",
            chat_id=chat_id,
            text="Не удалось разобрать код товара — скопируйте команду целиком из карточки.",
        )
        return
    with connect(db_path) as conn:
        draft = create_item_watch_draft(conn, target.shop, target.sku, target.max_price)
    text = (
        "🎯 <b>Цель по товару</b>\n"
        f"Магазин: {SHOP_LABELS.get(target.shop, target.shop)}\n"
        f"Артикул: <code>{escape(target.sku)}</code>\n"
        f"Уведомить при цене до <b>{tenge(target.max_price)}</b>\n\n"
        "Уведомление придёт в личном боте после подтверждения. Черновик действует 15 минут."
    )
    api.call(
        "sendMessage",
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=inline_keyboard([[("✅ Подтвердить", f"wi:{draft.id}")]]),
    )


def _confirm_item_draft(
    api: Api,
    chat_id: int,
    message: dict,
    query: dict,
    raw_id: str,
    db_path: Path | None,
    lookup: ItemLookup,
) -> None:
    """Нажатие wi:<id>: подтверждение черновика транзакционно, идемпотентно.

    Товар ищется в локальной базе, при отсутствии — через адаптер задачи 9.
    Без товара черновик сохраняется: причина и кнопка «Повторить».
    """
    if not re.fullmatch(r"[0-9a-fA-F]{4,16}", raw_id):
        api.call("answerCallbackQuery", callback_query_id=query["id"], text="Черновик не найден")
        return
    moment = now()
    outcome, watch = "missing", None
    draft = None
    product = None
    with connect(db_path) as conn:
        draft = get_item_watch_draft(conn, raw_id)
        if draft is not None and draft.expired(moment):
            delete_item_watch_draft(conn, raw_id)
            outcome = "expired"
            draft = None
        elif draft is not None:
            product = find_product(conn, draft.shop, draft.sku)
    if draft is not None and product is None:
        try:
            product = lookup.lookup(draft.shop, draft.sku)
        except Exception as exc:  # noqa: BLE001 — адаптер задачи 9 может обращаться к сети
            log.warning("item lookup %s: %s", draft.shop, type(exc).__name__)
            product = None
    if draft is not None:
        if product is None:
            # Товар не подтвердился ни в базе, ни по индексу магазина:
            # черновик сохранён, причина и кнопка «Повторить».
            outcome = "no-product"
        else:
            with connect(db_path) as conn:
                confirmed = confirm_item_watch_draft(conn, raw_id, at=moment)
            if confirmed is not None:
                outcome, watch = "confirmed", confirmed

    if outcome == "confirmed" and watch is not None:
        api.call(
            "editMessageText",
            chat_id=chat_id,
            message_id=message.get("message_id"),
            text=(
                "✅ <b>Цель сохранена</b>\n"
                f"Магазин: {SHOP_LABELS.get(watch.shop, watch.shop)}\n"
                f"Артикул: <code>{escape(watch.sku)}</code>\n"
                f"Уведомлю при цене до <b>{tenge(watch.max_price)}</b>."
            ),
            parse_mode="HTML",
        )
        api.call("answerCallbackQuery", callback_query_id=query["id"], text="Цель сохранена")
    elif outcome == "expired":
        api.call(
            "editMessageText",
            chat_id=chat_id,
            message_id=message.get("message_id"),
            text="Черновик истёк — повторите команду из карточки товара.",
            parse_mode="HTML",
        )
        api.call("answerCallbackQuery", callback_query_id=query["id"], text="Черновик истёк")
    elif outcome == "no-product":
        api.call(
            "editMessageText",
            chat_id=chat_id,
            message_id=message.get("message_id"),
            text="Товар пока не удалось найти в базе — попробуйте позже.",
            parse_mode="HTML",
            reply_markup=inline_keyboard([[("🔁 Повторить", f"wi:{raw_id}")]]),
        )
        api.call("answerCallbackQuery", callback_query_id=query["id"], text="Товар не найден")
    else:
        # идемпотентный повтор или неизвестный id — состояние не меняем
        api.call(
            "answerCallbackQuery",
            callback_query_id=query["id"],
            text="Уже подтверждено или черновик истёк",
        )


class Api:
    """Тонкая обёртка над Bot API. В логи — только имя метода: в URL токен."""

    def __init__(self, token: str, timeout: float = 20.0) -> None:
        self._base = f"https://api.telegram.org/bot{token}"
        self._timeout = timeout

    def call(self, method: str, http_timeout: float | None = None, **params) -> dict:
        response = httpx.post(
            f"{self._base}/{method}", json=params, timeout=http_timeout or self._timeout
        )
        data = response.json()
        if not data.get("ok"):
            log.warning("%s: %s", method, data.get("description"))
        return data


def _send_menu(api: Api, chat_id: int, db_path: Path | None) -> None:
    with connect(db_path) as conn:
        muted = muted_groups(conn)
    text, buttons = format_groups_menu(muted)
    api.call(
        "sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
        reply_markup=inline_keyboard(buttons),
    )


def _status_text(db_path: Path | None) -> str:
    with connect(db_path) as conn:
        crawls = [
            (shop, last_successful_crawl(conn, shop), previous_item_count(conn, shop))
            for shop in REGISTRY
        ]
        return format_status(crawls, queue_size(conn), muted_groups(conn))


def handle(
    update: dict,
    api: Api,
    owner_chat_id: str,
    db_path: Path | None = None,
    item_lookup: ItemLookup | None = None,
) -> None:
    """Одно обновление Telegram: нажатие кнопки или команда владельца."""
    query = update.get("callback_query")
    if query:
        message = query.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        if str(chat_id) != str(owner_chat_id):
            return
        data = query.get("data") or ""
        key = data.removeprefix("toggle:")
        if data == "groups":
            _send_menu(api, chat_id, db_path)
            api.call("answerCallbackQuery", callback_query_id=query["id"])
        elif data.startswith("toggle:") and key in GROUPS:
            with connect(db_path) as conn:
                now_muted = toggle_group(conn, key)
                muted = muted_groups(conn)
            text, buttons = format_groups_menu(muted)
            api.call(
                "editMessageText", chat_id=chat_id, message_id=message.get("message_id"),
                text=text, parse_mode="HTML", reply_markup=inline_keyboard(buttons),
            )
            api.call(
                "answerCallbackQuery", callback_query_id=query["id"],
                text=f"{group_label(key)}: {'выключено' if now_muted else 'включено'}",
            )
        elif data.startswith("unwatch:"):
            raw_id = data.removeprefix("unwatch:")
            removed = False
            if raw_id.isdigit():
                with connect(db_path) as conn:
                    removed = remove_watch(conn, int(raw_id))
                    watches = list_watches(conn)
                    item_watches = list_item_watches(conn)
                text, buttons = _format_watches_view(watches, item_watches)
                markup = inline_keyboard(buttons) if buttons else {"inline_keyboard": []}
                api.call(
                    "editMessageText",
                    chat_id=chat_id,
                    message_id=message.get("message_id"),
                    text=text,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
            api.call(
                "answerCallbackQuery",
                callback_query_id=query["id"],
                text="Подписка удалена" if removed else "Уже удалена",
            )
        elif data.startswith("wi:"):
            _confirm_item_draft(
                api, chat_id, message, query, data.removeprefix("wi:"), db_path,
                item_lookup or NoLookup(),
            )
        elif data.startswith("unwi:"):
            raw_id = data.removeprefix("unwi:")
            removed = False
            if raw_id.isdigit():
                with connect(db_path) as conn:
                    removed = remove_item_watch(conn, int(raw_id))
                    watches = list_watches(conn)
                    item_watches = list_item_watches(conn)
                text, buttons = _format_watches_view(watches, item_watches)
                markup = inline_keyboard(buttons) if buttons else {"inline_keyboard": []}
                api.call(
                    "editMessageText",
                    chat_id=chat_id,
                    message_id=message.get("message_id"),
                    text=text,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
            api.call(
                "answerCallbackQuery",
                callback_query_id=query["id"],
                text="Подписка удалена" if removed else "Уже удалена",
            )
        else:
            api.call("answerCallbackQuery", callback_query_id=query["id"])
        return

    message = update.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    if chat_id is None or str(chat_id) != str(owner_chat_id):
        return
    raw_text = (message.get("text") or "").strip()
    words = raw_text.split()
    command = words[0].split("@")[0].lower() if words else ""
    arg = raw_text.split(maxsplit=1)[1] if len(raw_text.split(maxsplit=1)) > 1 else ""
    lookup = item_lookup or NoLookup()
    if command == "/watchitem":
        tokens = arg.split()
        _handle_item_target(api, chat_id, tokens[0] if tokens else "", db_path, lookup)
    elif command == "/start" and len(words) > 1 and words[1].startswith("w2_"):
        # /start w2_… — цель из карточки; обрабатывается ДО общего /start.
        _handle_item_target(api, chat_id, words[1], db_path, lookup)
    elif command in ("/start", "/groups", "/группы"):
        _send_menu(api, chat_id, db_path)
    elif command == "/status":
        api.call("sendMessage", chat_id=chat_id, text=_status_text(db_path), parse_mode="HTML")
    elif command in ("/search", "/поиск"):
        if not arg:
            api.call("sendMessage", chat_id=chat_id, text="Укажите запрос: /search iPhone 16")
            return
        with connect(db_path) as conn:
            found = search_products(conn, arg)
        api.call(
            "sendMessage",
            chat_id=chat_id,
            text=_format_search_results(arg, found),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    elif command == "/watch":
        parsed = _parse_watch_args(arg)
        if not parsed:
            api.call(
                "sendMessage",
                chat_id=chat_id,
                text="Формат: <code>/watch запрос макс_цена</code>\nПример: <code>/watch iPhone 16 450к</code>",
                parse_mode="HTML",
            )
            return
        q_text, max_price = parsed
        with connect(db_path) as conn:
            entry = add_watch(conn, q_text, max_price)
        api.call(
            "sendMessage",
            chat_id=chat_id,
            text=f"🎯 Подписка #{entry.id} добавлена: <b>{escape(entry.query)}</b> до <b>{tenge(entry.max_price)}</b>",
            parse_mode="HTML",
        )
    elif command == "/watches":
        with connect(db_path) as conn:
            watches = list_watches(conn)
            item_watches = list_item_watches(conn)
        text, buttons = _format_watches_view(watches, item_watches)
        extra = {"reply_markup": inline_keyboard(buttons)} if buttons else {}
        api.call("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML", **extra)
    else:
        api.call("sendMessage", chat_id=chat_id, text=HELP)


def run(token: str, owner_chat_id: str, db_path: Path | None = None, poll_timeout: int = 50) -> None:
    """Длинный опрос getUpdates без конца; сбои сети — пауза и повтор."""
    api = Api(token)
    try:
        api.call("setMyCommands", commands=COMMANDS)
    except httpx.HTTPError as exc:
        log.warning("setMyCommands: %s", type(exc).__name__)
    log.info("слушатель запущен")
    offset: int | None = None
    while True:
        params: dict = {"timeout": poll_timeout, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            params["offset"] = offset
        try:
            data = api.call("getUpdates", http_timeout=poll_timeout + 15, **params)
        except (httpx.HTTPError, ValueError) as exc:
            # Не str(exc): в сообщениях httpx — URL с токеном.
            log.warning("getUpdates: %s", type(exc).__name__)
            time.sleep(10)
            continue
        for update in data.get("result") or []:
            offset = update["update_id"] + 1
            try:
                handle(update, api, owner_chat_id, db_path)
            except sqlite3.OperationalError as exc:
                log.warning("база занята: %s", exc)
            except httpx.HTTPError as exc:
                log.warning("Telegram: %s", type(exc).__name__)
            except Exception:  # noqa: BLE001 — одно обновление не должно ронять слушателя
                log.exception("обновление %s", update.get("update_id"))
        if not data.get("ok"):
            time.sleep(10)
