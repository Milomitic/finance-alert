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
    # Both are the 'trend' family → DE-CORRELATED to n_eff = 1 + 0.15 = 1.15,
    # so the bonus is small: base 80 + (98-80)*(1-0.5^0.15) ≈ 81.8 (a raw
    # count of 2 would have given 89.0).
    assert c.effective_n == 1.15
    assert round(c.strength, 1) == 81.8
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


def test_legacy_confidence_100_is_capped_at_ceiling(db):
    """A legacy snapshot storing confidence=100 (predating the score() reshape)
    must NOT leak a strength above the confluence ceiling. Before the cap, base
    = max(100) and the bonus term could push strength to 99 (n=2) or leave it at
    100 (n=1 prevailing); now base is clamped to CEIL first."""
    s = _stock(db, "EE3")
    _add(db, s.id, "trend_pullback", 100, "bull")   # legacy perfect score
    _add(db, s.id, "squeeze_expansion", 95, "bull")
    db.commit()
    c = compute_confluence(db, days=30)[0]
    # base = min(100, 98) = 98; n=2 → 98 + (98-98)*... = 98 (pinned at ceiling)
    assert c.strength == 98.0
    assert c.strength < 100.0


def test_strength_grows_with_confluence_below_ceiling(db):
    """More concurring signals push strength UP toward (never past) the ceiling
    — but DE-CORRELATED: these four are all the 'trend' family, so they count
    ~1.45 effective, not 4. base 70; n_eff = 1 + 0.15*3 = 1.45 →
    70 + (98-70)*(1-0.5^0.45) ≈ 77.5 (NOT the 94.5 a raw count would give)."""
    s2 = _stock(db, "EE2")
    for nm in ["trend_pullback", "squeeze_expansion", "high52_momentum", "sr_flip"]:
        _add(db, s2.id, nm, 70, "bull")
    db.commit()
    c = compute_confluence(db, days=30)[0]
    assert c.n_signals == 4
    assert c.effective_n == 1.45
    assert round(c.strength, 1) == 77.5
    assert c.strength < 98.0


def test_decorrelation_distinct_families_beat_same_family(db):
    """Same confidences: 3 DISTINCT-family signals must yield a HIGHER
    confluence strength than 3 SAME-family ones (independent evidence > one
    piece counted thrice)."""
    same = _stock(db, "SAME")
    for nm in ["trend_pullback", "volume_breakout", "adx_confirmation"]:  # all 'trend'
        _add(db, same.id, nm, 70, "bull")
    diff = _stock(db, "DIFF")
    for nm in ["trend_pullback", "rsi_divergence", "candle_reversal"]:  # 3 families
        _add(db, diff.id, nm, 70, "bull")
    db.commit()
    by_ticker = {c.ticker: c for c in compute_confluence(db, days=30)}
    assert by_ticker["SAME"].effective_n == 1.30   # 1 + 0.15*2
    assert by_ticker["DIFF"].effective_n == 3.0
    assert by_ticker["DIFF"].strength > by_ticker["SAME"].strength


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
