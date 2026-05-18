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


def test_keeps_sane_yfinance_values():
    """When yfinance's value is within normal noise of the value we'd
    derive from the reported-EPS series, yfinance is authoritative and
    must NOT be overridden."""
    f = Fundamentals(ticker="X")
    # Clean smooth series: YoY ≈ (0.67-0.59)/0.59 = +13.6%,
    # QoQ ≈ (0.67-0.64)/0.64 = +4.7%.
    f.earnings = [
        _eps("2025-04-30", 0.59),
        _eps("2025-07-31", 0.62),
        _eps("2025-10-31", 0.63),
        _eps("2026-01-31", 0.64),
        _eps("2026-05-07", 0.67),
    ]
    # yfinance gives values CLOSE to derived → kept verbatim.
    f.micro = MicroData(earnings_growth=0.14, earnings_quarterly_growth=0.05)
    _fill_growth_fallbacks(f)
    assert f.micro.earnings_growth == 0.14            # within noise → kept
    assert f.micro.earnings_quarterly_growth == 0.05  # within noise → kept


def test_reconciles_gross_yfinance_divergence_gen_case():
    """The GEN bug: yfinance's GAAP-net-income earningsGrowth explodes
    to +265% off a depressed prior-year base, while the smooth
    adjusted-EPS series (0.59→0.67) implies ~+14%. The metric shown
    next to that series must agree with it → override the absurd value
    with the history-derived one."""
    f = Fundamentals(ticker="GEN")
    f.earnings = [
        _eps("2025-04-30", 0.59),
        _eps("2025-07-31", 0.64),
        _eps("2025-11-06", 0.62),
        _eps("2026-02-05", 0.64),
        _eps("2026-05-07", 0.67),
    ]
    f.micro = MicroData(
        earnings_growth=2.652,            # yfinance GAAP artifact
        earnings_quarterly_growth=2.606,  # ditto
    )
    _fill_growth_fallbacks(f)
    # Derived YoY = (0.67-0.59)/0.59 ≈ 0.1356; QoQ = (0.67-0.64)/0.64 ≈ 0.0469
    assert abs(f.micro.earnings_growth - (0.67 - 0.59) / 0.59) < 1e-9
    assert abs(
        f.micro.earnings_quarterly_growth - (0.67 - 0.64) / 0.64
    ) < 1e-9


def test_opposite_sign_is_reconciled():
    """yfinance says contraction, our series says growth (or vice
    versa) → trust our series (it matches the displayed EPS trend)."""
    f = Fundamentals(ticker="X")
    f.earnings = [
        _eps("2025-04-30", 1.0),
        _eps("2025-07-31", 1.1),
        _eps("2025-10-31", 1.2),
        _eps("2026-01-31", 1.3),
        _eps("2026-05-07", 1.4),  # clearly growing
    ]
    f.micro = MicroData(earnings_growth=-0.30)  # source says -30% (wrong)
    _fill_growth_fallbacks(f)
    assert f.micro.earnings_growth == (1.4 - 1.0) / 1.0  # +40% derived


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
