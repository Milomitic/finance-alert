"""The three Esplora leaderboards.

The tests worth reading here are `TestRanksOpinionNotVolatility` (the design
decision the board exists to encode) and `TestReadsToneFromTheSnapshot` (the
bug this module nearly shipped with).
"""
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.models import Alert, Stock, StockScore, TechnicalScore
from app.services import leaderboard_service as svc
from app.services.leaderboard_service import (
    _analyst_rank,
    _signal_counts,
    build_leaderboards,
    soft_min,
    upside_pct,
)


def _stock(db, ticker, *, quality=None, technical=None, sector="Tech"):
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US", sector=sector)
    db.add(s)
    db.flush()
    now = datetime.now(UTC)
    if quality is not None:
        db.add(StockScore(
            stock_id=s.id, composite=quality,
            risk_tier="medium", computed_at=now, breakdown="{}",
        ))
    if technical is not None:
        db.add(TechnicalScore(
            stock_id=s.id, composite=technical,
            posture="neutral", computed_at=now, breakdown="{}",
        ))
    db.commit()
    return s


def _alert(db, stock, *, tone="bull", detector="volume_breakout", days_ago=1, archived=False):
    db.add(
        Alert(
            stock_id=stock.id,
            trigger_price=10.0,
            signal_name=detector,
            triggered_at=datetime.now(UTC) - timedelta(days=days_ago),
            archived_at=datetime.now(UTC) if archived else None,
            snapshot=json.dumps({"tone": tone, "strength": 70, "chain": []}),
        )
    )
    db.commit()


def _fake_fundamentals(*, mean, current, rec, n_analysts):
    return SimpleNamespace(
        micro=SimpleNamespace(recommendation_mean=rec, number_of_analyst_opinions=n_analysts),
        price_target=SimpleNamespace(mean=mean, current=current),
    )


@pytest.fixture
def cache(monkeypatch):
    """A populated stand-in for the fundamentals L1 cache.

    Non-empty on purpose: `_fundamentals_cache` hydrates from the DB when it
    finds L1 cold, and a test must not depend on that path.
    """
    fake: dict = {"__warm__": None}
    monkeypatch.setattr("app.services.stock_fundamentals_service._CACHE", fake)
    return fake


class TestReadsToneFromTheSnapshot:
    """`alerts` has NO `tone` column — tone lives inside the `snapshot` JSON.

    This was written after the first draft of the service grouped by
    `Alert.tone`. That version imports fine, type-checks fine, and would have
    raised only at query time; worse, an ORM that tolerated it would have
    returned an empty board, which reads as "no signals lately" rather than as
    a bug. Anyone who later "optimises" this into a column read fails here.
    """

    def test_counts_bull_and_bear_from_json(self, db):
        s = _stock(db, "AAA")
        _alert(db, s, tone="bull")
        _alert(db, s, tone="bull", detector="macd_cross")
        _alert(db, s, tone="bear")

        tally = _signal_counts(db)[s.id]
        assert (tally.bull, tally.bear) == (2, 1)

    def test_counts_distinct_bullish_detectors(self, db):
        """Ten fires of one detector is one thing happening repeatedly."""
        s = _stock(db, "AAA")
        for _ in range(5):
            _alert(db, s, tone="bull", detector="volume_breakout")
        _alert(db, s, tone="bull", detector="macd_cross")

        tally = _signal_counts(db)[s.id]
        assert tally.bull == 6
        assert len(tally.bull_detectors) == 2

    def test_archived_alerts_are_excluded(self, db):
        s = _stock(db, "AAA")
        _alert(db, s, tone="bull")
        _alert(db, s, tone="bull", archived=True)

        assert _signal_counts(db)[s.id].bull == 1

    def test_alerts_older_than_the_window_are_excluded(self, db):
        s = _stock(db, "AAA")
        _alert(db, s, tone="bull", days_ago=2)
        _alert(db, s, tone="bull", days_ago=svc.SIGNAL_WINDOW_DAYS + 5)

        assert _signal_counts(db)[s.id].bull == 1


class TestSoftMin:
    def test_disagreement_does_not_average_into_a_good_score(self):
        """The whole reason this is not a mean.

        90/30 is a stock one lens likes and the other does not. A plain average
        calls it 60 — better than an honest 55/55, which both lenses agree is
        mediocre-but-consistent. The floor has to decide.
        """
        disagree = soft_min(90.0, 30.0)
        agree = soft_min(55.0, 55.0)
        assert disagree == pytest.approx(42.0)  # 30 + 12 slack, not 60
        assert agree > disagree

    def test_agreement_still_earns_more_than_a_hard_minimum(self):
        # 80/78 is genuinely better than 80/60; a hard min would call them 78 vs
        # 60 — right ordering, but it throws away that both lenses are strong.
        assert soft_min(80.0, 78.0) == pytest.approx(79.0)
        assert soft_min(80.0, 78.0) > soft_min(80.0, 60.0)

    def test_is_symmetric(self):
        assert soft_min(70.0, 40.0) == soft_min(40.0, 70.0)


class TestUpsidePct:
    def test_computes_the_gap_to_target(self):
        assert upside_pct(120.0, 100.0) == pytest.approx(20.0)

    def test_rejects_a_target_below_the_price(self):
        # Not "top picks": the sell side thinks it is worth less than it costs.
        assert upside_pct(90.0, 100.0) is None

    def test_rejects_an_implausible_gap(self):
        """A +400% target is a stale figure or a pre-collapse leftover far more
        often than a real call. Dropped rather than shown — same rule as the
        dividend-yield ceiling in percent_units."""
        assert upside_pct(500.0, 100.0) is None
        assert upside_pct(100.0 + svc.MAX_PLAUSIBLE_UPSIDE_PCT, 100.0) is not None

    @pytest.mark.parametrize("target,price", [(None, 100.0), (120.0, None), (120.0, 0.0)])
    def test_refuses_to_invent(self, target, price):
        assert upside_pct(target, price) is None


class TestRanksOpinionNotVolatility:
    """The measurement that shaped this board.

    Ranking the live cache by raw target gap returned APLD +144%, CRVS +138%,
    NTLA +137%, ONDS +122%, USAR +120% — microcap biotech, crypto miners and
    defence-tech, several covered by 7-8 analysts. A wide target gap is mostly
    a statement about how UNCERTAIN a name is; sorting by it builds a
    volatility filter wearing an analyst costume. The user asked for picks
    "in base alle valutazioni degli analisti", so the opinion has to outrank
    its variance.
    """

    def test_broad_conviction_beats_a_thinly_covered_lottery_ticket(self):
        # The exact shape of the case above: NVDA-like against CRVS-like.
        covered = _analyst_rank(up_pct=46.0, recommendation=1.30, n_analysts=58)
        speculative = _analyst_rank(up_pct=138.0, recommendation=1.12, n_analysts=7)
        assert covered > speculative

    def test_upside_still_matters_when_conviction_is_equal(self):
        more_room = _analyst_rank(up_pct=40.0, recommendation=1.5, n_analysts=20)
        less_room = _analyst_rank(up_pct=10.0, recommendation=1.5, n_analysts=20)
        assert more_room > less_room

    def test_a_hold_consensus_scores_below_a_buy_consensus(self):
        buy = _analyst_rank(up_pct=30.0, recommendation=1.2, n_analysts=20)
        hold = _analyst_rank(up_pct=30.0, recommendation=3.0, n_analysts=20)
        assert buy > hold

    def test_upside_saturates_rather_than_running_away(self):
        """A 100% gap is a bigger call than 25%, not four times bigger. Without
        saturation the room term dominates and the board reverts to the
        microcap list this design rejects."""
        a = _analyst_rank(up_pct=25.0, recommendation=1.5, n_analysts=20)
        b = _analyst_rank(up_pct=100.0, recommendation=1.5, n_analysts=20)
        assert b > a
        assert (b - a) < (a * 0.5)


class TestBuildLeaderboards:
    def test_returns_the_three_boards(self, db, cache):
        assert set(build_leaderboards(db)) == {"analysts", "combined", "signals"}

    def test_combined_needs_both_lenses(self, db, cache):
        _stock(db, "BOTH", quality=70.0, technical=80.0)
        _stock(db, "QONLY", quality=95.0)  # no technical score

        combined = build_leaderboards(db)["combined"]
        assert [r.ticker for r in combined] == ["BOTH"]

    def test_signals_board_needs_net_bullishness(self, db, cache):
        up = _stock(db, "UP", quality=50.0, technical=50.0)
        down = _stock(db, "DOWN", quality=50.0, technical=50.0)
        _alert(db, up, tone="bull")
        _alert(db, up, tone="bull", detector="macd_cross")
        _alert(db, down, tone="bull")
        _alert(db, down, tone="bear")  # net zero — not "firing bullish"

        assert [r.ticker for r in build_leaderboards(db)["signals"]] == ["UP"]

    def test_analyst_board_gates_on_coverage_and_consensus(self, db, cache):
        _stock(db, "GOOD")
        _stock(db, "THIN")
        _stock(db, "SOLD")
        cache["GOOD"] = _fake_fundamentals(mean=130.0, current=100.0, rec=1.4, n_analysts=25)
        # Enough upside, but too few voices for the consensus to mean anything.
        cache["THIN"] = _fake_fundamentals(mean=180.0, current=100.0, rec=1.1, n_analysts=2)
        # Well covered, but the sell side is not positive.
        cache["SOLD"] = _fake_fundamentals(mean=130.0, current=100.0, rec=3.8, n_analysts=30)

        assert [r.ticker for r in build_leaderboards(db)["analysts"]] == ["GOOD"]

    def test_analyst_rows_carry_what_the_ui_shows(self, db, cache):
        _stock(db, "GOOD")
        cache["GOOD"] = _fake_fundamentals(mean=130.0, current=100.0, rec=1.4, n_analysts=25)

        row = build_leaderboards(db)["analysts"][0]
        assert row.upside_pct == pytest.approx(30.0)
        assert (row.analysts, row.recommendation) == (25, 1.4)
        assert (row.target, row.last_close) == (130.0, 100.0)

    def test_a_cold_fundamentals_cache_costs_only_the_analyst_board(self, db, cache):
        """Degrade one board, not the page. The other two read from the DB."""
        _stock(db, "AAA", quality=70.0, technical=75.0)
        boards = build_leaderboards(db)
        assert boards["analysts"] == []
        assert [r.ticker for r in boards["combined"]] == ["AAA"]

    def test_ties_break_on_ticker_so_the_order_is_stable(self, db, cache):
        _stock(db, "ZZZ", quality=60.0, technical=60.0)
        _stock(db, "AAA", quality=60.0, technical=60.0)

        assert [r.ticker for r in build_leaderboards(db)["combined"]] == ["AAA", "ZZZ"]

    def test_limit_is_respected(self, db, cache):
        for i in range(10):
            _stock(db, f"S{i:02d}", quality=50.0 + i, technical=50.0 + i)

        assert len(build_leaderboards(db, limit=3)["combined"]) == 3
