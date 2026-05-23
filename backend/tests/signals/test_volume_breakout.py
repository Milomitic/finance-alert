import pandas as pd
from app.signals.context import build_context
from app.signals.events import extract_events
from app.signals.detectors.volume_breakout import VolumeBreakout


def _series(breakout=True, with_volume=True):
    rows = [{"date": f"2026-04-{i:02d}", "open": 100, "high": 101, "low": 99,
             "close": 100, "volume": 1000} for i in range(1, 21)]
    if breakout:
        rows.append({"date": "2026-05-01", "open": 100, "high": 112, "low": 100,
                     "close": 110, "volume": 4000 if with_volume else 1000})
    return pd.DataFrame(rows)


def test_fires_when_breakout_confirmed_by_volume():
    df = _series(breakout=True, with_volume=True)
    m = VolumeBreakout().detect(extract_events(df), df, build_context(df))
    assert m is not None and m.tone == "bull" and m.confidence > 0
    assert any(s["label"].lower().startswith("breakout") for s in m.chain)
    assert any("volume" in s["label"].lower() for s in m.chain)


def test_silent_without_volume_confirmation():
    df = _series(breakout=True, with_volume=False)
    assert VolumeBreakout().detect(extract_events(df), df, build_context(df)) is None


def test_silent_without_breakout():
    df = _series(breakout=False)
    assert VolumeBreakout().detect(extract_events(df), df, build_context(df)) is None
