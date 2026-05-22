import pandas as pd
from app.signals.context import build_context


def test_context_reports_uptrend_and_atr():
    rows = [{"date": f"2026-01-{i:02d}", "open": 100 + i, "high": 101 + i,
             "low": 99 + i, "close": 100 + i, "volume": 1000} for i in range(1, 31)]
    ctx = build_context(pd.DataFrame(rows))
    assert ctx.trend_sign == 1          # rising series -> up
    assert ctx.atr is not None and ctx.atr > 0
    assert ctx.last_close == 130.0
