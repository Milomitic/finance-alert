"""Tests for confluence_service: grouping, scoring, contested detection."""
import json
from datetime import date

from app.models import Alert, Stock
from app.services.confluence_service import compute_confluence


def _stock(db, ticker):
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US")
    db.add(s)
    db.flush()
    return s


def _add(db, stock_id, name, conf, tone, horizon="medium"):
    db.add(Alert(
        stock_id=stock_id, trigger_price=10, signal_date=date.today(),
        signal_name=name,
        snapshot=json.dumps({"tone": tone, "confidence": conf, "chain": [], "horizon": horizon}),
    ))


def test_groups_same_direction_and_scores(db):
    s = _stock(db, "AAA")
    _add(db, s.id, "trend_pullback", 80, "bear")
    _add(db, s.id, "volume_breakout", 70, "bear")
    db.commit()
    clusters = compute_confluence(db, days=30)
    assert len(clusters) == 1
    c = clusters[0]
    assert c.ticker == "AAA"
    assert c.direction == "bear"
    assert c.n_signals == 2
    # Diminishing-returns bonus toward CEIL=98: base 80 + (98-80)*(1-0.5^1) = 89
    assert c.strength == 89.0
    assert c.contested is False


def test_requires_at_least_two_signals(db):
    s = _stock(db, "BBB")
    _add(db, s.id, "trend_pullback", 90, "bull")
    db.commit()
    assert compute_confluence(db, days=30) == []


def test_contested_when_both_sides_close(db):
    s = _stock(db, "CCC")
    _add(db, s.id, "macd_divergence", 96, "bear")
    _add(db, s.id, "candle_reversal", 90, "bull")
    db.commit()
    c = compute_confluence(db, days=30)[0]
    # bull=90, bear=96, gap=6 < 25 -> contested; prevailing = bear (stronger)
    assert c.direction == "bear"
    assert c.contested is True


def test_not_contested_when_one_side_dominates(db):
    s = _stock(db, "DDD")
    _add(db, s.id, "trend_pullback", 95, "bull")
    _add(db, s.id, "candle_reversal", 60, "bear")
    db.commit()
    c = compute_confluence(db, days=30)[0]
    # bull=95, bear=60, gap=35 >= 25 -> not contested
    assert c.direction == "bull"
    assert c.contested is False


def test_strength_never_reaches_100(db):
    s = _stock(db, "EEE")
    for nm, cf in [("trend_pullback", 98), ("squeeze_expansion", 90), ("high52_momentum", 85)]:
        _add(db, s.id, nm, cf, "bull")
    db.commit()
    c = compute_confluence(db, days=30)[0]
    # base=max(98)=CEIL → gap to ceiling is 0, so strength stays 98 (the
    # asymptotic ceiling); confluence strength is bounded below 100 by design.
    assert c.strength == 98.0
    assert c.strength < 100.0
    assert c.n_signals == 3


def test_strength_grows_with_confluence_below_ceiling(db):
    """More concurring signals push strength UP toward (never past) the ceiling."""
    s2 = _stock(db, "EE2")
    for nm in ["trend_pullback", "squeeze_expansion", "high52_momentum", "sr_flip"]:
        _add(db, s2.id, nm, 70, "bull")
    db.commit()
    c = compute_confluence(db, days=30)[0]
    # base 70; n=4 → 70 + (98-70)*(1-0.5^3) = 70 + 28*0.875 = 94.5
    assert c.strength == 94.5
    assert c.strength < 98.0


def test_stale_signals_excluded_by_window(db):
    s = _stock(db, "FFF")
    # both within the table but signal_date far in the past
    from datetime import timedelta
    old = date.today() - timedelta(days=60)
    db.add(Alert(stock_id=s.id, trigger_price=10, signal_date=old, signal_name="trend_pullback",
                 snapshot=json.dumps({"tone": "bull", "confidence": 90, "chain": []})))
    db.add(Alert(stock_id=s.id, trigger_price=10, signal_date=old, signal_name="volume_breakout",
                 snapshot=json.dumps({"tone": "bull", "confidence": 80, "chain": []})))
    db.commit()
    assert compute_confluence(db, days=7) == []


def test_multi_horizon_flag_set_when_prevailing_spans_two_horizons(db):
    s = _stock(db, "MHX")
    _add(db, s.id, "trend_pullback", 90, "bull", horizon="long")
    _add(db, s.id, "candle_reversal", 70, "bull", horizon="short")
    db.commit()
    c = compute_confluence(db, days=30)[0]
    assert c.multi_horizon is True
    assert c.horizons == ["short", "long"]


def test_multi_horizon_false_when_single_horizon(db):
    s = _stock(db, "MHY")
    _add(db, s.id, "trend_pullback", 90, "bull", horizon="long")
    _add(db, s.id, "high52_momentum", 70, "bull", horizon="long")
    db.commit()
    c = compute_confluence(db, days=30)[0]
    assert c.multi_horizon is False
    assert c.horizons == ["long"]


def test_multi_horizon_only_counts_prevailing_direction(db):
    # bull is prevailing (stronger); a lone bear of a different horizon must
    # NOT make it multi-horizon.
    s = _stock(db, "MHZ")
    _add(db, s.id, "trend_pullback", 95, "bull", horizon="long")
    _add(db, s.id, "high52_momentum", 90, "bull", horizon="long")
    _add(db, s.id, "candle_reversal", 60, "bear", horizon="short")
    db.commit()
    c = compute_confluence(db, days=30)[0]
    assert c.direction == "bull"
    assert c.multi_horizon is False  # both bull components are "long"
