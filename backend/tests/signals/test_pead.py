import pandas as pd

from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.pead import Pead
from app.signals.events import Event


def _df(n=40):
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": 100,
         "high": 101, "low": 99, "close": 100, "volume": 1000} for i in range(n)])


def test_fires_on_beat_gap_volume():
    events = [
        Event("2026-02-10", "earnings_surprise", "bull", magnitude=0.6,
              payload={"surprise_pct": 0.15}, source="earnings"),
        Event("2026-02-10", "gap", "bull", magnitude=0.04, payload={"gap_pct": 0.04}),
        Event("2026-02-10", "volume_spike", None, magnitude=3.0, payload={}),
    ]
    m = Pead().detect(events, _df(), build_context(_df()))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.strength > 0
    assert any("earning" in s["label"].lower() or "sorpresa" in s["label"].lower()
               or "drift" in s["label"].lower() for s in m.chain)
    # Non-technical (first) chain step must carry source="earnings".
    assert m.chain[0].get("source") == "earnings"
    # Technical confirmation steps must NOT carry a source key.
    for step in m.chain[1:]:
        assert "source" not in step


def test_two_score_model_on_fire():
    events = [
        Event("2026-02-10", "earnings_surprise", "bull", magnitude=0.6,
              payload={"surprise_pct": 0.15}, source="earnings"),
        Event("2026-02-10", "gap", "bull", magnitude=0.04, payload={"gap_pct": 0.04}),
        Event("2026-02-10", "volume_spike", None, magnitude=3.0, payload={}),
    ]
    m = Pead().detect(events, _df(), build_context(_df()))
    assert isinstance(m, SignalMatch)
    # Forza: bounded, never pinned at the top of the scale.
    assert 0 < m.strength <= 99
    # Probabilità: empirical hit-rate within the calibrated [floor, ceil].
    assert 5 <= m.probability <= 95


def test_silent_earnings_without_confirmation():
    events = [Event("2026-02-10", "earnings_surprise", "bull", magnitude=0.6,
                    payload={"surprise_pct": 0.15}, source="earnings")]
    assert Pead().detect(events, _df(), build_context(_df())) is None
