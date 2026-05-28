import pandas as pd
from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.hidden_divergence import HiddenDivergence
from app.signals.events import Event


def _uptrend_df(n=40):
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": 100 + i,
         "high": 101 + i, "low": 99 + i, "close": 100 + i, "volume": 1000} for i in range(n)])


def test_fires_bull_hidden_in_uptrend():
    df = _uptrend_df()
    events = [Event("2026-02-10", "hidden_divergence", "bull", magnitude=0.5,
                    payload={"rsi": [45.0, 38.0]})]
    m = HiddenDivergence().detect(events, df, build_context(df))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.strength > 0
    assert any("divergen" in s["label"].lower() or "continuaz" in s["label"].lower()
               for s in m.chain)


def test_two_score_model_bull_hidden():
    """Forza (strength) is a bounded soft-min score; Probabilità sits in the
    empirical 5..95 band."""
    df = _uptrend_df()
    events = [Event("2026-02-10", "hidden_divergence", "bull", magnitude=0.5,
                    payload={"rsi": [45.0, 38.0]})]
    m = HiddenDivergence().detect(events, df, build_context(df))
    assert m is not None
    assert 0 < m.strength <= 99
    assert 5 <= m.probability <= 95


def test_silent_without_event():
    df = _uptrend_df()
    assert HiddenDivergence().detect([], df, build_context(df)) is None


def test_hidden_divergence_annotations_points_from_pivot_dates():
    df = pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": 100 + i,
         "high": 101 + i, "low": 99 + i, "close": 100 + i * 0.5, "volume": 1000}
        for i in range(40)])
    d1 = str(df["date"].iloc[5])[:10]
    d2 = str(df["date"].iloc[30])[:10]
    events = [Event("2026-02-10", "hidden_divergence", "bull", magnitude=0.5,
                    payload={"rsi": [45.0, 38.0], "pivot_dates": [d1, d2]})]
    m = HiddenDivergence().detect(events, df, build_context(df))
    assert m is not None
    pts = m.annotations["points"]
    assert len(pts) == 2
    assert pts[0]["date"] == d1
    assert pts[1]["date"] == d2
    assert isinstance(pts[0]["price"], float)
    assert isinstance(pts[1]["price"], float)
