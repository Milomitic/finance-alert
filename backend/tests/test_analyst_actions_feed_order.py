"""Ordering of the analyst-actions feed.

`out.sort(key=lambda t: (t[0], t[1].ticker), reverse=True)` reversed the WHOLE
tuple, so the ticker tiebreak ran Z->A while the comment directly above it
promised A->Z. Same-day is the common case, not an edge one: several firms act
on one name, or on several names, on the same morning.
"""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services import analyst_actions_feed as feed


def _fund(ticker: str, day: str):
    return SimpleNamespace(
        ticker=ticker,
        analyst_actions=[SimpleNamespace(
            action="up", date=day, firm="Some Bank",
            to_grade="Buy", from_grade="Hold",
            current_price_target=None, prior_price_target=None,
            price_target_action=None, from_news=False,
        )],
    )


@pytest.fixture
def feed_of(monkeypatch):
    """Build the L1 cache the feed reads, in a deliberately UNSORTED insertion
    order — dicts preserve insertion order, so seeding alphabetically would let
    the buggy sort pass by accident."""
    def build(pairs):
        from app.services import stock_fundamentals_service as sfs
        monkeypatch.setattr(sfs, "_CACHE", {t: _fund(t, d) for t, d in pairs})
        return feed.recent_actions()
    return build


def _day(offset_days: int) -> str:
    return (datetime.now(UTC).date() - timedelta(days=offset_days)).isoformat()


def test_same_day_actions_are_alphabetical_by_ticker(feed_of):
    items = feed_of([("ZTS", _day(3)), ("AAPL", _day(3)), ("MSFT", _day(3))])
    assert [i.ticker for i in items] == ["AAPL", "MSFT", "ZTS"]


def test_the_newest_day_still_comes_first(feed_of):
    # The older AAPL must not jump ahead merely by being alphabetical.
    items = feed_of([("AAPL", _day(20)), ("ZTS", _day(1))])
    assert [i.ticker for i in items] == ["ZTS", "AAPL"]


def test_date_outranks_ticker_across_days(feed_of):
    items = feed_of([("BBB", _day(1)), ("AAA", _day(2)), ("CCC", _day(1))])
    assert [i.ticker for i in items] == ["BBB", "CCC", "AAA"]


def test_actions_older_than_the_window_are_dropped(feed_of):
    # Guards the freshness gate while we are here — 90 days is the cutoff.
    items = feed_of([("OLD", _day(200)), ("NEW", _day(2))])
    assert [i.ticker for i in items] == ["NEW"]
