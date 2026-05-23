import pandas as pd
from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.rsi_divergence import RsiDivergence
from app.signals.events import Event


def test_fires_from_bull_divergence_event():
    events = [Event("2026-05-01", "rsi_divergence", "bull", magnitude=0.4,
                    payload={"period": 14, "rsi": [22.0, 42.0],
                             "pivot_dates": ["2026-04-10", "2026-05-01"]})]
    rows = [{"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": 100,
             "high": 101, "low": 99, "close": 100, "volume": 1000} for i in range(30)]
    df = pd.DataFrame(rows)
    m = RsiDivergence().detect(events, df, build_context(df))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.confidence > 0
    assert any("divergen" in s["label"].lower() for s in m.chain)


def test_silent_without_divergence_event():
    rows = [{"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": 100,
             "high": 101, "low": 99, "close": 100, "volume": 1000} for i in range(30)]
    df = pd.DataFrame(rows)
    assert RsiDivergence().detect([], df, build_context(df)) is None
