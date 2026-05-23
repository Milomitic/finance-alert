import pandas as pd
from app.signals.events import extract_rsi_extreme, extract_sr_levels


def _df(closes):
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": c,
         "high": c + 1, "low": c - 1, "close": c, "volume": 1000}
        for i, c in enumerate(closes)
    ])


def test_rsi_extreme_emits_oversold_on_sharp_drop():
    closes = [100] * 20 + [100 - i * 4 for i in range(1, 12)]
    evs = extract_rsi_extreme(_df(closes), period=14, low=30, high=70)
    assert any(e.type == "rsi_extreme" and e.direction == "bull" for e in evs)


def test_sr_levels_emit_support_and_resistance():
    closes = []
    for _ in range(4):
        closes += [100, 104, 108, 104, 100, 96, 92, 96, 100]
    evs = extract_sr_levels(_df(closes), width=2)
    kinds = {e.payload.get("kind") for e in evs if e.type == "sr_level"}
    assert "support" in kinds and "resistance" in kinds
