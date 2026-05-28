import pandas as pd
from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.gap_and_go import GapAndGo
from app.signals.events import Event


def _df(n=30):
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": 100,
         "high": 101, "low": 99, "close": 100, "volume": 1000} for i in range(n)])


def test_fires_gap_up_with_volume():
    events = [
        Event("2026-02-10", "gap", "bull", magnitude=0.05, payload={"gap_pct": 0.05}),
        Event("2026-02-10", "volume_spike", None, magnitude=3.0, payload={}),
    ]
    m = GapAndGo().detect(events, _df(), build_context(_df()))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.strength > 0
    assert any("gap" in s["label"].lower() for s in m.chain)


def test_two_score_model_on_fire():
    events = [
        Event("2026-02-10", "gap", "bull", magnitude=0.05, payload={"gap_pct": 0.05}),
        Event("2026-02-10", "volume_spike", None, magnitude=3.0, payload={}),
    ]
    m = GapAndGo().detect(events, _df(), build_context(_df()))
    assert isinstance(m, SignalMatch)
    # Forza: bounded, never pinned at the top of the scale.
    assert 0 < m.strength <= 99
    # Probabilità: empirical hit-rate within the calibrated [floor, ceil].
    assert 5 <= m.probability <= 95


def test_silent_gap_without_volume():
    events = [Event("2026-02-10", "gap", "bull", magnitude=0.05, payload={"gap_pct": 0.05})]
    assert GapAndGo().detect(events, _df(), build_context(_df())) is None
