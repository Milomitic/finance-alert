"""The market-neutral benchmark must be TONE-SYMMETRIC.

Every "market-neutral hit rate" in this repo is `signal beat the universe
benchmark that day`, sign-flipped for bear-tone signals. That only means
anything if a zero-skill signal scores 50%. Cross-sectional forward returns are
right-skewed, so the MEAN does not satisfy this: a few large winners drag it
above the typical stock, and most stocks sit below it.

Measured over 400 real stocks / ~1M stock-days, the fraction of stock-days
beating each benchmark with no skill involved at all:

          h=5      h=21     h=63
    mean  49.29%   48.37%   47.12%
    med   49.94%   49.94%   49.94%

So the mean charges every bull-tone detector 1.6pp at h=21 and 2.9pp at h=63,
and credits every bear-tone one the same amount. That asymmetry fabricated the
trend_pullback regime artifact (CLAUDE.md, conditional-screen invariant #3),
and `signal_detector_outcomes` — which writes the `mkt_neutral_hit` and
`quality_tag` the UI shows — was still using the mean until 2026-09-02.
"""
import numpy as np
import pytest

from app.scripts.signal_factor_outcomes import (
    _universe_mean_fwd,
    _universe_median_fwd,
)


class _Stock:
    """Minimal stand-in for the loader's row: dates + closes is all the two
    benchmark helpers touch."""
    def __init__(self, dates, closes):
        self.dates = dates
        self.closes = np.asarray(closes, dtype=float)


def _skewed_universe(n_stocks=60, n_days=40, seed=7):
    """A right-skewed cross-section: most names drift mildly, a few compound
    hard. This is the shape of a real equity cross-section, and the shape that
    separates a mean from a median."""
    rng = np.random.default_rng(seed)
    dates = [f"2026-01-{d:02d}" for d in range(1, n_days + 1)]
    out = []
    for i in range(n_stocks):
        # lognormal daily steps: heavy right tail, bounded left
        step = rng.lognormal(mean=0.0, sigma=0.02, size=n_days)
        if i < 3:
            step *= 1.05          # the handful of big compounders
        out.append(_Stock(dates, 100.0 * np.cumprod(step)))
    return out


def _fraction_beating(universe, bench, h):
    d2i = bench["_date_to_idx"]
    beat = tot = 0
    for s in universe:
        c = s.closes
        if len(c) <= h:
            continue
        with np.errstate(divide="ignore", invalid="ignore"):
            fwd = np.where(c[:-h] > 0, c[h:] / c[:-h] - 1.0, np.nan)
        for k, d in enumerate(s.dates[:-h]):
            b = bench[h][d2i[d]]
            if not (np.isfinite(fwd[k]) and np.isfinite(b)):
                continue
            beat += fwd[k] > b
            tot += 1
    return beat / tot if tot else float("nan")


def test_the_median_benchmark_is_tone_symmetric():
    """The property the whole market-neutral column rests on."""
    uni = _skewed_universe()
    med = _universe_median_fwd(uni)
    for h in (5, 21):
        frac = _fraction_beating(uni, med, h)
        assert abs(frac - 0.5) < 0.02, f"h={h}: {frac:.4f} non è simmetrico"


def test_the_mean_benchmark_is_not_symmetric_on_skewed_returns():
    """Documents WHY the median is required. If this ever stops failing to be
    symmetric, the fixture stopped being right-skewed and the test above is no
    longer proving anything."""
    uni = _skewed_universe()
    mean = _universe_mean_fwd(uni)
    frac = _fraction_beating(uni, mean, 21)
    assert frac < 0.49, f"la media dovrebbe essere sbilanciata, invece {frac:.4f}"


def test_both_helpers_agree_on_the_calendar():
    """The swap at each call site is one identifier, which is only safe while
    the two return the identical date->index map."""
    uni = _skewed_universe()
    assert (_universe_mean_fwd(uni)["_date_to_idx"]
            == _universe_median_fwd(uni)["_date_to_idx"])


def test_the_median_is_the_cross_section_median_not_something_near_it():
    """Pin the actual value on a hand-checkable cross-section."""
    dates = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04",
             "2026-01-05", "2026-01-06", "2026-01-07"]
    # 5 stocks, 1-bar forward returns on day 0 of +1%, +2%, +3%, +4%, +100%
    uni = [_Stock(dates, [100.0 * (1 + r) ** i for i in range(len(dates))])
           for r in (0.01, 0.02, 0.03, 0.04, 1.00)]
    med = _universe_median_fwd(uni)
    mean = _universe_mean_fwd(uni)
    i0 = med["_date_to_idx"]["2026-01-01"]
    # 5-bar forward returns are (1+r)^5 - 1 for r in .01 .02 .03 .04 1.00.
    expected = sorted((1 + r) ** 5 - 1 for r in (0.01, 0.02, 0.03, 0.04, 1.00))[2]
    assert med[5][i0] == pytest.approx(expected, rel=1e-9)
    # The +100%/bar name sits far above every other stock, so it drags the mean
    # above ALL FIVE of them — the median is unmoved by it.
    assert mean[5][i0] > max((1 + r) ** 5 - 1 for r in (0.01, 0.02, 0.03, 0.04))
    assert med[5][i0] < mean[5][i0]
