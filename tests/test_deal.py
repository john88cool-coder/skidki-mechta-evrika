"""Сигнал «скидка магазина»: от −20%, цена от 20 000 ₸, только новые скидки."""

from datetime import timedelta

from conftest import T0, product

from skidki import crawler, storage
from skidki.config import Rules, Thresholds
from skidki.evaluate import Signal, SignalHit, Verdict, evaluate
from skidki.report import format_line

TH = Thresholds()
NO_RULES = Rules()
LATER = T0 + timedelta(hours=2)


def deal(price: int = 75_000, old: int = 100_000, **kwargs):
    return product(price, old_price=old, **kwargs)


def _has_deal(conn, item, **kwargs) -> bool:
    return evaluate(conn, item, kwargs.pop("rules", NO_RULES), TH, **kwargs).has(Signal.DEAL)


def test_cold_start_remembers_current_deals_silently(conn):
    assert not _has_deal(conn, deal(), at=T0, cold_start=True)


def test_new_product_with_deal_after_baseline(conn):
    assert _has_deal(conn, deal(), at=T0, cold_start=False)


def test_discount_appears_on_known_product(conn):
    storage.save_products(conn, [product(100_000)], T0)
    verdict = evaluate(conn, deal(), NO_RULES, TH, at=LATER)
    assert verdict.hit(Signal.DEAL).base == 100_000


def test_same_deal_is_not_news(conn):
    storage.save_products(conn, [deal()], T0)
    assert not _has_deal(conn, deal(), at=LATER)


def test_deal_getting_deeper_is_news(conn):
    storage.save_products(conn, [deal(75_000)], T0)
    assert _has_deal(conn, deal(70_000), at=LATER)


def test_back_in_stock_with_deal_is_news(conn):
    storage.save_products(conn, [deal(in_stock=False)], T0)
    assert _has_deal(conn, deal(), at=LATER)


def test_discount_below_threshold_is_ignored(conn):
    storage.save_products(conn, [product(100_000)], T0)
    assert not _has_deal(conn, deal(85_000), at=LATER)


def test_cheap_items_are_filtered(conn):
    # Чехол за 990 «было 19 990» — −95%, но дешевле 20 000 ₸.
    assert not _has_deal(conn, deal(990, old=19_990), at=T0)
    assert not _has_deal(conn, deal(15_000, old=19_990), at=T0)


def test_absurd_discount_is_price_error(conn):
    assert not _has_deal(conn, deal(25_000, old=999_990), at=T0)


def test_rules_override_deal_threshold(conn):
    storage.save_products(conn, [product(100_000)], T0)
    assert _has_deal(conn, deal(85_000), at=LATER, rules=Rules(deal_pct=10))


def test_deal_line_shows_shop_discount():
    line = format_line(Verdict(deal(), [SignalHit(Signal.DEAL, base=100_000)]))
    assert "скидка −25%, было 100 000 ₸" in line


def test_first_crawl_is_silent_then_only_new_deals(conn):
    first, _ = crawler.process(
        conn, [("mechta", [deal(sku="a"), product(100_000, sku="b")], None)], NO_RULES, TH, T0
    )
    assert first == []
    second, _ = crawler.process(
        conn, [("mechta", [deal(sku="a"), deal(sku="b"), deal(sku="c")], None)], NO_RULES, TH, LATER
    )
    # a — висела с прошлого обхода; b — скидка появилась; c — новый товар со скидкой.
    assert sorted(v.product.sku for v in second) == ["b", "c"]
