import pandas as pd
from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.insider_buy import InsiderBuy
from app.signals.events import Event


def _df(last_close=96.5, n=40):
    closes = [100.0] * (n - 1) + [last_close]
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": c,
         "high": c + 1, "low": c - 1, "close": c, "volume": 1000}
        for i, c in enumerate(closes)])


def test_fires_on_cluster_with_oversold():
    events = [
        Event("2026-02-10", "insider_cluster", "bull", magnitude=0.7,
              payload={"n_buyers": 3, "total_shares": 50000}, source="insider"),
        Event("2026-02-10", "rsi_extreme", "bull", magnitude=0.6, payload={"rsi": 24.0}),
    ]
    m = InsiderBuy().detect(events, _df(), build_context(_df()))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.confidence > 0
    assert any("insider" in s["label"].lower() for s in m.chain)
    # Non-technical (first) chain step must carry source="insider".
    assert m.chain[0].get("source") == "insider"
    # Technical confirmation steps must NOT carry a source key.
    for step in m.chain[1:]:
        assert "source" not in step


def test_two_score_model_cluster_with_oversold():
    """Forza (strength) is a bounded soft-min score; confidence aliases it;
    Probabilità sits in the empirical 5..95 band."""
    events = [
        Event("2026-02-10", "insider_cluster", "bull", magnitude=0.7,
              payload={"n_buyers": 3, "total_shares": 50000}, source="insider"),
        Event("2026-02-10", "rsi_extreme", "bull", magnitude=0.6, payload={"rsi": 24.0}),
    ]
    m = InsiderBuy().detect(events, _df(), build_context(_df()))
    assert m is not None
    assert 0 < m.strength <= 93
    assert m.confidence == m.strength
    assert 5 <= m.probability <= 95


def test_silent_cluster_without_confirmation():
    events = [Event("2026-02-10", "insider_cluster", "bull", magnitude=0.7,
                    payload={"n_buyers": 3}, source="insider")]
    assert InsiderBuy().detect(events, _df(), build_context(_df())) is None


def test_fires_on_cluster_with_support():
    """Cluster + support near last_close (96.5) should fire."""
    events = [
        Event("2026-02-10", "insider_cluster", "bull", magnitude=0.6,
              payload={"n_buyers": 2, "total_shares": 20000}, source="insider"),
        # Support at 96.0 -- within 3% of last_close=96.5
        Event("2026-02-08", "sr_level", None, magnitude=None,
              payload={"kind": "support", "level": 96.0}),
    ]
    m = InsiderBuy().detect(events, _df(last_close=96.5), build_context(_df(last_close=96.5)))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.confidence > 0


def test_silent_when_no_insider_cluster():
    """Only technical events -- no insider cluster -- must return None."""
    events = [
        Event("2026-02-10", "rsi_extreme", "bull", magnitude=0.8, payload={"rsi": 22.0}),
    ]
    assert InsiderBuy().detect(events, _df(), build_context(_df())) is None


def test_bear_cluster_ignored():
    """A bear insider_cluster (hypothetical) must not trigger the bull detector."""
    events = [
        Event("2026-02-10", "insider_cluster", "bear", magnitude=0.7,
              payload={"n_buyers": 3}, source="insider"),
        Event("2026-02-10", "rsi_extreme", "bull", magnitude=0.6, payload={"rsi": 24.0}),
    ]
    assert InsiderBuy().detect(events, _df(), build_context(_df())) is None


def test_too_few_bars_returns_none():
    small_df = _df(n=10)
    events = [
        Event("2026-01-05", "insider_cluster", "bull", magnitude=0.7,
              payload={"n_buyers": 3}, source="insider"),
        Event("2026-01-05", "rsi_extreme", "bull", magnitude=0.6, payload={"rsi": 24.0}),
    ]
    assert InsiderBuy().detect(events, small_df, build_context(small_df)) is None
