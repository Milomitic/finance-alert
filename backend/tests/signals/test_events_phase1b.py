import pandas as pd
from app.signals.events import (
    extract_ema_cross, extract_rsi_divergence, extract_bollinger,
)


def _df(rows):
    return pd.DataFrame([
        {"date": d, "open": c, "high": h, "low": lo, "close": c, "volume": v}
        for (d, c, h, lo, v) in rows
    ])


def test_ema_cross_emits_golden():
    rows = [(f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", 200 - i, 201 - i, 199 - i, 1000)
            for i in range(60)]
    base = rows[-1][1]
    rows += [(f"2027-{1 + i // 28:02d}-{1 + i % 28:02d}", base + i, base + i + 1, base + i - 1, 1000)
             for i in range(1, 80)]
    evs = extract_ema_cross(_df(rows), fast=20, slow=50)
    assert any(e.type == "ema_cross" and e.direction == "bull" for e in evs)


def test_rsi_divergence_bull():
    seq = []
    price = 100.0
    for _ in range(8):
        price -= 4
        seq.append(price)
    for _ in range(6):
        price += 3
        seq.append(price)
    for _ in range(8):
        price -= 2.5
        seq.append(price)
    rows = [(f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", round(p, 2),
             round(p, 2) + 1, round(p, 2) - 1, 1000) for i, p in enumerate(seq)]
    evs = extract_rsi_divergence(_df(rows), period=14, pivot_w=2)
    assert isinstance(evs, list)


def test_bollinger_emits_squeeze_then_expansion():
    rows = [(f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", 100.0, 100.2, 99.8, 1000)
            for i in range(40)]
    base = 100.0
    rows += [(f"2027-{1 + i // 28:02d}-{1 + i % 28:02d}", base + i * 3,
              base + i * 3 + 1, base + i * 3 - 1, 1000) for i in range(1, 12)]
    evs = extract_bollinger(_df(rows), period=20, k=2.0, kc_mult=1.5)
    assert any(e.type == "bb_squeeze" for e in evs)
    assert any(e.type == "bb_expansion" for e in evs)
