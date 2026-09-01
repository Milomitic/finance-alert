"""The risk classifier compares market cap against DOLLAR thresholds.

`stock.market_cap` is denominated in the listing currency, and the thresholds
are dollar figures — the docstrings say "> $200B" and "< $2B". Comparing them
directly judged a yen, won or Hong Kong dollar cap against a dollar bar.

Measured on the live catalogue: 158 names cleared 200e9 in native currency and
only 83 in USD, so 75 stocks were being scored as stable mega-caps without
being anything of the kind — 7270.T at $10.9bn, 033780.KS at $14.4bn,
0175.HK at $26.8bn.
"""
import pytest

from app.models import Stock
from app.services.score_service.common import _MEGA_CAP_THRESHOLD, _SMALL_CAP_THRESHOLD
from app.services.score_service.risk import _classify_risk


def _stock(cap, currency="USD"):
    return Stock(
        ticker="X", exchange="X", name="X", country="US",
        market_cap=cap, currency=currency,
    )


class TestCurrencyIsConverted:
    def test_a_yen_cap_below_the_dollar_bar_is_not_a_mega_cap(self):
        """7270.T shape: 1,746bn JPY clears 200e9 as a bare number and is
        $10.9bn in reality."""
        native = _classify_risk(_stock(1_746_000_000_000.0, "JPY"), None, None)
        assert native == _classify_risk(_stock(10_900_000_000.0, "USD"), None, None)

    def test_a_won_cap_is_converted(self):
        # 033780.KS: 19,812bn KRW = $14.4bn.
        assert _classify_risk(_stock(19_812_000_000_000.0, "KRW"), None, None) ==             _classify_risk(_stock(14_400_000_000.0, "USD"), None, None)

    def test_a_genuine_dollar_mega_cap_still_counts(self):
        big = _classify_risk(_stock(_MEGA_CAP_THRESHOLD * 2, "USD"), None, None)
        mid = _classify_risk(_stock(_MEGA_CAP_THRESHOLD / 10, "USD"), None, None)
        assert big != mid

    def test_the_small_cap_side_is_unchanged_on_this_catalogue(self):
        """Honest scope. The mega-cap half moved 75 stocks; the small-cap half
        moved NONE — measured, 6 names sit under $2B either way. A weak
        currency inflates the raw number, so it pushes stocks OVER a bar, not
        under one, and this universe holds no company small enough for the
        two readings to disagree. The conversion is still right; its effect
        here is simply one-sided, and claiming otherwise would overstate it.
        """
        # 1bn JPY is ~$6.6M: genuinely small in both readings.
        assert _classify_risk(_stock(1_000_000_000.0, "JPY"), None, None) ==             _classify_risk(_stock(1_000_000_000.0, "USD"), None, None)


class TestItCountsAsAnInput:
    def test_market_cap_alone_produces_a_tier(self):
        """It used to not increment `inputs`, so a stock whose only available
        signal was its size fell through to `inputs == 0` and was scored
        "moderate" regardless of how large or small it was."""
        mega = _classify_risk(_stock(_MEGA_CAP_THRESHOLD * 3, "USD"), None, None)
        small = _classify_risk(_stock(_SMALL_CAP_THRESHOLD / 4, "USD"), None, None)
        assert mega != small


class TestMissingData:
    @pytest.mark.parametrize("cap,cur", [(None, "USD"), (None, None)])
    def test_no_market_cap_does_not_raise(self, cap, cur):
        assert _classify_risk(_stock(cap, cur), None, None) is not None

    def test_an_unknown_currency_does_not_raise(self):
        assert _classify_risk(_stock(1_000_000_000.0, "ZZZ"), None, None) is not None
