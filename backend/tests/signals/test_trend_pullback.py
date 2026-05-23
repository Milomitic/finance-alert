import pandas as pd
from app.signals.context import build_context
from app.signals.events import extract_events
from app.signals.detectors.trend_pullback import TrendPullback


def _golden_then_pullback():
    rows = []
    price = 100.0
    for i in range(210):
        price += 0.6
        rows.append((price, 1000))
    for i in range(8):
        price -= 1.4
        rows.append((price, 1000))
    for i in range(4):
        price += 2.2
        rows.append((price, 1000))
    return pd.DataFrame([
        {"date": f"{2025 + i // 360}-{1 + (i // 30) % 12:02d}-{1 + i % 28:02d}",
         "open": p, "high": p + 1, "low": p - 1, "close": p, "volume": v}
        for i, (p, v) in enumerate(rows)
    ])


def test_fires_on_golden_cross_pullback_resume():
    df = _golden_then_pullback()
    m = TrendPullback().detect(extract_events(df), df, build_context(df))
    assert m is not None and m.tone == "bull" and m.confidence > 0
    assert any("cross" in s["label"].lower() or "incrocio" in s["label"].lower()
               for s in m.chain)


def test_silent_on_flat_series():
    rows = [{"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": 100,
             "high": 101, "low": 99, "close": 100, "volume": 1000} for i in range(210)]
    df = pd.DataFrame(rows)
    assert TrendPullback().detect(extract_events(df), df, build_context(df)) is None
