"""Was this signal about this stock, or about the whole market that morning?

Measured over the live alert table, the answer varies enormously by detector:

    trend_pullback    fires alongside 43 other stocks on average (max 127)
    candle_reversal   29
    gap_and_go         2.7 (max 8)

So a `trend_pullback` is almost never idiosyncratic — it is a market-wide
condition that happened to touch this name — while a `gap_and_go` really is
about the stock. The platform has always known this and never said it, so
every alert reads the same whether one stock moved or a hundred did.

⚠️ IT IS CONTEXT, NEVER CONFIRMATION. CLAUDE.md records two independent
studies finding concurrence NULL at h=1/2/3/5 — knowing that forty names did
the same thing does not make the signal better. It changes what the READER
should conclude: if it is sector-wide, the stock is telling you nothing of its
own. That is why the count is honest to show and would be dishonest to fold
into Forza or Probabilità.
"""

from datetime import date, datetime

import pytest

from app.models import Alert, Stock
from app.services.signal_breadth_service import breadth_for


def _stock(db, ticker: str, sector: str | None = "Information Technology") -> Stock:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, sector=sector)
    db.add(s)
    db.commit()
    return s


def _alert(db, stock: Stock, name: str, on: date | None) -> Alert:
    a = Alert(
        stock_id=stock.id,
        signal_name=name,
        signal_date=on,
        triggered_at=datetime(2026, 9, 8, 10, 0),
        trigger_price=100.0,
        snapshot="{}",  # colonna Text, non JSON
    )
    db.add(a)
    db.commit()
    return a


D = date(2026, 9, 8)


class TestTheCount:
    def test_a_lone_signal_reports_no_company(self, db):
        me = _stock(db, "NVDA")
        a = _alert(db, me, "gap_and_go", D)

        got = breadth_for(db, [a], stock_id=me.id, sector=me.sector)

        assert got[a.id].others == 0

    def test_it_counts_the_other_stocks_that_fired_the_same_day(self, db):
        me = _stock(db, "NVDA")
        for t in ("AMD", "INTC", "MU"):
            _alert(db, _stock(db, t), "trend_pullback", D)
        a = _alert(db, me, "trend_pullback", D)

        assert breadth_for(db, [a], stock_id=me.id, sector=me.sector)[a.id].others == 3

    def test_the_stock_itself_is_never_one_of_the_others(self, db):
        me = _stock(db, "NVDA")
        a = _alert(db, me, "trend_pullback", D)
        # Same detector, same day, same stock — a re-fire, not a peer.
        _alert(db, me, "trend_pullback", D)

        assert breadth_for(db, [a], stock_id=me.id, sector=me.sector)[a.id].others == 0

    def test_a_different_detector_the_same_day_does_not_count(self, db):
        me = _stock(db, "NVDA")
        _alert(db, _stock(db, "AMD"), "candle_reversal", D)
        a = _alert(db, me, "trend_pullback", D)

        assert breadth_for(db, [a], stock_id=me.id, sector=me.sector)[a.id].others == 0

    def test_the_same_detector_on_a_different_day_does_not_count(self, db):
        me = _stock(db, "NVDA")
        _alert(db, _stock(db, "AMD"), "trend_pullback", date(2026, 9, 7))
        a = _alert(db, me, "trend_pullback", D)

        assert breadth_for(db, [a], stock_id=me.id, sector=me.sector)[a.id].others == 0


class TestTheSectorSplit:
    """The whole point is telling a sector move from a market move."""

    def test_it_separates_peers_in_the_same_sector(self, db):
        me = _stock(db, "NVDA", "Information Technology")
        _alert(db, _stock(db, "AMD", "Information Technology"), "trend_pullback", D)
        _alert(db, _stock(db, "MU", "Information Technology"), "trend_pullback", D)
        _alert(db, _stock(db, "XOM", "Energy"), "trend_pullback", D)
        a = _alert(db, me, "trend_pullback", D)

        got = breadth_for(db, [a], stock_id=me.id, sector=me.sector)[a.id]

        assert (got.others, got.same_sector) == (3, 2)

    def test_a_stock_with_no_sector_reports_others_but_no_split(self, db):
        me = _stock(db, "PURR", None)
        _alert(db, _stock(db, "AMD"), "trend_pullback", D)
        a = _alert(db, me, "trend_pullback", D)

        got = breadth_for(db, [a], stock_id=me.id, sector=me.sector)[a.id]

        assert (got.others, got.same_sector) == (1, 0)


class TestWhatItRefusesToDo:
    def test_it_does_NOT_exclude_archived_alerts(self, db):
        """A count that shrinks when the user files their inbox is not a count.

        CLAUDE.md's rule — never filter a measurement on a field the USER
        writes — was learned the expensive way: the outcome warehouse was
        showing 19 of its 4,880 rows because three consumers excluded archived
        alerts, and archival tracks AGE. Breadth is not an efficacy metric, but
        it would drift the same way, and "38 other stocks" would quietly
        become "12" months later with nothing having changed in the market.
        """
        me = _stock(db, "NVDA")
        peer = _alert(db, _stock(db, "AMD"), "trend_pullback", D)
        peer.archived_at = datetime(2026, 9, 9, 12, 0)
        db.commit()
        a = _alert(db, me, "trend_pullback", D)

        assert breadth_for(db, [a], stock_id=me.id, sector=me.sector)[a.id].others == 1

    def test_a_legacy_alert_without_a_signal_date_gets_nothing(self, db):
        # No bar date means no "that day" to compare against. Nothing is a
        # better answer than a zero that reads as "it was alone".
        me = _stock(db, "NVDA")
        a = _alert(db, me, "trend_pullback", None)

        assert a.id not in breadth_for(db, [a], stock_id=me.id, sector=me.sector)


def test_it_answers_a_whole_page_of_alerts_in_one_pass(db):
    # The detail card renders up to 50; this must not be 50 queries.
    me = _stock(db, "NVDA")
    _alert(db, _stock(db, "AMD"), "trend_pullback", D)
    _alert(db, _stock(db, "MU"), "candle_reversal", D)
    mine = [_alert(db, me, "trend_pullback", D), _alert(db, me, "candle_reversal", D)]

    got = breadth_for(db, mine, stock_id=me.id, sector=me.sector)

    assert {k: v.others for k, v in got.items()} == {mine[0].id: 1, mine[1].id: 1}


@pytest.mark.parametrize("alerts", [[], None])
def test_no_alerts_asks_nothing_of_the_database(db, alerts):
    assert breadth_for(db, alerts or [], stock_id=1, sector="Energy") == {}
