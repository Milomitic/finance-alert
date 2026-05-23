import pandas as pd
from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.high52_momentum import High52Momentum
from app.signals.events import extract_events


def _near_52w_high_uptrend():
    rows = []
    price = 50.0
    for i in range(260):
        price += 0.25
        rows.append(price)
    return pd.DataFrame([
        {"date": f"{2025 + i // 360}-{1 + (i // 30) % 12:02d}-{1 + i % 28:02d}",
         "open": p, "high": p + 0.5, "low": p - 0.5, "close": p, "volume": 1000}
        for i, p in enumerate(rows)
    ])


def test_fires_near_52w_high_in_uptrend():
    df = _near_52w_high_uptrend()
    m = High52Momentum().detect(extract_events(df), df, build_context(df))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.confidence > 0
    assert any("52" in s["label"] for s in m.chain)


def test_silent_far_below_high():
    rows = []
    price = 50.0
    for i in range(220):
        price += 0.25
        rows.append(price)
    peak = price
    for i in range(40):
        price -= peak * 0.006
        rows.append(price)
    df = pd.DataFrame([
        {"date": f"{2025 + i // 360}-{1 + (i // 30) % 12:02d}-{1 + i % 28:02d}",
         "open": p, "high": p + 0.5, "low": p - 0.5, "close": p, "volume": 1000}
        for i, p in enumerate(rows)
    ])
    assert High52Momentum().detect(extract_events(df), df, build_context(df)) is None
