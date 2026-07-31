"""Technical score: dimension monotonicity, relative-strength ranking, upsert."""
import pandas as pd

from app.models import Stock, TechnicalScore
from app.services import technical_score_service as svc


def _df(prices):
    n = len(prices)
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "open": [float(p) for p in prices],
        "high": [float(p) + 1 for p in prices],
        "low": [float(p) - 1 for p in prices],
        "close": [float(p) for p in prices],
        "volume": [1000.0] * n,
    })


def test_uptrend_scores_higher_than_downtrend():
    up = svc.partial_for(_df([100 + i for i in range(120)]))
    down = svc.partial_for(_df([300 - i for i in range(120)]))
    assert up is not None and down is not None
    assert up["trend"] > down["trend"]
    assert up["momentum"] > down["momentum"]
    assert up["structure"] > down["structure"]


def test_short_history_returns_none():
    assert svc.partial_for(_df([100, 101, 102])) is None


def test_finalize_ranks_rel_strength_and_upserts(db):
    s1 = Stock(ticker="TUP", exchange="NASDAQ", name="Up", country="US")
    s2 = Stock(ticker="TDN", exchange="NASDAQ", name="Dn", country="US")
    db.add_all([s1, s2])
    db.flush()
    p_up = svc.partial_for(_df([100 + i for i in range(120)]))
    p_dn = svc.partial_for(_df([300 - i for i in range(120)]))
    n = svc.finalize(db, {s1.id: p_up, s2.id: p_dn})
    db.commit()
    assert n == 2
    ts_up = db.get(TechnicalScore, s1.id)
    ts_dn = db.get(TechnicalScore, s2.id)
    assert ts_up is not None and ts_dn is not None
    # The uptrend stock has the stronger blended return, so higher rel strength.
    assert ts_up.rel_strength > ts_dn.rel_strength
    assert ts_up.composite > ts_dn.composite
    assert ts_up.posture in ("Forte", "Neutro", "Debole")


def test_finalize_empty_is_noop(db):
    assert svc.finalize(db, {}) == 0


def test_composite_not_nudged_by_recent_signal(db):
    """Lens decoupling: the TechnicalScore composite is PURE price-action — the
    5-dim weighted average — and must NOT be bumped by a recent signal's
    confidence. (Signals are their own lens; the `signals` field stays as an
    informational reference only.) Regression: it used to add ±5pp."""
    import datetime
    import json

    from app.models import Alert

    s = Stock(ticker="TNUDGE", exchange="NASDAQ", name="N", country="US")
    db.add(s)
    db.flush()
    p = svc.partial_for(_df([100 + i for i in range(120)]))
    assert p is not None
    # Pure composite: single stock → rel_strength 50, weighted avg of dims.
    dims = {"trend": p["trend"], "momentum": p["momentum"],
            "structure": p["structure"], "volume": p["volume"], "rel_strength": 50.0}
    expected = round(sum(svc._WEIGHTS[k] * dims[k] for k in svc._WEIGHTS), 1)
    # A strong recent BULL signal that previously would have nudged +~4.4pp.
    db.add(Alert(
        stock_id=s.id, signal_name="volume_breakout", trigger_price=100.0,
        triggered_at=datetime.datetime.now(datetime.UTC),
        signal_date=datetime.date.today(),
        snapshot=json.dumps({"tone": "bull", "confidence": 95}),
    ))
    db.flush()
    svc.finalize(db, {s.id: p})
    db.commit()
    ts = db.get(TechnicalScore, s.id)
    assert ts is not None
    assert ts.composite == expected          # pure — NOT expected + nudge
    assert ts.signals == 95.0                # still surfaced as a reference


def _alert(db, stock_id: int, snapshot: dict):
    import datetime
    import json

    from app.models import Alert

    db.add(Alert(
        stock_id=stock_id, signal_name="volume_breakout", trigger_price=100.0,
        triggered_at=datetime.datetime.now(datetime.UTC),
        signal_date=datetime.date.today(),
        snapshot=json.dumps(snapshot),
    ))
    db.flush()


def test_signals_facet_reads_strength_snapshot(db):
    """Post Forza/Probabilità split, snapshots carry "strength" (not
    "confidence"). Regression: the facet read only "confidence" → 0/938
    technical_scores rows had a `signals` value despite 1457 recent alerts."""
    s = Stock(ticker="TSTR", exchange="NASDAQ", name="S", country="US")
    db.add(s)
    db.flush()
    _alert(db, s.id, {"tone": "bull", "strength": 88, "probability": 52})
    p = svc.partial_for(_df([100 + i for i in range(120)]))
    svc.finalize(db, {s.id: p})
    db.commit()
    ts = db.get(TechnicalScore, s.id)
    assert ts is not None and ts.signals == 88.0


def test_signals_facet_picks_best_across_both_snapshot_shapes(db):
    """Mixed history: a legacy confidence-only alert and a post-split
    strength alert on the same stock — the facet coalesces per-row and keeps
    the max, so neither shape is invisible."""
    s = Stock(ticker="TMIX", exchange="NASDAQ", name="M", country="US")
    db.add(s)
    db.flush()
    _alert(db, s.id, {"tone": "bull", "confidence": 70})            # legacy
    _alert(db, s.id, {"tone": "bull", "strength": 91})              # post-split
    p = svc.partial_for(_df([100 + i for i in range(120)]))
    svc.finalize(db, {s.id: p})
    db.commit()
    ts = db.get(TechnicalScore, s.id)
    assert ts is not None and ts.signals == 91.0


def test_trend_refuses_to_score_a_malformed_frame():
    """Targets `_trend` directly, and deliberately so.

    The ADX fallback used to sit behind a bare `except Exception: pass`, so a
    frame missing high/low silently rewrote the trend score to the neutral
    ADX weight — a wrong number indistinguishable from a right one. The catch
    is now narrowed to the genuine shortage errors (all-NaN series, non-finite
    values) so a defect escapes instead.

    Asserting this through `partial_for` would be VACUOUS: its outer boundary
    collapses every failure to None, and _structure/_volume touch the same
    missing column, so that assertion passes with or without the narrowing.
    Checked in both directions before writing it this way."""
    import pytest

    df = _df([100 + i for i in range(120)]).drop(columns=["high"])
    close = df["close"].astype(float).reset_index(drop=True)
    with pytest.raises(KeyError):
        svc._trend(close, df)


def test_partial_for_isolates_one_bad_stock_instead_of_failing_the_run():
    """The other half: that escaping error must NOT reach the caller. The
    broad catch in partial_for stays broad on purpose — one malformed stock
    cannot be allowed to kill a ~1000-name recompute. An absent score is
    honest; a plausible wrong one is not."""
    df = _df([100 + i for i in range(120)]).drop(columns=["high"])
    assert svc.partial_for(df) is None


def test_too_few_bars_for_adx_still_degrades_gracefully():
    """The other half of the narrowing: a short-but-well-formed history is a
    legitimate shortage, not a defect, and must still score."""
    out = svc.partial_for(_df([100 + i for i in range(60)]))
    assert out is not None
    assert 0.0 <= out["trend"] <= 100.0
