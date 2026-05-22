import pandas as pd
from app.signals.events import Event, extract_breakout, extract_volume_spike


def _df(rows):
    # rows: list of (date, close, high, low, volume); open inferred = close
    return pd.DataFrame([
        {"date": d, "open": c, "high": h, "low": lo, "close": c, "volume": v}
        for (d, c, h, lo, v) in rows
    ])


def test_breakout_emits_bull_on_new_n_day_high():
    # 20 flat bars at 100, then a close at 110 (new high) on the last bar.
    rows = [(f"2026-04-{i:02d}", 100, 101, 99, 1_000) for i in range(1, 21)]
    rows.append(("2026-05-01", 110, 111, 109, 1_000))
    events = extract_breakout(_df(rows), lookback=20)
    assert any(e.type == "breakout" and e.direction == "bull"
               and e.date == "2026-05-01" for e in events)


def test_breakout_silent_when_no_new_high():
    rows = [(f"2026-04-{i:02d}", 100, 101, 99, 1_000) for i in range(1, 22)]
    assert extract_breakout(_df(rows), lookback=20) == []


def test_volume_spike_emits_with_ratio_magnitude():
    rows = [(f"2026-04-{i:02d}", 100, 101, 99, 1_000) for i in range(1, 21)]
    rows.append(("2026-05-01", 100, 101, 99, 3_000))  # 3x avg
    events = extract_volume_spike(_df(rows), avg_period=20, k=2.0)
    spike = [e for e in events if e.type == "volume_spike"]
    assert spike and spike[-1].date == "2026-05-01"
    assert spike[-1].magnitude is not None and spike[-1].magnitude >= 2.0
