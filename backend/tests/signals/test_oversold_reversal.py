import pandas as pd

from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.oversold_reversal import OversoldReversal
from app.signals.events import Event


def _df(last_close, n=40):
    closes = [100.0] * (n - 1) + [last_close]
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": c,
         "high": c + 1, "low": c - 1, "close": c, "volume": 1000}
        for i, c in enumerate(closes)
    ])


def test_fires_oversold_at_support_with_turn_up():
    df = _df(96.5)
    events = [
        Event("2026-02-10", "rsi_extreme", "bull", magnitude=0.5,
              payload={"rsi": 22.0, "period": 14}),
        Event("2026-02-05", "sr_level", None, payload={"kind": "support", "level": 96.0}),
    ]
    m = OversoldReversal().detect(events, df, build_context(df))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.strength > 0
    assert any("ipervendut" in s["label"].lower() or "supporto" in s["label"].lower()
               for s in m.chain)


def test_silent_without_rsi_extreme():
    df = _df(96.5)
    only_sr = [Event("2026-02-05", "sr_level", None, payload={"kind": "support", "level": 96.0})]
    assert OversoldReversal().detect(only_sr, df, build_context(df)) is None


def test_two_score_wiring_on_fire():
    df = _df(96.5)
    events = [
        Event("2026-02-10", "rsi_extreme", "bull", magnitude=0.5,
              payload={"rsi": 22.0, "period": 14}),
        Event("2026-02-05", "sr_level", None, payload={"kind": "support", "level": 96.0}),
    ]
    m = OversoldReversal().detect(events, df, build_context(df))
    assert m is not None
    assert 0 < m.strength <= 99
    assert 5 <= m.probability <= 95


def test_oversold_reversal_annotations_has_primary_level():
    df = _df(96.5)
    events = [
        Event("2026-02-10", "rsi_extreme", "bull", magnitude=0.5,
              payload={"rsi": 22.0, "period": 14}),
        Event("2026-02-05", "sr_level", None, payload={"kind": "support", "level": 96.0}),
    ]
    m = OversoldReversal().detect(events, df, build_context(df))
    assert m is not None
    levels = m.annotations["levels"]
    assert len(levels) >= 1
    primary = levels[0]
    assert primary["kind"] in ("support", "resistance")
    assert isinstance(primary["price"], float)
