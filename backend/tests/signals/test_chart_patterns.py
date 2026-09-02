import pandas as pd
import pytest

from app.signals.chart_patterns import extract_chart_patterns


def _df(closes):
    return pd.DataFrame([
        {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}",
         "open": c, "high": c + 1.0, "low": c - 1.0, "close": c, "volume": 1000}
        for i, c in enumerate(closes)
    ])


def _double_bottom():
    # Two clear V-shape lows at ~90, separated by a peak at ~100 (neckline),
    # then a break above 100. Each bottom is a single-point minimum so pivot
    # detection with pivot_w=2 finds exactly one pivot per trough.
    closes = (
        [100, 98, 96, 94, 92, 90, 92, 94, 96, 98, 100]  # V-shape bottom 1 (idx 5 = 90)
        + [100, 100]                                      # flat peak at ~100 (neckline)
        + [98, 96, 94, 92, 90, 92, 95, 98, 101, 104]     # V-shape bottom 2 + break above
    )
    return _df(closes)


def test_double_bottom_emitted():
    evs = extract_chart_patterns(_double_bottom(), pivot_w=2)
    assert any(e.type == "chart_pattern" and e.direction == "bull"
               and e.payload.get("pattern") == "double_bottom" for e in evs)


def _inverse_hns():
    # left shoulder low ~92, head low ~88, right shoulder low ~92, neckline highs ~100,
    # then break above 100.
    seg = (
        [100, 96, 92, 96, 100]        # down to left shoulder (92) and back up (neckline ~100)
        + [100, 95, 90, 88, 90, 95, 100]   # down to head (88) and back up
        + [100, 96, 92, 96, 100]      # down to right shoulder (92) and back up
        + [101, 103, 105]             # break above neckline
    )
    return _df([100] * 6 + seg)


def test_inverse_head_shoulders_emitted():
    evs = extract_chart_patterns(_inverse_hns(), pivot_w=2)
    assert any(e.type == "chart_pattern" and e.direction == "bull"
               and e.payload.get("pattern") == "inverse_head_shoulders" for e in evs)


def _ascending_triangle():
    # flat highs ~110, rising lows; then break above 110.
    seg = []
    lows_floor = [95, 99, 103]   # rising lows
    for k in range(3):
        seg += [lows_floor[k], 106, 110, 106, lows_floor[k]]  # up to flat top 110, back to a higher low
    seg += [111, 113]            # break above the flat resistance
    return _df([100] * 6 + seg)


def test_ascending_triangle_emitted():
    evs = extract_chart_patterns(_ascending_triangle(), pivot_w=2)
    assert any(e.type == "chart_pattern" and e.direction == "bull"
               and e.payload.get("pattern") == "ascending_triangle" for e in evs)


def test_flat_series_no_pattern():
    assert extract_chart_patterns(_df([100] * 60), pivot_w=2) == []


def _symmetrical_triangle():
    # converging: falling highs (110,107,104) + rising lows (96,98,100),
    # then a breakout above the last high.
    seg = []
    highs = [110, 107, 104]
    lows = [96, 98, 100]
    for k in range(3):
        seg += [lows[k], (lows[k] + highs[k]) / 2, highs[k], (lows[k] + highs[k]) / 2, lows[k]]
    seg += [106, 109]   # break above the most recent pivot high (104)
    return _df([100] * 6 + seg)


def test_symmetrical_triangle_emitted():
    evs = extract_chart_patterns(_symmetrical_triangle(), pivot_w=2)
    assert any(e.type == "chart_pattern"
               and e.payload.get("pattern") == "symmetrical_triangle" for e in evs)


# ── Triangle amplitude is MEASURED, not asserted ────────────────────────────
# Every test above checks only that a pattern is *emitted*. That is exactly why
# the defect survived: all three triangle branches hard-coded their magnitude
# (0.6 / 0.6 / 0.55) while the four other families computed real geometry, and
# no test looked at the number. Since `pattern_amplitude` is the only strength
# factor the detector weighs, a constant magnitude meant a constant Forza — so
# all 95 chart_pattern alerts in the warehouse sat at exactly two values.

def _ascending_triangle_with_base(lows_floor):
    """Same shape as `_ascending_triangle`, with the base depth as a parameter."""
    seg = []
    for k in range(3):
        seg += [lows_floor[k], 106, 110, 106, lows_floor[k]]
    seg += [111, 113]
    return _df([100] * 6 + seg)


def _only(evs, pattern):
    return next(e for e in evs if e.payload.get("pattern") == pattern)


def test_triangle_amplitude_varies_with_the_geometry():
    """THE regression test: put the constant back and this fails.

    Two ascending triangles, identical but for how deep the base runs. A
    measured amplitude separates them; a hard-coded one cannot."""
    shallow = _only(extract_chart_patterns(
        _ascending_triangle_with_base([95, 99, 103]), pivot_w=2), "ascending_triangle")
    deep = _only(extract_chart_patterns(
        _ascending_triangle_with_base([80, 90, 100]), pivot_w=2), "ascending_triangle")
    assert deep.magnitude > shallow.magnitude
    assert shallow.magnitude != pytest.approx(0.6)


def test_ascending_triangle_amplitude_is_height_over_the_flat_side():
    """The house convention, verbatim: pattern height as a fraction of price.
    `_df` puts the bar high at close+1 and the low at close-1, so the flat
    resistance sits at 111 and the base low at 94."""
    e = _only(extract_chart_patterns(
        _ascending_triangle_with_base([95, 99, 103]), pivot_w=2), "ascending_triangle")
    assert e.payload["neckline"] == pytest.approx(111.0)
    assert e.magnitude == pytest.approx((111.0 - 94.0) / 111.0, abs=1e-6)


def test_symmetrical_triangle_amplitude_is_the_base_of_the_cone():
    """Highs fall 110->104, lows rise 96->100, so the base pair is (111, 95)
    in bar terms and the amplitude is that height over the high side."""
    e = _only(extract_chart_patterns(_symmetrical_triangle(), pivot_w=2),
              "symmetrical_triangle")
    assert e.magnitude == pytest.approx((111.0 - 95.0) / 111.0, abs=1e-6)
    assert e.magnitude != pytest.approx(0.55)


def test_measured_amplitudes_stay_in_the_range_the_anchors_expect():
    """Guards the units, not the value. Real pattern heights run ~0.05-0.35 of
    price (measured: p50 .094, p95 .234, max .564 over 1,041 patterns). A
    magnitude near 0.6 would mean a figure 60% as tall as the share price, and
    is the signature of the old constant coming back."""
    for fixture, pattern in (
        (_ascending_triangle_with_base([95, 99, 103]), "ascending_triangle"),
        (_symmetrical_triangle(), "symmetrical_triangle"),
        (_double_bottom(), "double_bottom"),
        (_inverse_hns(), "inverse_head_shoulders"),
    ):
        e = _only(extract_chart_patterns(fixture, pivot_w=2), pattern)
        assert 0.0 < e.magnitude < 0.5, f"{pattern}: {e.magnitude}"
