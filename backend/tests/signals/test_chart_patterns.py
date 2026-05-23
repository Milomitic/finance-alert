import pandas as pd
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


def test_flat_series_no_pattern():
    assert extract_chart_patterns(_df([100] * 60), pivot_w=2) == []
