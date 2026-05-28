import pandas as pd
from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.analyst_momentum import AnalystMomentum
from app.signals.events import Event


def _df(n=40):
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": 100,
         "high": 101, "low": 99, "close": 100, "volume": 1000} for i in range(n)])


def test_fires_on_upgrade_with_breakout():
    events = [
        Event("2026-02-10", "analyst_change", "bull", magnitude=0.6,
              payload={"firm": "X", "to_grade": "Buy"}, source="analyst"),
        Event("2026-02-11", "breakout", "bull", magnitude=0.04, payload={"level": 105.0}),
    ]
    m = AnalystMomentum().detect(events, _df(), build_context(_df()))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.confidence > 0
    assert any("analist" in s["label"].lower() or "upgrade" in s["label"].lower()
               or "rating" in s["label"].lower() for s in m.chain)
    # Non-technical (first) chain step must carry source="analyst".
    assert m.chain[0].get("source") == "analyst"
    # Technical confirmation steps must NOT carry a source key.
    for step in m.chain[1:]:
        assert "source" not in step


def test_two_score_model_upgrade_with_breakout():
    """Forza (strength) is a bounded soft-min score; confidence aliases it;
    Probabilità sits in the empirical 5..95 band."""
    events = [
        Event("2026-02-10", "analyst_change", "bull", magnitude=0.6,
              payload={"firm": "X", "to_grade": "Buy"}, source="analyst"),
        Event("2026-02-11", "breakout", "bull", magnitude=0.04, payload={"level": 105.0}),
    ]
    m = AnalystMomentum().detect(events, _df(), build_context(_df()))
    assert m is not None
    assert 0 < m.strength <= 93
    assert m.confidence == m.strength
    assert 5 <= m.probability <= 95


def test_silent_upgrade_without_confirmation():
    events = [Event("2026-02-10", "analyst_change", "bull", magnitude=0.6,
                    payload={"firm": "X"}, source="analyst")]
    assert AnalystMomentum().detect(events, _df(), build_context(_df())) is None


def test_fires_on_downgrade_with_bearish_breakout():
    events = [
        Event("2026-02-10", "analyst_change", "bear", magnitude=0.5,
              payload={"firm": "Y", "from_grade": "Buy", "to_grade": "Hold"}, source="analyst"),
        Event("2026-02-12", "breakout", "bear", magnitude=0.05, payload={"level": 95.0}),
    ]
    m = AnalystMomentum().detect(events, _df(), build_context(_df()))
    assert isinstance(m, SignalMatch) and m.tone == "bear" and m.confidence > 0


def test_fires_on_upgrade_with_ema_cross():
    events = [
        Event("2026-02-10", "analyst_change", "bull", magnitude=0.5,
              payload={"firm": "Z"}, source="analyst"),
        Event("2026-02-13", "ema_cross", "bull", magnitude=0.02,
              payload={"fast": 50, "slow": 200}),
    ]
    m = AnalystMomentum().detect(events, _df(), build_context(_df()))
    assert isinstance(m, SignalMatch) and m.tone == "bull"


def test_no_fire_when_technical_confirmation_too_late():
    """Technical confirmation outside the 5-day window => no signal."""
    events = [
        Event("2026-02-10", "analyst_change", "bull", magnitude=0.5,
              payload={"firm": "A"}, source="analyst"),
        Event("2026-02-17", "breakout", "bull", magnitude=0.04, payload={"level": 105.0}),
    ]
    assert AnalystMomentum().detect(events, _df(), build_context(_df())) is None


def test_no_fire_wrong_direction_technical():
    """Upgrade + bearish breakout (wrong direction) => no signal."""
    events = [
        Event("2026-02-10", "analyst_change", "bull", magnitude=0.5,
              payload={"firm": "A"}, source="analyst"),
        Event("2026-02-11", "breakout", "bear", magnitude=0.04, payload={"level": 95.0}),
    ]
    assert AnalystMomentum().detect(events, _df(), build_context(_df())) is None


def test_insufficient_bars():
    df_short = _df(n=20)
    events = [
        Event("2026-01-10", "analyst_change", "bull", magnitude=0.5,
              payload={"firm": "A"}, source="analyst"),
        Event("2026-01-11", "breakout", "bull", magnitude=0.04, payload={"level": 105.0}),
    ]
    assert AnalystMomentum().detect(events, df_short, build_context(df_short)) is None


def test_factors_and_chain_structure():
    events = [
        Event("2026-02-10", "analyst_change", "bull", magnitude=0.6,
              payload={"firm": "GS", "from_grade": "Hold", "to_grade": "Buy"}, source="analyst"),
        Event("2026-02-11", "breakout", "bull", magnitude=0.04, payload={"level": 105.0}),
    ]
    m = AnalystMomentum().detect(events, _df(), build_context(_df()))
    assert m is not None
    assert "upgrade_present" in m.factors
    assert "technical_strength" in m.factors
    assert m.factors["upgrade_present"] == 1.0
    assert len(m.chain) == 2
    assert m.invalidation is not None
