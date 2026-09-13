from conftest import product

from skidki.evaluate import Signal, SignalHit, Verdict
from skidki.models import Product
from skidki.report import format_finds, format_line, format_watchdog


def _drop(price: int, sku: str, base: int = 100_000) -> Verdict:
    return Verdict(product(price, sku=sku), [SignalHit(Signal.DROP, base=base, days=5)], reference=base)


def test_message_fits_ten_lines():
    verdicts = [_drop(90_000 - i * 1_000, str(i)) for i in range(20)]
    text, shown = format_finds(verdicts, limit=8)
    assert len(text.splitlines()) <= 10
    assert len(shown) == 8
    assert "ещё 12" in text
    # Самые глубокие падения — первыми.
    assert shown[0].product.price == min(v.product.price for v in verdicts)


def test_targets_go_first():
    target = Verdict(product(59_000, sku="t"), [SignalHit(Signal.TARGET, target=60_000)])
    _, shown = format_finds([_drop(50_000, "d"), target], limit=8)
    assert shown[0] is target


def test_html_is_escaped():
    item = Product(
        shop="evrika", sku="1", title="Чехол <b> & Co", price=5_000,
        url="https://evrika.com/catalog/a/p1?x=1&y=2",
    )
    line = format_line(Verdict(item, [SignalHit(Signal.DROP, base=10_000, days=4)]))
    assert "&lt;b&gt; &amp; Co" in line
    assert "x=1&amp;y=2" in line
    assert "−50%" in line and "Эврика" in line


def test_watchdog_names_stale_shops():
    text = format_watchdog([("mechta", 13.4), ("evrika", None)], 6)
    assert "Мечта: последний успешный 13 ч назад" in text
    assert "Эврика: ни одного успешного обхода" in text
