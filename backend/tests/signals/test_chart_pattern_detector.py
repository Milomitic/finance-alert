import pandas as pd

from app.signals.context import build_context
from app.signals.detectors.base import SignalMatch
from app.signals.detectors.chart_pattern import ChartPattern
from app.signals.events import Event


def _df(last_close, n=40):
    closes = [100.0] * (n - 1) + [last_close]
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": c,
         "high": c + 1, "low": c - 1, "close": c, "volume": 1000}
        for i, c in enumerate(closes)])


def test_double_bottom_fires_after_neckline_break():
    df = _df(103)   # last close above the 100 neckline = confirmed break
    events = [Event("2026-02-10", "chart_pattern", "bull", magnitude=0.5,
                    payload={"pattern": "double_bottom", "neckline": 100.0})]
    m = ChartPattern().detect(events, df, build_context(df))
    assert isinstance(m, SignalMatch) and m.tone == "bull" and m.strength > 0
    assert any("doppio" in s["label"].lower() or "double" in s["label"].lower()
               or "neckline" in s["detail"].lower() for s in m.chain)
    # Two-score model: Forza in range, Probabilità within the empirical band.
    assert 0 < m.strength <= 99
    assert 5 <= m.probability <= 95


def test_silent_before_neckline_break():
    df = _df(98)    # still below the neckline -> not confirmed
    events = [Event("2026-02-10", "chart_pattern", "bull", magnitude=0.5,
                    payload={"pattern": "double_bottom", "neckline": 100.0})]
    assert ChartPattern().detect(events, df, build_context(df)) is None


def test_chart_pattern_annotations_have_neckline_and_points():
    df = _df(103)
    events = [Event("2026-02-10", "chart_pattern", "bull", magnitude=0.5,
                    payload={"pattern": "double_bottom", "neckline": 100.0,
                             "points": [{"date": "2026-01-20", "price": 90.0},
                                        {"date": "2026-01-28", "price": 100.0},
                                        {"date": "2026-02-05", "price": 90.5}]})]
    m = ChartPattern().detect(events, df, build_context(df))
    assert m is not None
    levels = m.annotations["levels"]; points = m.annotations["points"]
    assert any(l["kind"] == "neckline" for l in levels)
    assert len(points) >= 2


# ── The Forza anchors have to be in the units of the thing they anchor ───────
# `pattern_amplitude` is this detector's ONLY strength factor (weight 1.0), so
# `_PATTERN_AMPLITUDE_ANCHORS` IS the Forza curve. They used to be
# (0.40, 0.65, 0.80, 0.92) — asking for a figure 40-92% as tall as the share
# price. Measured over 1,041 real patterns the amplitudes run p50 .094 /
# p95 .234 / max .564, so the median pattern scored Forza 10.6 and exactly one
# pattern in 1,041 could clear the 60 emission gate. The four families that
# measured themselves honestly had never emitted a single alert.

_GATE = 60   # settings.signal_min_confidence

def _forza(magnitude):
    df = _df(103)
    events = [Event("2026-02-10", "chart_pattern", "bull", magnitude=magnitude,
                    payload={"pattern": "double_bottom", "neckline": 100.0})]
    m = ChartPattern().detect(events, df, build_context(df))
    return m.strength


def test_a_typical_pattern_is_not_crushed_to_zero():
    """p50 of the measured distribution must read as middling, not as noise.
    Under the old anchors this returned ~10."""
    assert 40 <= _forza(0.094) <= 50


def test_a_large_pattern_clears_the_emission_gate():
    """p85 (.165) and above must be able to emit — otherwise the detector is
    silent by construction, which is exactly what it was."""
    assert _forza(0.165) >= _GATE
    assert _forza(0.234) >= _GATE          # p95
    assert _forza(0.094) < _GATE           # p50 does not; the gate still selects


def test_forza_still_separates_two_real_patterns():
    """A constant magnitude gave a constant Forza. Distinct amplitudes across
    the real range must give distinct, ordered Forza."""
    vals = [_forza(m) for m in (0.054, 0.094, 0.165, 0.234, 0.321)]
    assert len(set(round(v, 3) for v in vals)) == 5
    assert vals == sorted(vals)
