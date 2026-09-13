from conftest import product

from skidki.evaluate import Signal, SignalHit, Verdict
from skidki.models import Product
from skidki.report import format_card, format_more, format_watchdog, rank


def _drop(price: int, sku: str, base: int = 100_000) -> Verdict:
    return Verdict(product(price, sku=sku), [SignalHit(Signal.DROP, base=base, days=5)], reference=base)


def test_rank_limits_and_counts_rest():
    verdicts = [_drop(90_000 - i * 1_000, str(i)) for i in range(20)]
    shown, rest = rank(verdicts, limit=8)
    assert len(shown) == 8 and rest == 12
    # Самые глубокие падения — первыми.
    assert shown[0].product.price == min(v.product.price for v in verdicts)


def test_targets_go_first():
    target = Verdict(product(59_000, sku="t"), [SignalHit(Signal.TARGET, target=60_000)])
    shown, _ = rank([_drop(50_000, "d"), target], limit=8)
    assert shown[0] is target


def test_deal_card_shows_percent_old_price_and_button():
    item = Product(
        shop="mechta", sku="1", title="Робот-пылесос Tefal RG8577WH", price=69_990,
        url="https://www.mechta.kz/product/tefal-rg8577wh/", brand="Tefal",
        category="Роботы-пылесосы", old_price=99_990, stock_note="осталось мало",
    )
    text, buttons = format_card(Verdict(item, [SignalHit(Signal.DEAL, base=99_990)]))
    lines = text.splitlines()
    assert lines[0] == "🏷 <b>Скидка −30%</b> · Мечта"
    assert "<b>Робот-пылесос Tefal RG8577WH</b>" in text
    assert "💰 <b>69 990 ₸</b>  <s>99 990 ₸</s>  −30 000 ₸" in text
    assert "📂 Роботы-пылесосы · Tefal" in text
    assert "⚠️ Осталось мало" in text
    assert buttons == [[("🛒 Открыть в Мечте", "https://www.mechta.kz/product/tefal-rg8577wh/")]]
    assert len(lines) <= 10


def test_drop_card_explains_median():
    text, buttons = format_card(_drop(90_000, "1"))
    assert text.startswith("📉 <b>Цена упала на 10%</b> · Мечта")
    assert "📊 Обычно 100 000 ₸ (медиана за 5 дн) → −10%" in text
    assert buttons[0][0][0] == "🛒 Открыть в Мечте"


def test_target_card_headline():
    verdict = Verdict(product(59_000), [SignalHit(Signal.TARGET, target=60_000),
                                        SignalHit(Signal.RESTOCK, target=60_000)])
    text, _ = format_card(verdict)
    assert text.startswith("🎯 <b>Цель достигнута: ≤ 60 000 ₸</b>")
    assert "✅ Снова в наличии" in text


def test_evrika_button_and_html_escape():
    item = Product(
        shop="evrika", sku="1", title="Чехол <b> & Co", price=50_000,
        url="https://evrika.com/catalog/a/p1", old_price=80_000,
    )
    text, buttons = format_card(Verdict(item, [SignalHit(Signal.DEAL, base=80_000)]))
    assert "&lt;b&gt; &amp; Co" in text
    assert buttons == [[("🛒 Открыть в Эврике", "https://evrika.com/catalog/a/p1")]]


def test_format_more_plural():
    assert "ещё 1 находка" in format_more(1)
    assert "ещё 3 находки" in format_more(3)
    assert "ещё 12 находок" in format_more(12)


def test_watchdog_names_stale_shops():
    text = format_watchdog([("mechta", 13.4), ("evrika", None)], 6)
    assert "Мечта: последний успешный 13 ч назад" in text
    assert "Эврика: ни одного успешного обхода" in text
