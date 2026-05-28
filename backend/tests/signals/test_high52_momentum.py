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
    records = [
        {"date": f"{2025 + i // 360}-{1 + (i // 30) % 12:02d}-{1 + i % 28:02d}",
         "open": p, "high": p + 0.5, "low": p - 0.5, "close": p,
         # last bar has a volume spike (3x avg) so extract_events yields a
         # volume_spike event, satisfying the confirmation gate
         "volume": 3000 if i == len(rows) - 1 else 1000}
        for i, p in enumerate(rows)
    ]
    return pd.DataFrame(records)


def test_fires_near_52w_high_in_uptrend():
    df = _near_52w_high_uptrend()
    m = High52Momentum().detect(extract_events(df), df, build_context(df))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.confidence > 0
    assert any("52" in s["label"] for s in m.chain)


def test_silent_near_high_without_confirmation():
    df = _near_52w_high_uptrend()   # near-high + uptrend, but pass NO events
    assert High52Momentum().detect([], df, build_context(df)) is None


def test_two_score_wiring_on_fire():
    df = _near_52w_high_uptrend()
    m = High52Momentum().detect(extract_events(df), df, build_context(df))
    assert m is not None
    assert 0 < m.strength <= 93
    assert m.confidence == m.strength
    assert 5 <= m.probability <= 95


def test_high52_momentum_annotations_has_resistance_level():
    df = _near_52w_high_uptrend()
    m = High52Momentum().detect(extract_events(df), df, build_context(df))
    assert m is not None
    levels = m.annotations["levels"]
    resistance_levels = [l for l in levels if l.get("kind") == "resistance"]
    assert len(resistance_levels) == 1
    assert resistance_levels[0]["label"] == "Max 52 settimane"
    assert isinstance(resistance_levels[0]["price"], float)


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
