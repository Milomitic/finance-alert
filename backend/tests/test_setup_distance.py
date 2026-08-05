"""`distance_atr` — the per-setup half of "how close is this".

`proximity` answers "how much of the chain holds", which is the same number for
every setup of a detector at the same stage: measured live, ONE distinct value
across 20 trend_pullback rows. This field answers the question that number
cannot — is THIS stock a normal day's move from its trigger, or five.
"""
import pytest

from app.signals.setups.base import distance_to_trigger_atr


class TestScalesByVolatility:
    def test_the_same_price_gap_is_near_or_far_depending_on_the_stock(self):
        """The reason the unit is ATR and not percent.

        Both stocks sit €2 below their trigger. For the volatile one that is
        two-thirds of a typical day and could resolve tomorrow; for the quiet
        one it is four normal days of range. A percentage would call them
        identical, which is the comparison the page needs to get right.
        """
        volatile = distance_to_trigger_atr(last_close=98.0, level=100.0, atr_value=3.0)
        quiet = distance_to_trigger_atr(last_close=98.0, level=100.0, atr_value=0.5)
        assert volatile == pytest.approx(2 / 3, abs=1e-6)
        assert quiet == pytest.approx(4.0, abs=1e-6)
        assert volatile < quiet

    def test_touching_the_level_is_zero(self):
        assert distance_to_trigger_atr(100.0, 100.0, 2.0) == 0.0

    def test_direction_does_not_matter(self):
        # Distance, not signed displacement: a setup two ATR above its level is
        # exactly as far from firing as one two ATR below.
        above = distance_to_trigger_atr(104.0, 100.0, 2.0)
        below = distance_to_trigger_atr(96.0, 100.0, 2.0)
        assert above == below == pytest.approx(2.0)


class TestRefusesToInvent:
    @pytest.mark.parametrize(
        "close,level,atr",
        [
            (None, 100.0, 2.0),      # no price
            (100.0, None, 2.0),      # no level — e.g. a volatility trigger
            (100.0, 100.0, None),    # no ATR
        ],
    )
    def test_missing_inputs_give_none(self, close, level, atr):
        assert distance_to_trigger_atr(close, level, atr) is None

    def test_a_flat_instrument_gives_none_not_infinity(self):
        """ATR of zero means the stock has not moved at all in the window.
        Dividing by it would yield inf and sort to the very bottom (or top)
        of every ranking — a made-up answer for a stock we know nothing about.
        """
        assert distance_to_trigger_atr(100.0, 105.0, 0.0) is None
        assert distance_to_trigger_atr(100.0, 105.0, -1.0) is None

    def test_garbage_input_does_not_raise(self):
        # This runs inside the scan loop, where an exception would cost the
        # whole detector's setups for that stock.
        assert distance_to_trigger_atr("x", 100.0, 2.0) is None  # type: ignore[arg-type]


class TestRanksWithinADetector:
    def test_orders_setups_that_proximity_cannot_separate(self):
        """The point of the whole field.

        Three trend_pullback setups, all with proximity 0.80 because the gate
        chain is the same — but one is a fifth of a day's range from firing and
        another needs a three-day move. Sorting by distance separates them;
        sorting by proximity leaves them tied and falls back to whatever order
        the payload happened to arrive in.
        """
        rows = [
            ("SLOW", distance_to_trigger_atr(100.0, 106.0, 2.0)),   # 3.0 ATR
            ("NEAR", distance_to_trigger_atr(100.0, 100.4, 2.0)),   # 0.2 ATR
            ("MID", distance_to_trigger_atr(100.0, 102.0, 2.0)),    # 1.0 ATR
        ]
        assert [t for t, _ in sorted(rows, key=lambda r: r[1])] == ["NEAR", "MID", "SLOW"]
