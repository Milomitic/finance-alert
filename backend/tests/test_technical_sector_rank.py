"""Where this stock's technical posture sits AMONG ITS SECTOR PEERS.

The Qualità card has carried a sector percentile for a while; the Tecnico lens
never did, and the gap matters because the two answer different questions.

`rel_strength` is ALREADY measured against the whole universe — CLAUDE.md's
worked example is TIT.MI reading 100.0, "the HIGHEST in the whole universe" —
so a universe percentile of it would be a percentile of a percentile. The
SECTOR rank is the part that is genuinely missing: a stock can be unremarkable
across the catalogue and still be the strongest name in a weak sector, and
those are different things to know.

Ranking is on the technical COMPOSITE, which is what the card leads with, not
on rel_strength.
"""

from datetime import UTC, datetime

from app.models import Stock, TechnicalScore
from app.services.technical_sector_rank import sector_rank


def _scored(db, ticker: str, sector: str | None, composite: float) -> Stock:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, sector=sector)
    db.add(s)
    db.flush()
    db.add(
        TechnicalScore(
            stock_id=s.id,
            composite=composite,
            posture="Neutro",
            breakdown="{}",  # colonna NOT NULL
            computed_at=datetime.now(UTC),
        )
    )
    db.commit()
    return s


class TestTheRank:
    def test_the_strongest_in_its_sector_is_first(self, db):
        me = _scored(db, "NVDA", "Tech", 90.0)
        _scored(db, "AMD", "Tech", 70.0)
        _scored(db, "INTC", "Tech", 50.0)

        assert sector_rank(db, me.id, "Tech", 90.0) == (1, 3)

    def test_the_weakest_is_last(self, db):
        _scored(db, "NVDA", "Tech", 90.0)
        _scored(db, "AMD", "Tech", 70.0)
        me = _scored(db, "INTC", "Tech", 50.0)

        assert sector_rank(db, me.id, "Tech", 50.0) == (3, 3)

    def test_a_tie_takes_the_better_rank(self, db):
        # Two stocks at 90 are both "joint first", not first and second. The
        # alternative would make the rank depend on insertion order.
        me = _scored(db, "NVDA", "Tech", 90.0)
        _scored(db, "AMD", "Tech", 90.0)
        _scored(db, "INTC", "Tech", 50.0)

        assert sector_rank(db, me.id, "Tech", 90.0) == (1, 3)

    def test_only_peers_in_the_SAME_sector_count(self, db):
        me = _scored(db, "NVDA", "Tech", 50.0)
        _scored(db, "XOM", "Energy", 99.0)
        _scored(db, "CVX", "Energy", 98.0)

        # Two stronger names exist, neither is a peer.
        assert sector_rank(db, me.id, "Tech", 50.0) == (1, 1)

    def test_a_peer_without_a_technical_score_is_not_counted(self, db):
        me = _scored(db, "NVDA", "Tech", 50.0)
        db.add(Stock(ticker="PURR", exchange="NASDAQ", name="PURR", sector="Tech"))
        db.commit()

        assert sector_rank(db, me.id, "Tech", 50.0) == (1, 1)


class TestWhenItDeclinesToAnswer:
    def test_a_stock_with_no_sector_has_no_peers(self, db):
        me = _scored(db, "PURR", None, 50.0)
        _scored(db, "NVDA", "Tech", 90.0)

        assert sector_rank(db, me.id, None, 50.0) == (None, None)

    def test_a_stock_with_no_composite_cannot_be_ranked(self, db):
        me = _scored(db, "NVDA", "Tech", 50.0)

        assert sector_rank(db, me.id, "Tech", None) == (None, None)

    def test_being_alone_in_a_sector_is_reported_honestly(self, db):
        # "1 of 1" is not a ranking, and the UI needs the peer count to say so
        # rather than showing a proud first place.
        me = _scored(db, "PURR", "Esoteric", 50.0)

        assert sector_rank(db, me.id, "Esoteric", 50.0) == (1, 1)
