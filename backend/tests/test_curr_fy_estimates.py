"""Current-FY consensus estimates (the estimate row of the annual table).

`_fy_avg_from_estimate_df` reads the `0y` row's `avg` from yfinance's
earnings_estimate / revenue_estimate tables — the full-year consensus VALUES
for the fiscal year in progress. Same never-raise tolerance contract as the
`growth` reader next to it. Old L2 cache rows lack the new Fundamentals
fields and must deserialize to None.
"""
import pandas as pd

from app.services import fetch_cache_store
from app.services.stock_fundamentals_service import (
    Fundamentals,
    _fy_avg_from_estimate_df,
)


def _estimate_df(avg_0y: float | None = 2.5) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "numberOfAnalysts": [30, 31, 32, 28],
            "avg": [0.6, 0.7, avg_0y, 3.1],
            "growth": [0.1, 0.12, 0.15, 0.24],
        },
        index=["0q", "+1q", "0y", "+1y"],
    )


def test_avg_reads_0y_row():
    assert _fy_avg_from_estimate_df(_estimate_df(avg_0y=21.9e9)) == 21.9e9


def test_avg_tolerates_missing_shapes():
    assert _fy_avg_from_estimate_df(None) is None
    assert _fy_avg_from_estimate_df(pd.DataFrame()) is None
    # No `avg` column
    df = pd.DataFrame({"growth": [0.1]}, index=["0y"])
    assert _fy_avg_from_estimate_df(df) is None
    # No `0y` row
    df = pd.DataFrame({"avg": [0.6]}, index=["0q"])
    assert _fy_avg_from_estimate_df(df) is None
    # NaN value
    assert _fy_avg_from_estimate_df(_estimate_df(avg_0y=float("nan"))) is None


def test_old_l2_payload_without_new_fields_defaults_to_none():
    """A cached row serialized BEFORE the fields existed must hydrate with
    None (additive-schema contract of _fundamentals_from_dict)."""
    old_payload = {"ticker": "AAPL", "annual": [], "quarterly": [], "earnings": []}
    f = fetch_cache_store._fundamentals_from_dict(old_payload)
    assert isinstance(f, Fundamentals)
    assert f.curr_fy_eps_estimate is None
    assert f.curr_fy_revenue_estimate is None


def test_fetch_fresh_populates_curr_fy_estimates(monkeypatch):
    """End-to-end through _fetch_fresh: a raw yfinance payload carrying the
    estimate tables must land on Fundamentals.curr_fy_*_estimate. This is the
    proof that a FORCED refresh (card ↻) populates the new row — the only
    reason it's missing in the UI is a cached payload older than the fields
    (fundamentals TTL is 7 days)."""
    from app.services import stock_fundamentals_service as sfs

    raw = {
        "earnings_estimate": _estimate_df(avg_0y=7.89),
        "revenue_estimate": _estimate_df(avg_0y=445.6e9),
    }
    monkeypatch.setattr(sfs, "_yf_fetch_with_retry", lambda t: raw)
    monkeypatch.setattr(sfs, "_throttle_upstream_fetch", lambda: None)

    f = sfs._fetch_fresh("AAPL")

    assert f.curr_fy_eps_estimate == 7.89
    assert f.curr_fy_revenue_estimate == 445.6e9
    # And the consensus growth (pre-existing behavior) still reads `growth`.
    assert f.micro.eps_growth_curr_fy == 0.15
