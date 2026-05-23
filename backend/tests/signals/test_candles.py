import pandas as pd
from app.signals.candles import extract_candle_reversal


def _df(rows):
    # rows: list of (open, high, low, close)
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}",
         "open": o, "high": h, "low": lo, "close": c, "volume": 1000}
        for i, (o, h, lo, c) in enumerate(rows)
    ])


def test_bullish_engulfing():
    rows = [(100, 101, 99, 100)] * 5
    rows.append((99, 100, 98, 98.5))      # small bearish
    rows.append((98, 103, 97.5, 102))     # bullish body engulfs prior body
    evs = extract_candle_reversal(_df(rows))
    assert any(e.type == "candle_reversal" and e.direction == "bull"
               and e.payload.get("pattern") == "engulfing" for e in evs)


def test_hammer():
    rows = [(100 - i, 101 - i, 99 - i, 100 - i) for i in range(6)]   # downtrend
    rows.append((95, 95.3, 90, 95.1))     # tiny body on top, long lower wick
    evs = extract_candle_reversal(_df(rows))
    assert any(e.type == "candle_reversal" and e.direction == "bull"
               and e.payload.get("pattern") == "hammer" for e in evs)


def test_shooting_star():
    rows = [(100 + i, 101 + i, 99 + i, 100 + i) for i in range(6)]   # uptrend
    rows.append((105, 110, 104.8, 105.1))  # tiny body at bottom, long upper wick
    evs = extract_candle_reversal(_df(rows))
    assert any(e.type == "candle_reversal" and e.direction == "bear"
               and e.payload.get("pattern") == "shooting_star" for e in evs)


def test_flat_series_no_pattern():
    evs = extract_candle_reversal(_df([(100, 100.5, 99.5, 100)] * 30))
    assert all(e.payload.get("pattern") not in ("engulfing", "hammer", "shooting_star")
               for e in evs) or evs == []
