from datetime import timedelta

from conftest import T0, product, seed

from skidki import storage
from skidki.config import CategoryRule, Rules, Thresholds, WatchItem
from skidki.evaluate import Signal, evaluate, should_send, weighted_median
from skidki.storage import Span

TH = Thresholds()
NO_RULES = Rules()
AFTER_5_DAYS = T0 + timedelta(days=5, hours=2)


def test_cold_start_gives_no_signals(conn):
    assert evaluate(conn, product(50_000), NO_RULES, TH, at=T0).signals == []


def test_drop_below_median_after_history(conn):
    seed(conn, product(100_000), hours=5 * 24)
    verdict = evaluate(conn, product(90_000), NO_RULES, TH, at=AFTER_5_DAYS)
    hit = verdict.hit(Signal.DROP)
    assert hit is not None and hit.base == 100_000 and hit.days >= 5
    assert not verdict.has(Signal.LOW)  # истории меньше 7 дней


def test_drop_needs_enough_history(conn):
    seed(conn, product(100_000), hours=24)
    verdict = evaluate(conn, product(80_000), NO_RULES, TH, at=T0 + timedelta(hours=26))
    assert verdict.signals == []


def test_small_drop_is_ignored(conn):
    seed(conn, product(100_000), hours=5 * 24)
    assert evaluate(conn, product(95_000), NO_RULES, TH, at=AFTER_5_DAYS).signals == []


def test_cheap_item_needs_absolute_drop(conn):
    seed(conn, product(1_990), hours=5 * 24)
    # −50%, но всего 1 000 ₸ — не находка.
    assert evaluate(conn, product(990), NO_RULES, TH, at=AFTER_5_DAYS).signals == []


def test_category_rule_lowers_drop_threshold(conn):
    seed(conn, product(100_000), hours=5 * 24)
    rules = Rules(categories=(CategoryRule(match="часы", drop_pct=3),))
    assert evaluate(conn, product(95_000), rules, TH, at=AFTER_5_DAYS).has(Signal.DROP)


def test_thirty_day_low(conn):
    seed(conn, product(100_000), hours=8 * 24)
    verdict = evaluate(conn, product(97_000), NO_RULES, TH, at=T0 + timedelta(days=8, hours=2))
    assert verdict.has(Signal.LOW)
    assert not verdict.has(Signal.DROP)  # 3% — ниже порога «упало»


def test_target_and_restock(conn):
    rules = Rules(watch=(WatchItem(query="тест", max_price=60_000),))
    storage.save_products(conn, [product(55_000, in_stock=False)], T0)
    verdict = evaluate(conn, product(55_000), rules, TH, at=T0 + timedelta(hours=2))
    assert verdict.hit(Signal.TARGET).target == 60_000
    assert verdict.has(Signal.RESTOCK)


def test_watch_respects_shop(conn):
    rules = Rules(watch=(WatchItem(query="тест", max_price=60_000, shop="evrika"),))
    assert evaluate(conn, product(55_000), rules, TH, at=T0).signals == []


def test_out_of_stock_never_alerts(conn):
    rules = Rules(watch=(WatchItem(query="тест", max_price=60_000),))
    assert evaluate(conn, product(55_000, in_stock=False), rules, TH, at=T0).signals == []


def test_weighted_median_is_time_weighted():
    ten_days = T0 + timedelta(days=10)
    spans = [Span(T0, ten_days, 100_000, True), Span(ten_days, ten_days, 50_000, True)]
    # Двухчасовая распродажа не сдвигает медиану недели по 100 000.
    assert weighted_median(spans, T0, ten_days) == 100_000


def test_should_send_only_on_new_low(conn):
    seed(conn, product(100_000), hours=5 * 24)
    verdict = evaluate(conn, product(90_000), NO_RULES, TH, at=AFTER_5_DAYS)
    assert should_send(conn, verdict, TH, AFTER_5_DAYS)
    storage.record_alert(conn, "mechta:1", "упало", 90_000, AFTER_5_DAYS)
    storage.mark_alerts_delivered(conn, ["mechta:1"], AFTER_5_DAYS)
    assert not should_send(conn, verdict, TH, AFTER_5_DAYS)
    lower = evaluate(conn, product(85_000), NO_RULES, TH, at=AFTER_5_DAYS)
    assert should_send(conn, lower, TH, AFTER_5_DAYS)
