import pandas as pd
from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.adx_confirmation import AdxConfirmation
from app.signals.events import Event


def _df(n=40):
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": 100,
         "high": 101, "low": 99, "close": 100, "volume": 1000} for i in range(n)])


def test_fires_strong_trend_with_breakout():
    events = [
        Event("2026-02-10", "adx_trend", "bull", magnitude=0.6,
              payload={"adx": 35.0, "plus_di": 30.0, "minus_di": 12.0}),
        Event("2026-02-10", "breakout", "bull", magnitude=0.04, payload={"level": 105.0}),
    ]
    m = AdxConfirmation().detect(events, _df(), build_context(_df()))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.confidence > 0
    assert any("adx" in s["label"].lower() or "trend" in s["label"].lower() for s in m.chain)
    # Two-score model: Forza in range, confidence is the alias of strength,
    # Probabilità within the empirical band.
    assert 0 < m.strength <= 93
    assert m.confidence == m.strength
    assert 5 <= m.probability <= 95


def test_silent_adx_without_breakout():
    events = [Event("2026-02-10", "adx_trend", "bull", magnitude=0.6,
                    payload={"adx": 35.0, "plus_di": 30.0, "minus_di": 12.0})]
    assert AdxConfirmation().detect(events, _df(), build_context(_df())) is None
