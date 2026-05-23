import pandas as pd
from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.squeeze_expansion import SqueezeExpansion
from app.signals.events import Event


def _events_squeeze_then_expansion():
    return [
        Event("2026-04-20", "bb_squeeze", None, magnitude=1.4, payload={"period": 20}),
        Event("2026-04-28", "bb_expansion", "bull", magnitude=0.05, payload={"period": 20}),
    ]


def test_fires_on_squeeze_then_expansion():
    rows = [{"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": 100,
             "high": 101, "low": 99, "close": 100, "volume": 1000} for i in range(40)]
    df = pd.DataFrame(rows)
    m = SqueezeExpansion().detect(_events_squeeze_then_expansion(), df, build_context(df))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.confidence > 0
    assert any("squeeze" in s["label"].lower() or "compressione" in s["label"].lower()
               for s in m.chain)


def test_silent_with_squeeze_but_no_expansion():
    rows = [{"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": 100,
             "high": 101, "low": 99, "close": 100, "volume": 1000} for i in range(40)]
    df = pd.DataFrame(rows)
    only_squeeze = [Event("2026-04-20", "bb_squeeze", None, magnitude=1.4, payload={})]
    assert SqueezeExpansion().detect(only_squeeze, df, build_context(df)) is None
