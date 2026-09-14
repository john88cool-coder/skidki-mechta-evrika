"""Слушатель Telegram: кнопки и команды настройки групп уведомлений.

Обход (skidki crawl) запускается раз в 2 часа и на нажатия кнопок ответить не
может — это делает отдельный процесс, работающий, пока ПК включён (задача
Планировщика skidki-bot, deploy/install_bot_task.ps1). Принимает только чат
владельца (TELEGRAM_CHAT_ID); остальным не отвечает вовсе.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

import httpx

from .config import GROUPS
from .notify import inline_keyboard
from .parsers import REGISTRY
from .report import format_groups_menu, format_status, group_label
from .storage import (
    connect,
    last_successful_crawl,
    muted_groups,
    previous_item_count,
    queue_size,
    toggle_group,
)

log = logging.getLogger("skidki.bot")

HELP = (
    "Команды:\n"
    "/groups — какие группы присылать в сводках\n"
    "/status — когда были обходы и сколько находок в очереди"
)
COMMANDS = [
    {"command": "groups", "description": "Группы уведомлений"},
    {"command": "status", "description": "Состояние обходов"},
]


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


def handle(update: dict, api: Api, owner_chat_id: str, db_path: Path | None = None) -> None:
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
        else:
            api.call("answerCallbackQuery", callback_query_id=query["id"])
        return

    message = update.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    if chat_id is None or str(chat_id) != str(owner_chat_id):
        return
    words = (message.get("text") or "").strip().split()
    command = words[0].split("@")[0].lower() if words else ""
    if command in ("/start", "/groups", "/группы"):
        _send_menu(api, chat_id, db_path)
    elif command == "/status":
        api.call("sendMessage", chat_id=chat_id, text=_status_text(db_path), parse_mode="HTML")
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
