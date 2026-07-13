import pandas as pd

from app.signals.events import extract_adx_trend, extract_gap, extract_macd_cross


def _df(rows):
    # rows: (close, high, low) ; open defaults to close unless 4th given
    out = []
    for i, r in enumerate(rows):
        c, h, lo = r[0], r[1], r[2]
        op = r[3] if len(r) > 3 else c
        out.append({"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}",
                    "open": op, "high": h, "low": lo, "close": c, "volume": 1000})
    return pd.DataFrame(out)


def test_macd_cross_emits_bull_when_line_crosses_up():
    closes = [100 - i for i in range(40)] + [60 + i * 2 for i in range(20)]
    evs = extract_macd_cross(_df([(c, c + 1, c - 1) for c in closes]))
    assert any(e.type == "macd_cross" and e.direction == "bull" for e in evs)


def test_gap_emits_up_on_open_above_prev_close():
    rows = [(100, 101, 99) for _ in range(5)]
    rows.append((110, 112, 108, 108))   # open 108 vs prev close 100 -> +8% gap up
    evs = extract_gap(_df(rows), min_pct=0.02)
    assert any(e.type == "gap" and e.direction == "bull" for e in evs)


def test_adx_trend_emits_bull_in_strong_uptrend():
    closes = [100 + i * 2 for i in range(40)]   # strong, steady uptrend
    evs = extract_adx_trend(_df([(c, c + 1, c - 1) for c in closes]), period=14, adx_min=20)
    assert any(e.type == "adx_trend" and e.direction == "bull" for e in evs)


def test_macd_divergence_returns_list():
    closes = [100 - i for i in range(20)] + [80 + (i % 3) for i in range(20)]
    from app.signals.events import extract_macd_divergence
    evs = extract_macd_divergence(_df([(c, c + 1, c - 1) for c in closes]))
    assert isinstance(evs, list)   # smoke: deterministic MACD divergence is hard to synthesise
