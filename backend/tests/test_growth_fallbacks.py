"""`_fill_growth_fallbacks` derives EPS YoY/QoQ + Rev YoY from the
historical series when yfinance's `info` left them null."""
from app.services.stock_fundamentals_service import (
    EarningsPoint,
    Fundamentals,
    MicroData,
    QuarterlyPoint,
    _fill_growth_fallbacks,
    _growth,
)


def _eps(date: str, reported: float | None) -> EarningsPoint:
    return EarningsPoint(
        date=date, eps_estimate=None, eps_reported=reported,
        surprise_pct=None,
    )


def test_growth_formula():
    assert _growth(110, 100) == 0.10
    assert _growth(90, 100) == -0.10
    # loss → profit flip: sign tracks direction via abs(prior)
    assert _growth(2, -1) == 3.0
    assert _growth(5, 0) is None      # div-by-zero guard
    assert _growth(None, 100) is None
    assert _growth(100, None) is None


def test_qoq_filled_from_two_quarters():
    f = Fundamentals(ticker="X")
    f.micro = MicroData()  # all None
    f.earnings = [_eps("2026-01-31", 1.0), _eps("2026-04-30", 1.2)]
    _fill_growth_fallbacks(f)
    assert f.micro.earnings_quarterly_growth == (1.2 - 1.0) / 1.0


def test_yoy_eps_filled_from_five_quarters():
    f = Fundamentals(ticker="X")
    f.micro = MicroData()
    # 5 quarters: latest (idx -1) vs same quarter LY (idx -5)
    f.earnings = [
        _eps("2025-04-30", 2.0),  # -5 → prior-year same quarter
        _eps("2025-07-31", 2.1),
        _eps("2025-10-31", 2.2),
        _eps("2026-01-31", 2.3),
        _eps("2026-04-30", 2.6),  # -1 → latest
    ]
    _fill_growth_fallbacks(f)
    assert f.micro.earnings_growth == (2.6 - 2.0) / 2.0  # +30%
    # QoQ also gets filled (latest vs immediately prior)
    assert f.micro.earnings_quarterly_growth == (2.6 - 2.3) / 2.3


def test_does_not_overwrite_yfinance_values():
    f = Fundamentals(ticker="X")
    f.micro = MicroData(
        earnings_growth=0.99,            # yfinance gave it → authoritative
        earnings_quarterly_growth=0.88,
        revenue_growth=0.77,
    )
    f.earnings = [_eps("a", 1.0), _eps("b", 5.0)] * 3  # would compute big growth
    _fill_growth_fallbacks(f)
    assert f.micro.earnings_growth == 0.99
    assert f.micro.earnings_quarterly_growth == 0.88
    assert f.micro.revenue_growth == 0.77


def test_revenue_yoy_prefers_quarterly_statement():
    f = Fundamentals(ticker="X")
    f.micro = MicroData()
    f.quarterly = [
        QuarterlyPoint("2025-04-30", revenue=100.0, eps=1.0),
        QuarterlyPoint("2025-07-31", revenue=105.0, eps=1.1),
        QuarterlyPoint("2025-10-31", revenue=110.0, eps=1.2),
        QuarterlyPoint("2026-01-31", revenue=115.0, eps=1.3),
        QuarterlyPoint("2026-04-30", revenue=130.0, eps=1.4),
    ]
    _fill_growth_fallbacks(f)
    assert f.micro.revenue_growth == (130.0 - 100.0) / 100.0  # +30%


def test_revenue_yoy_falls_back_to_earnings_revenue_reported():
    f = Fundamentals(ticker="X")
    f.micro = MicroData()
    f.quarterly = []  # no clean statement → use earnings.revenue_reported
    eps = []
    for i, rev in enumerate([200.0, 210.0, 220.0, 230.0, 260.0]):
        e = _eps(f"2025-{i+1:02d}-01", 1.0)
        e.revenue_reported = rev
        eps.append(e)
    f.earnings = eps
    _fill_growth_fallbacks(f)
    assert f.micro.revenue_growth == (260.0 - 200.0) / 200.0  # +30%


def test_noop_when_insufficient_history():
    f = Fundamentals(ticker="X")
    f.micro = MicroData()
    f.earnings = [_eps("2026-04-30", 1.5)]  # only 1 point
    _fill_growth_fallbacks(f)
    assert f.micro.earnings_quarterly_growth is None
    assert f.micro.earnings_growth is None
    assert f.micro.revenue_growth is None
