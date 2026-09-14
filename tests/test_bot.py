"""Слушатель Telegram: кнопки групп и команды — только от владельца."""

import pytest

from skidki import bot, storage
from skidki.config import GROUPS

OWNER = "366256716"


class FakeApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def call(self, method, http_timeout=None, **params):
        self.calls.append((method, params))
        return {"ok": True, "result": []}

    def methods(self) -> list[str]:
        return [method for method, _ in self.calls]


def callback(data: str, chat: str = OWNER) -> dict:
    return {"update_id": 1, "callback_query": {
        "id": "q1", "data": data, "message": {"message_id": 7, "chat": {"id": int(chat)}}}}


def message(text: str, chat: str = OWNER) -> dict:
    return {"update_id": 2, "message": {"message_id": 9, "chat": {"id": int(chat)}, "text": text}}


@pytest.fixture
def db(tmp_path):
    return tmp_path / "db.sqlite3"


def test_toggle_mutes_group_and_redraws_menu(db):
    api = FakeApi()
    bot.handle(callback("toggle:tv"), api, OWNER, db)
    with storage.connect(db) as conn:
        assert storage.muted_groups(conn) == {"tv"}
    assert api.methods() == ["editMessageText", "answerCallbackQuery"]
    edit = api.calls[0][1]
    assert edit["message_id"] == 7
    labels = [b["text"] for row in edit["reply_markup"]["inline_keyboard"] for b in row]
    assert f"🔕 {GROUPS['tv']}" in labels
    assert "выключено" in api.calls[1][1]["text"]

    bot.handle(callback("toggle:tv"), api, OWNER, db)
    with storage.connect(db) as conn:
        assert storage.muted_groups(conn) == set()


def test_strangers_are_ignored(db):
    api = FakeApi()
    bot.handle(callback("toggle:tv", chat="1"), api, OWNER, db)
    bot.handle(message("/groups", chat="1"), api, OWNER, db)
    assert api.calls == []
    with storage.connect(db) as conn:
        assert storage.muted_groups(conn) == set()


def test_groups_command_and_digest_button_send_menu(db):
    api = FakeApi()
    bot.handle(message("/groups"), api, OWNER, db)
    bot.handle(callback("groups"), api, OWNER, db)
    sends = [params for method, params in api.calls if method == "sendMessage"]
    assert len(sends) == 2 and all("Группы уведомлений" in p["text"] for p in sends)
    first_button = sends[0]["reply_markup"]["inline_keyboard"][0][0]
    assert first_button["callback_data"].startswith("toggle:")
    assert "answerCallbackQuery" in api.methods()


def test_status_command(db):
    with storage.connect(db) as conn:
        storage.record_crawl(conn, "mechta", 7_636, True)
    api = FakeApi()
    bot.handle(message("/status"), api, OWNER, db)
    [(method, params)] = api.calls
    assert method == "sendMessage"
    assert "7 636 позиций" in params["text"] and "В очереди: 0" in params["text"]


def test_unknown_input_is_harmless(db):
    api = FakeApi()
    bot.handle(callback("toggle:hack"), api, OWNER, db)
    bot.handle(message("привет"), api, OWNER, db)
    assert api.methods() == ["answerCallbackQuery", "sendMessage"]
    assert "/groups" in api.calls[1][1]["text"]
    with storage.connect(db) as conn:
        assert storage.muted_groups(conn) == set()
