"""Сводка по группам, меню групп и статус (сообщения Telegram)."""

from datetime import UTC, datetime

from conftest import product

from skidki.config import GROUPS
from skidki.evaluate import Signal, SignalHit, Verdict
from skidki.models import Product
from skidki.notify import inline_keyboard, split_message
from skidki.report import (
    format_digest,
    format_groups_menu,
    format_line,
    format_more,
    format_status,
    format_watchdog,
    rank,
)


def _drop(price: int, sku: str, base: int = 100_000, group: str | None = "phones") -> Verdict:
    return Verdict(
        product(price, sku=sku, group=group), [SignalHit(Signal.DROP, base=base, days=5)], reference=base
    )


def test_rank_limits_and_counts_rest():
    verdicts = [_drop(90_000 - i * 1_000, str(i)) for i in range(20)]
    shown, rest = rank(verdicts, limit=8)
    assert len(shown) == 8 and rest == 12
    assert shown[0].product.price == min(v.product.price for v in verdicts)


def test_targets_go_first():
    target = Verdict(product(59_000, sku="t"), [SignalHit(Signal.TARGET, target=60_000)])
    shown, _ = rank([_drop(50_000, "d"), target], limit=8)
    assert shown[0] is target


def test_deal_line_shows_percent_old_price_and_link():
    item = Product(
        shop="mechta", sku="1", title="Робот-пылесос Tefal RG8577WH", price=69_990,
        url="https://www.mechta.kz/product/tefal-rg8577wh/", old_price=99_990,
        stock_note="осталось мало", group="home",
    )
    first, second = format_line(Verdict(item, [SignalHit(Signal.DEAL, base=99_990)])).split("\n")
    assert first == (
        '🏷 <b>−30%</b> <a href="https://www.mechta.kz/product/tefal-rg8577wh/">'
        "Робот-пылесос Tefal RG8577WH</a>"
    )
    assert second == "└ <b>69 990 ₸</b> · <s>99 990 ₸</s> · Мечта · ⚠️ осталось мало"


def test_drop_line_shows_usual_price():
    first, second = format_line(_drop(90_000, "1")).split("\n")
    assert first.startswith("📉 <b>−10%</b>")
    assert "обычно 100 000 ₸" in second


def test_target_line_with_restock():
    verdict = Verdict(product(59_000), [SignalHit(Signal.TARGET, target=60_000),
                                        SignalHit(Signal.RESTOCK, target=60_000)])
    line = format_line(verdict)
    assert line.startswith("🎯 <b>цель ≤ 60 000 ₸</b>")
    assert "снова в наличии" in line


def test_digest_groups_in_fixed_order_with_counts():
    verdicts = [
        _drop(90_000, "a", group="kitchen"),
        _drop(85_000, "c", group="phones"),
        _drop(80_000, "b", group="phones"),
        _drop(95_000, "d", group=None),
    ]
    text = format_digest(verdicts, rest=3)
    assert text.startswith("<b>🔥 Новые скидки: 4</b>")
    assert text.index(GROUPS["phones"]) < text.index(GROUPS["kitchen"]) < text.index("🗂 Прочее")
    assert f"<b>{GROUPS['phones']}</b> · 2" in text
    assert text.index("/product/b/") < text.index("/product/c/")  # глубже — выше
    assert "И ещё 3 находки" in text


def test_digest_escapes_html():
    item = Product(
        shop="evrika", sku="1", title="Чехол <b> & Co", price=50_000,
        url="https://evrika.com/catalog/a/p1?x=1&y=2", old_price=80_000, group="phones",
    )
    text = format_digest([Verdict(item, [SignalHit(Signal.DEAL, base=80_000)])])
    assert "&lt;b&gt; &amp; Co" in text and "x=1&amp;y=2" in text and "Эврика" in text


def test_long_digest_splits_without_breaking_markup():
    title = "Очень длинное название товара для проверки нарезки сообщения " * 2
    verdicts = [
        Verdict(Product(shop="mechta", sku=str(i), title=title, price=50_000 + i,
                        url=f"https://www.mechta.kz/product/{i}/", old_price=80_000,
                        group=list(GROUPS)[i % len(GROUPS)]),
                [SignalHit(Signal.DEAL, base=80_000)])
        for i in range(40)
    ]
    chunks = split_message(format_digest(verdicts))
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 4000
        assert chunk.count("<a ") == chunk.count("</a>")
        assert chunk.count("<b>") == chunk.count("</b>")


def test_groups_menu_shows_state_and_toggles():
    text, buttons = format_groups_menu({"tv"})
    flat = [button for row in buttons for button in row]
    assert (f"🔕 {GROUPS['tv']}", "toggle:tv") in flat
    assert (f"✅ {GROUPS['phones']}", "toggle:phones") in flat
    assert len(flat) == len(GROUPS)
    assert "Выключены: " + GROUPS["tv"] in text


def test_inline_keyboard_urls_and_callbacks():
    markup = inline_keyboard([[("Открыть", "https://x.kz/"), ("Группы", "groups")]])
    assert markup == {"inline_keyboard": [[
        {"text": "Открыть", "url": "https://x.kz/"},
        {"text": "Группы", "callback_data": "groups"},
    ]]}


def test_status_lists_crawls_queue_and_muted():
    text = format_status(
        [("mechta", datetime(2026, 9, 14, 5, 17, tzinfo=UTC), 7_636), ("evrika", None, None)],
        queued=5, muted={"tv"},
    )
    assert "Мечта: последний обход" in text and "7 636 позиций" in text
    assert "Эврика: успешных обходов ещё не было" in text
    assert "В очереди: 5" in text and GROUPS["tv"] in text


def test_format_more_plural():
    assert "ещё 1 находка" in format_more(1)
    assert "ещё 3 находки" in format_more(3)
    assert "ещё 12 находок" in format_more(12)


def test_watchdog_names_stale_shops():
    text = format_watchdog([("mechta", 13.4), ("evrika", None)], 6)
    assert "Мечта: последний успешный 13 ч назад" in text
    assert "Эврика: ни одного успешного обхода" in text
