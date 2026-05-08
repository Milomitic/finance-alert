"""Country-aware classifier for earnings release timing.

Given a UTC HH:MM string for when an earnings was released and the listing
country, return "pre" | "after" | None to drive the sun/moon icon in the
calendar and stock-detail UIs.

This logic was originally inlined in `calendar_service._classify_session_timing`
-- extracted here so the stock-detail API can reuse it without importing
calendar_service (which itself imports stock_fundamentals_service, creating
a dependency hairball).

The thresholds are deliberately wide (using winter-DST UTC offsets) so the
icon is informational rather than authoritative:
  - US: 14:30 UTC = NYSE/NASDAQ open, 21:00 UTC = close.
    Times < 14:30 -> "pre"; times >= 21:00 -> "after"; mid-session -> None.
  - Other countries: currently None (no session model yet -- we'd rather
    show no icon than a wrong one).
"""
from typing import Literal


def classify_session_timing(
    time_utc: str | None, country: str | None
) -> Literal["pre", "after"] | None:
    """Return "pre" | "after" | None for the given earnings release timestamp."""
    if not time_utc or not country:
        return None
    try:
        h, m = time_utc.split(":")
        minutes = int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None
    if country == "US":
        # 14:30 UTC = 870 minutes (NYSE open); 21:00 UTC = 1260 minutes (close)
        if minutes < 14 * 60 + 30:
            return "pre"
        if minutes >= 21 * 60:
            return "after"
        return None
    # Other markets: heuristic only -- we don't model their sessions yet.
    return None
