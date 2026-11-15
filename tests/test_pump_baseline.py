"""Накрутка перед скидкой: база сравнения — прежний уровень цены."""

from datetime import UTC, datetime, timedelta

from conftest import T0, product, seed

from skidki import export, storage
from skidki.config import Rules, Thresholds
from skidki.evaluate import Baseline, Signal, evaluate, honest_baseline
from skidki.storage import Span

RULES = Rules()
TH = Thresholds()


def _span(price: int, start_day: float, end_day: float, at: datetime) -> Span:
    """Отрезок «цена держалась с start_day по end_day дней назад»."""
    return Span(
        first_seen=at - timedelta(days=start_day),
        last_seen=at - timedelta(days=end_day),
        price=price,
        in_stock=True,
    )


def test_pump_before_discount_uses_earlier_level():
    at = T0
    spans = [
        _span(299_970, 28, 12, at),  # прежняя цена: 16 дней
        _span(524_990, 12, 3, at),  # подняли на 9 дней
        _span(199_970, 3, 0, at),  # «скидка»
    ]
    assert honest_baseline(spans, at, TH) == Baseline(299_970, pump_price=524_990)


def test_long_stable_price_is_not_a_pump():
    at = T0
    spans = [_span(524_990, 28, 3, at), _span(199_970, 3, 0, at)]
    assert honest_baseline(spans, at, TH) == Baseline(524_990)


def test_small_gap_keeps_trend_median():
    at = T0
    # Прежняя цена ниже всего на 5% — это не накрутка, база прежняя.
    spans = [_span(95_000, 28, 12, at), _span(100_000, 12, 0, at)]
    assert honest_baseline(spans, at, TH) == Baseline(100_000)


def test_no_history_gives_empty_baseline():
    assert honest_baseline([], T0, TH) == Baseline(None)


def test_evaluate_drop_is_measured_from_earlier_level(conn):
    seed(conn, product(299_970), hours=16 * 24)  # дни 0–16
    seed(conn, product(524_990), hours=9 * 24, start=T0 + timedelta(days=16))  # дни 16–25
    at = T0 + timedelta(days=25, hours=2)
    verdict = evaluate(conn, product(199_970), RULES, TH, at)
    hit = verdict.hit(Signal.DROP)
    assert hit is not None
    assert hit.base == 299_970
    assert round(verdict.drop_pct) == 33


def test_export_reports_honest_discount_and_pump_price(tmp_path):
    db = tmp_path / "pump.sqlite3"
    now = datetime.now(UTC)
    start = now - timedelta(days=28)
    with storage.connect(db) as conn:
        seed(conn, product(299_970, sku="pump", old_price=599_990), hours=16 * 24, start=start, step=12)
        seed(
            conn,
            product(524_990, sku="pump", old_price=599_990),
            hours=9 * 24 - 12,
            start=start + timedelta(days=16),
            step=12,
        )
        sale = product(199_970, sku="pump", old_price=599_990)
        seed(conn, sale, hours=3 * 24 - 12, start=start + timedelta(days=25), step=12)
        fair, ref, _age, pump = export._fair_reference_and_age(conn, sale, now)
        deal = export._deal_dict(conn, sale, now, "deal")
    assert ref == 299_970
    assert pump == 524_990
    assert fair == 33.3
    assert deal["base_price"] == 299_970
    assert deal["pump_price"] == 524_990


def test_export_without_pump_has_no_pump_price(tmp_path):
    db = tmp_path / "plain.sqlite3"
    now = datetime.now(UTC)
    start = now - timedelta(days=20)
    with storage.connect(db) as conn:
        seed(conn, product(100_000, sku="plain"), hours=17 * 24, start=start, step=12)
        sale = product(70_000, sku="plain")
        seed(conn, sale, hours=3 * 24 - 12, start=start + timedelta(days=17, hours=12), step=12)
        deal = export._deal_dict(conn, sale, now, "drop")
    assert deal["base_price"] == 100_000
    assert deal["fair_discount"] == 30.0
    assert deal["pump_price"] is None
