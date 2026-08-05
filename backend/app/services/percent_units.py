"""Single owner of the dividend-yield percent normalization.

THE BUG THIS REPLACES. Three copies of the same heuristic lived in
`api/sectors.py`, `services/sector_stats_service.py` and
`services/score_service/pillars.py`, each carrying the same comment:

    # yfinance is inconsistent: <1 -> fraction, >=1 -> percent
    dy_pct = raw if raw > 1 else raw * 100.0

That belief was presumably true of some yfinance version. It is not true of
the data we actually store, and the heuristic cannot work even in principle:
it has no way to tell "0.25 meaning 0.25%" from "0.25 meaning 25%". Whenever a
company genuinely yields less than one percent — which is most of the growth
universe — the rule multiplies its yield by a hundred.

Measured over the 755 cached stocks that carry the field: MU reads 0.06
(Micron's real 0.06% yield) and the heuristic reported 6.00%; LAND.L reads
12.32 and is a REIT genuinely yielding 12.32%. The distribution is uniformly
PERCENT, exactly as `StockMicro.dividend_yield` documents at its declaration
("%, yfinance returns 1.81 = 1.81%"). 147 of those 755 — one stock in five —
sat at or below 1 and were being inflated a hundredfold.

It was not only a display defect. `pillars.py` fed the inflated value into the
Value pillar's dividend lane, where `abs_full=3.0` means "3% or better scores
top marks": a 0.06% yield read as 6% earned the maximum. The stocks affected
are precisely the low-yield growth names, so the error pushed their Qualità up.

WHY THIS FILE RE-SCALES NOTHING. The upstream contract says percent, the data
says percent, so the honest conversion is the identity. What it adds instead is
a plausibility ceiling: a yield above `MAX_PLAUSIBLE_PCT` is bad data, not a
unit mismatch, and is dropped with a warning rather than silently rescaled into
something that looks reasonable. Guessing at units is what produced the bug;
refusing to guess is the fix.

Same shape as `currency_units.py`, and for the same reason — logic that lives
in three places drifts in three directions.
"""
from __future__ import annotations

import math

from loguru import logger

# Above this, a "yield" is a data error rather than an exceptional payer. The
# highest genuine value in the catalog is 0881.HK at 13.04%; distressed names
# and special dividends can reach the twenties, so the ceiling sits well clear
# of anything real while still catching a stray fraction-scaled 100×.
MAX_PLAUSIBLE_PCT = 40.0


def _is_finite(v: object) -> bool:
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return not (math.isnan(f) or math.isinf(f))


def dividend_yield_pct(raw: float | None, *, ticker: str | None = None) -> float | None:
    """Dividend yield as a percentage, or None when unusable.

    The input is already a percentage — see the module docstring. Returns None
    for missing, non-finite, negative or implausible values, so callers get
    "unknown" rather than a number invented by a units guess.
    """
    if raw is None or not _is_finite(raw):
        return None
    v = float(raw)
    if v < 0:
        return None
    if v > MAX_PLAUSIBLE_PCT:
        # Loud, because the only ways to reach here are an upstream unit change
        # or corrupt data, and both want a human to look.
        logger.warning(
            f"[percent_units] dividend yield {v:.2f}% exceeds the plausible "
            f"ceiling of {MAX_PLAUSIBLE_PCT}%{f' for {ticker}' if ticker else ''} "
            "— dropped rather than rescaled"
        )
        return None
    return v
