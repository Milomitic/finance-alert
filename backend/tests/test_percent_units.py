"""The dividend-yield unit fix, held in place.

Every case here is drawn from the measurement that found the bug: 755 cached
stocks carrying `dividend_yield`, uniformly in percent, 147 of them at or below
1 and therefore inflated a hundredfold by the heuristic this replaces.
"""
import pytest

from app.services.percent_units import MAX_PLAUSIBLE_PCT, dividend_yield_pct


class TestSubOnePercentYields:
    """The whole bug. These are real tickers and real stored values."""

    @pytest.mark.parametrize(
        "ticker,stored,expected",
        [
            ("MU", 0.06, 0.06),      # Micron: a token dividend, not 6%
            ("PWR", 0.07, 0.07),
            ("MRVL", 0.13, 0.13),
            ("BAX", 0.14, 0.14),
        ],
    )
    def test_a_sub_one_percent_yield_stays_sub_one_percent(self, ticker, stored, expected):
        # The old rule read "0.06 < 1, so it must be a fraction" and returned
        # 6.00 — a hundredfold overstatement on one stock in five.
        assert dividend_yield_pct(stored, ticker=ticker) == pytest.approx(expected)

    def test_the_old_heuristic_would_have_failed_this(self):
        """Guards the intent, not the implementation.

        If someone reintroduces `v if v > 1 else v * 100`, this is the case
        that catches it: the value is unambiguous in the stored data and the
        two rules disagree by 100×.
        """
        old_rule = lambda v: v if v > 1 else v * 100.0  # noqa: E731
        assert old_rule(0.06) == pytest.approx(6.0)
        assert dividend_yield_pct(0.06) == pytest.approx(0.06)


class TestOrdinaryValues:
    @pytest.mark.parametrize("v", [1.81, 2.79, 3.29, 5.14, 9.07, 13.04])
    def test_percent_values_pass_through_unchanged(self, v):
        # 13.04 is 0881.HK, the catalog's genuine high — it must survive.
        assert dividend_yield_pct(v) == pytest.approx(v)

    def test_zero_is_a_real_answer_not_a_missing_one(self):
        # A company that pays nothing yields 0%. That is knowledge, and it
        # must not collapse to None the way an absent value does.
        assert dividend_yield_pct(0.0) == 0.0


class TestRefusesToGuess:
    def test_implausible_values_are_dropped_not_rescaled(self):
        """The design choice. A yield of 250% is a broken record, and dividing
        it by 100 to make it 'look right' is exactly the reasoning that
        produced the original bug. Unknown beats invented."""
        assert dividend_yield_pct(250.0) is None
        assert dividend_yield_pct(MAX_PLAUSIBLE_PCT + 0.01) is None

    def test_the_ceiling_leaves_real_payers_alone(self):
        assert dividend_yield_pct(MAX_PLAUSIBLE_PCT - 0.01) is not None
        assert dividend_yield_pct(25.0) == pytest.approx(25.0)

    @pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), -1.0, "x"])
    def test_unusable_input_yields_none(self, bad):
        assert dividend_yield_pct(bad) is None
