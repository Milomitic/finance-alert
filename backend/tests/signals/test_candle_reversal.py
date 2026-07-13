# backend/tests/signals/test_candle_reversal.py
import pandas as pd

from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.candle_reversal import CandleReversal
from app.signals.events import Event


def _df(last_close, n=40):
    closes = [100.0] * (n - 1) + [last_close]
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": c,
         "high": c + 1, "low": c - 1, "close": c, "volume": 1000}
        for i, c in enumerate(closes)])


def test_fires_bull_candle_at_support():
    df = _df(96.5)
    events = [
        Event("2026-02-10", "candle_reversal", "bull", magnitude=0.8,
              payload={"pattern": "hammer"}),
        Event("2026-02-05", "sr_level", None, payload={"kind": "support", "level": 96.0}),
    ]
    m = CandleReversal().detect(events, df, build_context(df))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.strength > 0
    assert any("hammer" in s["detail"].lower() or "candela" in s["label"].lower()
               for s in m.chain)


def test_silent_candle_away_from_level():
    df = _df(96.5)
    events = [Event("2026-02-10", "candle_reversal", "bull", magnitude=0.8,
                    payload={"pattern": "hammer"})]   # no S/R level near price
    assert CandleReversal().detect(events, df, build_context(df)) is None


def test_two_score_wiring_on_fire():
    df = _df(96.5)
    events = [
        Event("2026-02-10", "candle_reversal", "bull", magnitude=0.8,
              payload={"pattern": "hammer"}),
        Event("2026-02-05", "sr_level", None, payload={"kind": "support", "level": 96.0}),
    ]
    m = CandleReversal().detect(events, df, build_context(df))
    assert m is not None
    assert 0 < m.strength <= 99
    assert 5 <= m.probability <= 95


def test_candle_reversal_annotations_has_primary_level():
    df = _df(96.5)
    events = [
        Event("2026-02-10", "candle_reversal", "bull", magnitude=0.8,
              payload={"pattern": "hammer"}),
        Event("2026-02-05", "sr_level", None, payload={"kind": "support", "level": 96.0}),
    ]
    m = CandleReversal().detect(events, df, build_context(df))
    assert m is not None
    levels = m.annotations["levels"]
    assert len(levels) >= 1
    primary = levels[0]
    assert primary["kind"] in ("support", "resistance")
    assert isinstance(primary["price"], float)
