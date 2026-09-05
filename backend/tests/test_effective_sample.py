"""Effective sample size: overlapping signal windows are NOT independent.

The warehouse counts one row per matured signal, and every consumer so far has
treated those rows as independent observations. They are not. A detector that
fires on 88 different stocks across 34 trading days inside one quarter, each
labeled on a 21-day forward window, has produced something much closer to
THREE observations than to ninety-nine: the windows overlap almost completely,
and on any given day the whole cross-section shares one market.

Measured on the live warehouse 2026-09-04, `macd_divergence` bull read 81.8%
market-neutral on n=99 — a number that would be extraordinary if it were 99
draws, and is unremarkable as 3 overlapping quarters of a rising tape. Sizing
a confidence interval on n instead of on the independent count is what turns
the second into the first.

This mirrors rule A in CLAUDE.md (market-wide conditions are counted in TIME
BLOCKS, not stock-episodes), which was learned the expensive way: the first
conditional-screen grid reported 9 survivors, all false, because a cell
credited with 12,054 "independent episodes" was 4-13 contiguous occurrences of
one market state.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.services.detector_performance_service import (
    independent_blocks,
    sized_interval,
)

# --------------------------------------------------------------------------- #
# independent_blocks                                                          #
# --------------------------------------------------------------------------- #

def test_no_dates_is_no_blocks():
    assert independent_blocks([], 21) == 0


def test_signals_inside_one_horizon_are_one_observation():
    """Ten fires on ten consecutive days, each labeled 21 trading days forward.
    Their windows overlap by at least 11/21 — this is one episode, not ten."""
    d = date(2026, 6, 1)
    dates = [d + timedelta(days=i) for i in range(10)]
    assert independent_blocks(dates, 21) == 1


def test_signals_beyond_the_horizon_are_separate_observations():
    """Two fires 60 calendar days apart: the first window closed long before
    the second opened, so they carry independent information."""
    dates = [date(2026, 6, 1), date(2026, 7, 31)]
    assert independent_blocks(dates, 21) == 2


def test_block_boundary_is_the_horizon_in_calendar_days():
    """21 trading days spans 30 calendar days (the 7/5 weekday factor). A fire
    inside that span joins the open block; one past it opens a new one."""
    d = date(2026, 6, 1)
    assert independent_blocks([d, d + timedelta(days=29)], 21) == 1
    assert independent_blocks([d, d + timedelta(days=30)], 21) == 2


def test_order_does_not_matter():
    """Callers hand us warehouse rows in whatever order the query returned."""
    d = date(2026, 6, 1)
    scrambled = [d + timedelta(days=x) for x in (90, 0, 45, 1, 91)]
    assert independent_blocks(scrambled, 21) == independent_blocks(
        sorted(scrambled), 21
    )


def test_duplicate_dates_collapse():
    """A detector firing on 23 stocks on one day saw ONE day of market."""
    d = date(2026, 7, 29)
    assert independent_blocks([d] * 23, 21) == 1


def test_the_live_macd_divergence_shape():
    """The case that motivated this: ~99 fires over 34 distinct days inside a
    single quarter. The honest denominator is a small handful, not 99."""
    start = date(2026, 5, 15)
    days = [start + timedelta(days=i * 2) for i in range(34)]  # 34 days, ~68 apart end to end
    dates = [d for d in days for _ in range(3)]  # ~3 stocks per day
    n_blocks = independent_blocks(dates, 21)
    assert len(dates) == 102
    assert 2 <= n_blocks <= 4, f"expected a handful of blocks, got {n_blocks}"


# --------------------------------------------------------------------------- #
# sized_interval — the CI must be widened by the OVERLAP, not by the row count #
# --------------------------------------------------------------------------- #

def test_clustered_sample_yields_an_uninformative_interval():
    """100 rows that are really one episode cannot distinguish 80% from a coin
    flip. The interval must still contain 50."""
    lo, hi = sized_interval(rate_pct=80.0, effective_n=1)
    assert lo < 50.0 < hi


def test_independent_sample_yields_a_tight_interval():
    """The same 80% earned across 100 independent windows excludes 50 easily."""
    lo, hi = sized_interval(rate_pct=80.0, effective_n=100)
    assert lo > 50.0
    assert hi - lo < 20.0


def test_interval_widens_as_independence_falls():
    """The monotonicity that makes the whole thing honest."""
    wide = sized_interval(rate_pct=60.0, effective_n=3)
    narrow = sized_interval(rate_pct=60.0, effective_n=300)
    assert (wide[1] - wide[0]) > (narrow[1] - narrow[0])


def test_zero_effective_n_is_fully_uninformative():
    lo, hi = sized_interval(rate_pct=100.0, effective_n=0)
    assert (lo, hi) == (0.0, 100.0)


def test_interval_is_bounded_to_a_percentage():
    """Wilson, not Wald: a 100% rate must not produce an upper bound above 100
    nor a lower bound below 0."""
    for rate in (0.0, 100.0):
        lo, hi = sized_interval(rate_pct=rate, effective_n=5)
        assert 0.0 <= lo <= hi <= 100.0


# --------------------------------------------------------------------------- #
# The horizon has to travel with the count                                    #
# --------------------------------------------------------------------------- #

def test_cell_reports_the_horizon_that_set_the_block_length():
    """Without it the window count is unreadable: `candle_reversal` shows 16
    independent windows and `trend_pullback` shows 1 over the SAME three and a
    half months, purely because one is labeled 5 trading days forward and the
    other 63. A reader who cannot see that concludes the column is arbitrary.
    """
    from datetime import date as _d
    from types import SimpleNamespace

    from app.services.detector_performance_service import _cell

    def row(horizon: int, day: int):
        return SimpleNamespace(
            abs_hit=1, mkt_neutral_hit=1, fwd_return=0.01,
            signal_date=_d(2026, 5, 15) + timedelta(days=day),
            horizon_days=horizon,
        )

    short = _cell("totale", [row(5, i * 7) for i in range(15)], 30)
    long_ = _cell("totale", [row(63, i * 7) for i in range(15)], 30)

    assert short["horizon_days"] == 5
    assert long_["horizon_days"] == 63
    # Same fires, same span — only the horizon differs, and it dominates.
    assert short["effective_n"] > long_["effective_n"]
