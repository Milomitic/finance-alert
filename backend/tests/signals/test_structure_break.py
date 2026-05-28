import pandas as pd
from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.structure_break import StructureBreak


def _df(closes, high_offset=1.0, low_offset=1.0):
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": c,
         "high": c + high_offset, "low": c - low_offset, "close": c, "volume": 1000}
        for i, c in enumerate(closes)
    ])


def _uptrend_then_break_down():
    # 3 confirmed rising swings (HH+HL) then a close below the last higher-low.
    # High pivots land at bars 3, 10, 17 (values 112, 117, 122 with +2 offset).
    # Low pivots land at bars 6, 13, 20 (values 102, 106, 110 with -2 offset).
    # Last bar close = 108 < last HL pivot low = 110 -> bear CHoCH.
    closes = [
        100, 103, 106, 110, 108, 105, 104,   # swing 1: peak 110, trough 104
        107, 111, 113, 115, 113, 110, 108,   # swing 2: peak 115, trough 108
        111, 114, 117, 120, 118, 115, 112,   # swing 3: peak 120, trough 112
        115, 118, 121, 122,                  # swing 4 partial peak 122
        108,                                 # break: below last HL (112 - 2 = 110)
    ]
    return _df(closes, high_offset=2.0, low_offset=2.0)


def test_bear_choch_breaks_last_higher_low():
    df = _uptrend_then_break_down()
    m = StructureBreak().detect([], df, build_context(df))
    assert isinstance(m, SignalMatch) and m.tone == "bear" and m.strength > 0
    assert any("struttura" in s["label"].lower() for s in m.chain)
    # Two-score model: Forza in range, Probabilità within the empirical band.
    assert 0 < m.strength <= 99
    assert 5 <= m.probability <= 95


def test_silent_on_intact_uptrend():
    df = _df([100 + i for i in range(40)])
    assert StructureBreak().detect([], df, build_context(df)) is None


def test_structure_break_annotations_has_primary_level():
    df = _uptrend_then_break_down()
    m = StructureBreak().detect([], df, build_context(df))
    assert m is not None
    levels = m.annotations["levels"]
    assert len(levels) >= 1
    primary = levels[0]
    assert primary["kind"] in ("support", "resistance")
    assert primary["label"] == "Livello protetto"
    assert isinstance(primary["price"], float)
