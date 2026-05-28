# backend/tests/signals/test_macd_divergence.py
import pandas as pd
from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.macd_divergence import MacdDivergence
from app.signals.events import Event


def _df(n=40):
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": 100,
         "high": 101, "low": 99, "close": 100, "volume": 1000} for i in range(n)])


def test_fires_from_bull_macd_divergence():
    events = [Event("2026-02-10", "macd_divergence", "bull", magnitude=0.6,
                    payload={"pivot_dates": ["2026-01-20", "2026-02-10"]})]
    m = MacdDivergence().detect(events, _df(), build_context(_df()))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.strength > 0
    assert any("divergen" in s["label"].lower() for s in m.chain)


def test_two_score_model_bull_macd_divergence():
    """Forza (strength) is a bounded soft-min score; Probabilità sits in the
    empirical 5..95 band."""
    events = [Event("2026-02-10", "macd_divergence", "bull", magnitude=0.6,
                    payload={"pivot_dates": ["2026-01-20", "2026-02-10"]})]
    m = MacdDivergence().detect(events, _df(), build_context(_df()))
    assert m is not None
    assert 0 < m.strength <= 99
    assert 5 <= m.probability <= 95


def test_silent_without_event():
    assert MacdDivergence().detect([], _df(), build_context(_df())) is None


def test_macd_divergence_annotations_points_from_pivot_dates():
    df = pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": 100,
         "high": 101, "low": 99, "close": 100 + i * 0.1, "volume": 1000}
        for i in range(40)])
    d1 = str(df["date"].iloc[5])[:10]
    d2 = str(df["date"].iloc[35])[:10]
    events = [Event("2026-02-10", "macd_divergence", "bull", magnitude=0.6,
                    payload={"pivot_dates": [d1, d2]})]
    m = MacdDivergence().detect(events, df, build_context(df))
    assert m is not None
    pts = m.annotations["points"]
    assert len(pts) == 2
    assert pts[0]["date"] == d1
    assert pts[1]["date"] == d2
    assert isinstance(pts[0]["price"], float)
    assert isinstance(pts[1]["price"], float)
