import pandas as pd
from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.chart_pattern import ChartPattern
from app.signals.events import Event


def _df(last_close, n=40):
    closes = [100.0] * (n - 1) + [last_close]
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": c,
         "high": c + 1, "low": c - 1, "close": c, "volume": 1000}
        for i, c in enumerate(closes)])


def test_double_bottom_fires_after_neckline_break():
    df = _df(103)   # last close above the 100 neckline = confirmed break
    events = [Event("2026-02-10", "chart_pattern", "bull", magnitude=0.5,
                    payload={"pattern": "double_bottom", "neckline": 100.0})]
    m = ChartPattern().detect(events, df, build_context(df))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.confidence > 0
    assert any("doppio" in s["label"].lower() or "double" in s["label"].lower()
               or "neckline" in s["detail"].lower() for s in m.chain)


def test_silent_before_neckline_break():
    df = _df(98)    # still below the neckline -> not confirmed
    events = [Event("2026-02-10", "chart_pattern", "bull", magnitude=0.5,
                    payload={"pattern": "double_bottom", "neckline": 100.0})]
    assert ChartPattern().detect(events, df, build_context(df)) is None


def test_chart_pattern_annotations_have_neckline_and_points():
    df = _df(103)
    events = [Event("2026-02-10", "chart_pattern", "bull", magnitude=0.5,
                    payload={"pattern": "double_bottom", "neckline": 100.0,
                             "points": [{"date": "2026-01-20", "price": 90.0},
                                        {"date": "2026-01-28", "price": 100.0},
                                        {"date": "2026-02-05", "price": 90.5}]})]
    m = ChartPattern().detect(events, df, build_context(df))
    assert m is not None
    levels = m.annotations["levels"]; points = m.annotations["points"]
    assert any(l["kind"] == "neckline" for l in levels)
    assert len(points) >= 2
