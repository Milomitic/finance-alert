import pandas as pd
from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.sr_flip import SRFlip
from app.signals.events import Event


def _df(closes):
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": c,
         "high": c + 1, "low": c - 1, "close": c, "volume": 1000}
        for i, c in enumerate(closes)
    ])


def test_bull_flip_break_then_hold_above_old_resistance():
    closes = [98, 99, 100, 99, 100, 106, 104, 102, 101]
    df = _df([100.0] * 25 + closes)
    events = [Event("2026-02-05", "sr_level", None,
                    payload={"kind": "resistance", "level": 100.0})]
    m = SRFlip().detect(events, df, build_context(df))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.confidence > 0
    assert any("flip" in s["label"].lower() or "polarit" in s["label"].lower()
               or "supporto" in s["label"].lower() for s in m.chain)


def test_silent_when_price_back_below_level():
    closes = [98, 99, 100, 106, 104, 99]
    df = _df([100.0] * 25 + closes)
    events = [Event("2026-02-05", "sr_level", None,
                    payload={"kind": "resistance", "level": 100.0})]
    assert SRFlip().detect(events, df, build_context(df)) is None


def test_silent_without_sr_level():
    df = _df([100.0] * 30)
    assert SRFlip().detect([], df, build_context(df)) is None
