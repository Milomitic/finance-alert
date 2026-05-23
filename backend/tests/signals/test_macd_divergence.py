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
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.confidence > 0
    assert any("divergen" in s["label"].lower() for s in m.chain)


def test_silent_without_event():
    assert MacdDivergence().detect([], _df(), build_context(_df())) is None
