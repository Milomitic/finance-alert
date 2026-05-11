"""Tests for app.services.score_service (V2 — comprehensive + missing-data neutral).

Three layers:
1. Sub-score boundary tests (pure functions on stub Stock + MicroData inputs).
2. Risk classification edge cases.
3. recompute_all integration.

Plus a dedicated section for the V2 missing-data-neutralization invariant:
adding a None component must NOT lower the pillar score.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd
import pytest
from sqlalchemy.orm import Session

from app.models import OhlcvDaily, Stock, StockScore
from app.services import score_service, stock_fundamentals_service, stock_news_service
from app.services.score_service import (
    PILLAR_WEIGHTS,
    _build_score,
    _classify_risk,
    _quality,
    _growth,
    _momentum,
    _renormalize_weights,
    _sentiment,
    _value,
)
from app.services.stock_fundamentals_service import (
    AnalystAction,
    AnalystPriceTarget,
    AnnualPoint,
    EarningsPoint,
    Fundamentals,
    MicroData,
)


def _stock(
    *,
    id: int = 1,
    ticker: str = "TEST",
    sector: str | None = "Technology",
    market_cap: int | None = 50_000_000_000,
) -> Stock:
    return Stock(
        id=id,
        ticker=ticker,
        exchange="NMS",
        name=f"{ticker} Corp",
        sector=sector,
        country="US",
        market_cap=market_cap,
    )


# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------

def test_quality_all_good_full_score():
    """All present components at their best values → pillar ≈ 100."""
    micro = MicroData(
        return_on_equity=0.30, return_on_assets=0.20,
        profit_margins=0.25, operating_margins=0.25, gross_margins=0.60,
        free_cashflow=1e10,
        debt_to_equity=30.0, current_ratio=2.5, quick_ratio=2.0,
        overall_risk=1.0,
        held_percent_insiders=0.15, held_percent_institutions=0.80,
    )
    score, mx, br = _quality(_stock(), micro)
    assert mx == 100.0
    assert score == pytest.approx(100.0, abs=0.5)
    # Components are present.
    assert br["roe"]["present"] is True
    assert br["fcf"]["score"] == 100.0


def test_quality_all_bad_zero_score():
    micro = MicroData(
        return_on_equity=-0.05, return_on_assets=-0.05,
        profit_margins=-0.10, operating_margins=-0.10, gross_margins=0.05,
        free_cashflow=-1e9,
        debt_to_equity=300.0, current_ratio=0.5, quick_ratio=0.3,
        overall_risk=10.0,
        held_percent_insiders=0.0, held_percent_institutions=0.0,
    )
    score, _, _ = _quality(_stock(), micro)
    assert score == pytest.approx(0.0, abs=1.0)


def test_quality_missing_micro_returns_none():
    score, mx, br = _quality(_stock(), None)
    assert score is None
    assert br == {}


# ---------------------------------------------------------------------------
# Growth
# ---------------------------------------------------------------------------

def test_growth_all_good():
    micro = MicroData(
        revenue_growth=0.25, earnings_growth=0.30, earnings_quarterly_growth=0.30,
        eps_trailing=4.0, eps_forward=5.0,
    )
    earnings = [
        EarningsPoint(date=f"2025-0{i}-01", eps_estimate=1.0, eps_reported=1.2, surprise_pct=20.0)
        for i in range(1, 5)
    ]
    annual = [
        AnnualPoint(fiscal_year_end="2023-12-31", revenue=100_000_000, net_income=10_000_000, eps=1.0),
        AnnualPoint(fiscal_year_end="2024-12-31", revenue=115_000_000, net_income=11_000_000, eps=1.1),
        AnnualPoint(fiscal_year_end="2025-12-31", revenue=132_000_000, net_income=13_000_000, eps=1.3),
    ]
    f = Fundamentals(ticker="TEST", micro=micro, earnings=earnings, annual=annual)
    score, _, br = _growth(_stock(), f)
    assert score == pytest.approx(100.0, abs=2.0)
    assert br["earnings_beats"]["raw"] == 4


def test_growth_zero_when_all_negative():
    micro = MicroData(
        revenue_growth=-0.20, earnings_growth=-0.20, earnings_quarterly_growth=-0.30,
    )
    earnings = [
        EarningsPoint(date=f"2025-0{i}-01", eps_estimate=1.0, eps_reported=0.5, surprise_pct=-50.0)
        for i in range(1, 5)
    ]
    f = Fundamentals(ticker="TEST", micro=micro, earnings=earnings)
    score, _, _ = _growth(_stock(), f)
    assert score == pytest.approx(0.0, abs=2.0)


def test_growth_missing_components_neutralised():
    """No earnings history, no quarterly growth, no annual revenue:
    only revenue_growth + earnings_growth contribute. Their full-marks
    score must NOT be diluted by the missing components."""
    micro = MicroData(revenue_growth=0.20, earnings_growth=0.20)
    f = Fundamentals(ticker="TEST", micro=micro, earnings=[])
    score, _, br = _growth(_stock(), f)
    assert score == pytest.approx(100.0, abs=1.0)
    assert br["earnings_beats"]["present"] is False
    assert br["qoq_earnings_growth"]["present"] is False
    assert br["revenue_cagr_3y"]["present"] is False


# ---------------------------------------------------------------------------
# Value
# ---------------------------------------------------------------------------

def test_value_full_when_well_below_sector_median():
    """V3: scoring is now blended (50% absolute + 50% sector-relative).
    To get 100 a multiple needs to be in the absolute "full" zone AND
    < 0.7x the sector median. Tests the full-score path explicitly."""
    from app.services.sector_stats_service import SectorStats, SectorStatsBundle
    bundle = SectorStatsBundle()
    # Tech sector medians chosen so the stock multiples sit comfortably
    # below the 0.7x threshold for full sector-relative score.
    bundle.by_sector["Technology"] = SectorStats(
        sector="Technology", n=20,
        pe_median=30.0, forward_pe_median=28.0, peg_median=2.0,
        pb_median=5.0, ps_median=4.0, ev_ebitda_median=15.0,
        ev_revenue_median=4.0, dividend_yield_median=0.5,
    )
    micro = MicroData(
        # All multiples deliberately well below the sector medians and
        # below the absolute "full" thresholds (22 / 1.0 / 3.0 / 2.0 / 8 / 2).
        trailing_pe=15.0, forward_pe=15.0, peg_ratio=0.5,
        price_to_book=2.0, price_to_sales=1.0,
        enterprise_to_ebitda=5.0, enterprise_to_revenue=1.0,
        dividend_yield=0.04, payout_ratio=0.45,
    )
    score, _, br = _value(_stock(sector="Technology"), micro, last_close=200.0,
                          sector_stats=bundle)
    assert br["pe"]["score"] == pytest.approx(100.0, abs=0.5)
    assert br["peg"]["score"] == pytest.approx(100.0, abs=0.5)
    assert br["dividend_yield"]["score"] == pytest.approx(100.0, abs=0.5)
    assert score == pytest.approx(100.0, abs=2.0)


def test_value_zero_when_well_above_sector_median():
    """V3: zero score requires both absolute zone (>=44 P/E) AND >1.5x
    sector median for sector-relative. Tests the zero-score path."""
    from app.services.sector_stats_service import SectorStats, SectorStatsBundle
    bundle = SectorStatsBundle()
    bundle.by_sector["Technology"] = SectorStats(
        sector="Technology", n=20,
        pe_median=20.0, peg_median=1.5, pb_median=3.0, ps_median=3.0,
        ev_ebitda_median=10.0, ev_revenue_median=3.0, dividend_yield_median=3.0,
    )
    micro = MicroData(
        # Multiples chosen well above absolute "zero" thresholds AND
        # >1.5x sector medians for the LIB-multiple ratio test.
        trailing_pe=56.0, peg_ratio=3.5,
        price_to_book=15.0, price_to_sales=12.0,
        enterprise_to_ebitda=30.0, enterprise_to_revenue=12.0,
        dividend_yield=0.0,
    )
    score, _, br = _value(_stock(sector="Technology"), micro, last_close=200.0,
                          sector_stats=bundle)
    assert br["pe"]["score"] == pytest.approx(0.0, abs=0.5)
    assert br["peg"]["score"] == pytest.approx(0.0, abs=0.5)
    assert br["dividend_yield"]["score"] == pytest.approx(0.0, abs=0.5)
    assert score == pytest.approx(0.0, abs=2.0)


def test_value_missing_micro_returns_none():
    score, _, br = _value(_stock(), None, last_close=100.0)
    assert score is None
    assert br == {}


# ---------------------------------------------------------------------------
# Momentum
# ---------------------------------------------------------------------------

def _strong_uptrend_closes(n: int = 260, start: float = 100.0, drift: float = 0.5) -> pd.Series:
    return pd.Series([start + drift * i for i in range(n)])


def _strong_downtrend_closes(n: int = 260, start: float = 200.0, drift: float = -0.5) -> pd.Series:
    return pd.Series([max(1.0, start + drift * i) for i in range(n)])


def test_momentum_strong_uptrend_high_score():
    closes = _strong_uptrend_closes()
    micro = MicroData(fifty_two_week_change=0.60, sp500_fifty_two_week_change=0.10)
    score, _, br = _momentum(_stock(), micro, closes)
    assert score is not None
    assert score >= 60.0
    assert br["change_52w"]["score"] == 100.0
    assert br["macd"]["score"] == 100.0


def test_momentum_strong_downtrend_low_score():
    closes = _strong_downtrend_closes()
    micro = MicroData(fifty_two_week_change=-0.40, sp500_fifty_two_week_change=0.10)
    score, _, br = _momentum(_stock(), micro, closes)
    assert score is not None
    assert score < 35.0
    assert br["macd"]["raw"]["state"] == "bearish_or_flat"


def test_momentum_no_inputs_returns_none():
    score, _, br = _momentum(_stock(), None, None)
    assert score is None
    assert br == {}


# ---------------------------------------------------------------------------
# Sentiment
# ---------------------------------------------------------------------------

def test_sentiment_full_score():
    today = date.today()
    actions = [
        AnalystAction(
            date=(today - timedelta(days=10 * (i + 1))).isoformat(),
            firm=f"F{i}", to_grade="Buy", from_grade="Hold", action="up",
        )
        for i in range(3)
    ]
    f = Fundamentals(
        ticker="TEST",
        micro=MicroData(recommendation_mean=1.5, short_percent_of_float=0.005),
        price_target=AnalystPriceTarget(mean=240.0),
        analyst_actions=actions,
    )
    score, _, _ = _sentiment(
        _stock(), f, last_close=200.0,
        news_polarity=80.0, news_count=25,
    )
    assert score == pytest.approx(100.0, abs=2.0)


def test_sentiment_zero_score():
    today = date.today()
    actions = [
        AnalystAction(
            date=(today - timedelta(days=10 * (i + 1))).isoformat(),
            firm=f"F{i}", to_grade="Sell", from_grade="Hold", action="down",
        )
        for i in range(3)
    ]
    f = Fundamentals(
        ticker="TEST",
        micro=MicroData(recommendation_mean=4.5, short_percent_of_float=0.30),
        price_target=AnalystPriceTarget(mean=180.0),  # -10% downside
        analyst_actions=actions,
    )
    score, _, _ = _sentiment(
        _stock(), f, last_close=200.0,
        news_polarity=-80.0, news_count=0,
    )
    assert score == pytest.approx(0.0, abs=2.0)


def test_sentiment_old_actions_excluded():
    today = date.today()
    actions = [
        AnalystAction(
            date=(today - timedelta(days=120)).isoformat(),
            firm="GS", to_grade="Buy", from_grade="Hold", action="up",
        ),
    ]
    f = Fundamentals(ticker="TEST", analyst_actions=actions)
    _, _, br = _sentiment(
        _stock(), f, last_close=200.0,
        news_polarity=None, news_count=10,
    )
    assert br["net_upgrades_90d"]["present"] is False


# ---------------------------------------------------------------------------
# MISSING-DATA NEUTRALIZATION INVARIANT — V2's headline guarantee.
# ---------------------------------------------------------------------------

def test_quality_missing_components_do_not_drag_score_down():
    """A stock with only ROE + ROA + FCF reported, all at full marks,
    should score ≈100 — the absent components must NOT dilute."""
    micro_full = MicroData(return_on_equity=0.30, return_on_assets=0.20, free_cashflow=1e10)
    score, _, _ = _quality(_stock(), micro_full)
    assert score == pytest.approx(100.0, abs=0.5)


def test_value_missing_components_do_not_drag_score_down():
    """Only P/E and dividend present, both at full → pillar ≈ 100."""
    micro = MicroData(trailing_pe=20.0, dividend_yield=0.04)
    score, _, _ = _value(_stock(sector="Technology"), micro, last_close=100.0)
    assert score == pytest.approx(100.0, abs=0.5)


def test_growth_dense_vs_sparse_same_signal_same_score():
    """Same signal magnitude (full marks across) should give same score
    whether the inputs are dense (all 6 components) or sparse (only 2).
    This is the precise statement of the missing-data invariant."""
    # Dense: all components at full marks.
    micro_dense = MicroData(
        revenue_growth=0.20, earnings_growth=0.20, earnings_quarterly_growth=0.25,
        eps_trailing=2.0, eps_forward=2.4,
    )
    earnings = [
        EarningsPoint(date=f"2025-0{i}-01", eps_estimate=1.0, eps_reported=1.2, surprise_pct=20.0)
        for i in range(1, 5)
    ]
    annual = [
        AnnualPoint(fiscal_year_end="2023-12-31", revenue=100, net_income=10, eps=1.0),
        AnnualPoint(fiscal_year_end="2024-12-31", revenue=115, net_income=12, eps=1.15),
        AnnualPoint(fiscal_year_end="2025-12-31", revenue=132, net_income=14, eps=1.32),
    ]
    f_dense = Fundamentals(ticker="A", micro=micro_dense, earnings=earnings, annual=annual)
    s_dense, _, _ = _growth(_stock(), f_dense)

    # Sparse: only revenue_growth + earnings_growth at full marks.
    f_sparse = Fundamentals(
        ticker="B",
        micro=MicroData(revenue_growth=0.20, earnings_growth=0.20),
    )
    s_sparse, _, _ = _growth(_stock(), f_sparse)

    # The headline guarantee: if the present components are at full marks,
    # the score should be ~100 regardless of how many components are
    # actually present.
    assert s_dense == pytest.approx(100.0, abs=2.0)
    assert s_sparse == pytest.approx(100.0, abs=2.0)


def test_sentiment_only_news_polarity_present():
    """Even if every analyst input is missing, news polarity alone should
    be enough to produce a sentiment score (not zero, not None)."""
    score, _, br = _sentiment(
        _stock(), Fundamentals(ticker="T"),
        last_close=None,
        news_polarity=50.0, news_count=10,
    )
    assert score is not None
    # news_polarity=50 → full (100); news_count=10 → ramps. Most other
    # components missing → neutralised. Score should be high.
    assert score >= 70.0
    assert br["news_polarity"]["present"] is True
    assert br["price_target_upside"]["present"] is False


def test_pillar_dropped_when_all_components_missing():
    """A pillar with zero present components → returns None and is
    dropped from the composite via _renormalize_weights."""
    score, _, br = _quality(_stock(), MicroData())  # all fields default None
    assert score is None
    assert br == {}


# ---------------------------------------------------------------------------
# Renormalization
# ---------------------------------------------------------------------------

def test_renormalize_skips_missing_pillars():
    """V3.2 has 6 pillars: profitability, sustainability, growth,
    value, momentum, sentiment. PILLAR_WEIGHTS sum to 1.0. When one
    pillar is None, renormalisation rescales the rest proportionally."""
    sub = {
        "profitability": 80.0,
        "sustainability": 70.0,
        "growth": 60.0,
        "value": 50.0,
        "momentum": 70.0,
        "sentiment": None,
    }
    w = _renormalize_weights(sub)
    assert w["sentiment"] == 0.0
    assert sum(w.values()) == pytest.approx(1.0, abs=1e-9)
    # profitability weight 0.15 / sum-of-present-weights
    present_total = (
        PILLAR_WEIGHTS["profitability"] + PILLAR_WEIGHTS["sustainability"]
        + PILLAR_WEIGHTS["growth"] + PILLAR_WEIGHTS["value"]
        + PILLAR_WEIGHTS["momentum"]
    )
    assert w["profitability"] == pytest.approx(
        PILLAR_WEIGHTS["profitability"] / present_total, abs=1e-9
    )


def test_renormalize_all_missing_returns_zero_weights():
    sub = {k: None for k in PILLAR_WEIGHTS}
    w = _renormalize_weights(sub)
    assert all(v == 0.0 for v in w.values())


def test_renormalize_all_present_gives_original_weights():
    sub = {k: 50.0 for k in PILLAR_WEIGHTS}
    w = _renormalize_weights(sub)
    for k in PILLAR_WEIGHTS:
        assert w[k] == pytest.approx(PILLAR_WEIGHTS[k], abs=1e-9)


# ---------------------------------------------------------------------------
# Risk classification
# ---------------------------------------------------------------------------

def test_risk_defensive_low_beta_mega_cap_is_conservative():
    s = _stock(sector="Utilities", market_cap=300_000_000_000)
    micro = MicroData(beta=0.5)
    tier = _classify_risk(s, micro, volatility_90d=0.8)
    assert tier == "conservative"


def test_risk_high_beta_small_cap_cyclical_is_aggressive():
    s = _stock(sector="Technology", market_cap=2_000_000_000)
    micro = MicroData(beta=1.8)
    tier = _classify_risk(s, micro, volatility_90d=4.5)
    assert tier == "aggressive"


def test_risk_default_moderate_when_inputs_balance():
    s = _stock(sector=None, market_cap=10_000_000_000)
    micro = MicroData(beta=1.0)
    tier = _classify_risk(s, micro, volatility_90d=2.0)
    assert tier == "moderate"


def test_risk_no_inputs_defaults_moderate():
    s = _stock(sector=None, market_cap=None)
    micro = MicroData(beta=None)
    tier = _classify_risk(s, micro, volatility_90d=None)
    assert tier == "moderate"


def test_risk_high_leverage_pushes_aggressive():
    """High debt/equity should add to the aggressive tally even if the
    other inputs are neutral."""
    s = _stock(sector=None, market_cap=10_000_000_000)
    micro = MicroData(beta=1.0, debt_to_equity=350.0)  # very levered
    tier = _classify_risk(s, micro, volatility_90d=2.0)
    assert tier == "aggressive"


# ---------------------------------------------------------------------------
# Pure compute path: _build_score
# ---------------------------------------------------------------------------

def test_build_score_all_pillars_present():
    closes = _strong_uptrend_closes()
    micro = MicroData(
        return_on_equity=0.25, return_on_assets=0.15,
        profit_margins=0.20, operating_margins=0.20, gross_margins=0.50,
        free_cashflow=1e10,
        debt_to_equity=40.0, current_ratio=2.0, quick_ratio=1.5,
        overall_risk=2.0,
        held_percent_insiders=0.10, held_percent_institutions=0.70,
        revenue_growth=0.20, earnings_growth=0.20, earnings_quarterly_growth=0.20,
        eps_trailing=4.0, eps_forward=4.8,
        trailing_pe=20.0, forward_pe=18.0, peg_ratio=1.0,
        price_to_book=4.0, price_to_sales=2.0,
        enterprise_to_ebitda=8.0, enterprise_to_revenue=2.0,
        dividend_yield=0.03, payout_ratio=0.45,
        beta=1.0, fifty_two_week_change=0.50, sp500_fifty_two_week_change=0.10,
        recommendation_mean=1.8, short_percent_of_float=0.02,
    )
    earnings = [
        EarningsPoint(date=f"2025-0{i}-01", eps_estimate=1.0, eps_reported=1.2, surprise_pct=20.0)
        for i in range(1, 5)
    ]
    actions = [
        AnalystAction(
            date=(date.today() - timedelta(days=15 * (i + 1))).isoformat(),
            firm=f"F{i}", to_grade="Buy", from_grade="Hold", action="up",
        )
        for i in range(3)
    ]
    f = Fundamentals(
        ticker="TEST", micro=micro, earnings=earnings, analyst_actions=actions,
        price_target=AnalystPriceTarget(mean=closes.iloc[-1] * 1.30),
    )
    cs = _build_score(
        _stock(sector="Technology"), f, closes, news_count=25,
        news_polarity=70.0,
    )
    assert 70.0 <= cs.composite <= 100.0
    assert all(v is not None for v in cs.sub_scores.values())
    for pillar in ("profitability", "sustainability", "growth", "value", "momentum", "sentiment"):
        assert pillar in cs.breakdown
    assert "weights_used" in cs.breakdown


def test_build_score_missing_pillar_renormalises():
    closes = _strong_uptrend_closes()
    cs = _build_score(_stock(), None, closes, news_count=None)
    # Only momentum should be non-None.
    assert cs.sub_scores["momentum"] is not None
    assert cs.sub_scores["profitability"] is None
    assert cs.sub_scores["sustainability"] is None
    assert cs.sub_scores["growth"] is None
    assert cs.sub_scores["value"] is None
    assert cs.sub_scores["sentiment"] is None
    assert cs.composite == pytest.approx(cs.sub_scores["momentum"], abs=0.1)


def test_build_score_breakdown_is_json_serialisable():
    closes = _strong_uptrend_closes()
    cs = _build_score(_stock(), None, closes, news_count=5)
    s = json.dumps(cs.breakdown, allow_nan=False)
    assert "NaN" not in s and "Infinity" not in s


# ---------------------------------------------------------------------------
# recompute_all integration
# ---------------------------------------------------------------------------

def _seed_ohlcv(db: Session, stock_id: int, n_bars: int = 250, drift: float = 0.1) -> None:
    today = date(2026, 5, 1)
    for i in range(n_bars):
        d = today - timedelta(days=n_bars - 1 - i)
        close = 100.0 + drift * i
        db.add(OhlcvDaily(
            stock_id=stock_id, date=d,
            open=close - 0.5, high=close + 0.5, low=close - 1.0,
            close=close, volume=1_000_000,
        ))


def _build_fundamentals_for(ticker: str, *, good: bool) -> Fundamentals:
    if good:
        micro = MicroData(
            return_on_equity=0.30, profit_margins=0.25, free_cashflow=1e10,
            debt_to_equity=30.0, current_ratio=2.5,
            revenue_growth=0.25, earnings_growth=0.30,
            trailing_pe=20.0, peg_ratio=0.9, dividend_yield=0.025,
            beta=0.9, fifty_two_week_change=0.50,
        )
        earnings = [
            EarningsPoint(date=f"2025-0{i}-01", eps_estimate=1.0, eps_reported=1.2, surprise_pct=20.0)
            for i in range(1, 5)
        ]
        return Fundamentals(
            ticker=ticker, micro=micro, earnings=earnings,
            price_target=AnalystPriceTarget(mean=200.0),
        )
    micro = MicroData(
        return_on_equity=-0.05, profit_margins=-0.10, free_cashflow=-1e9,
        debt_to_equity=300.0, current_ratio=0.5,
        revenue_growth=-0.20, earnings_growth=-0.30,
        trailing_pe=80.0, peg_ratio=4.0, dividend_yield=0.0,
        beta=1.5, fifty_two_week_change=-0.30,
    )
    return Fundamentals(ticker=ticker, micro=micro)


def test_recompute_all_populates_table(db: Session, monkeypatch):
    fund_map: dict[str, Fundamentals] = {}
    monkeypatch.setattr(
        stock_fundamentals_service, "get_fundamentals",
        lambda ticker, force_refresh=False: fund_map.get(ticker, Fundamentals(ticker=ticker)),
    )
    monkeypatch.setattr(stock_news_service, "get_news", lambda ticker, limit=5: [])

    sectors = ["Technology", "Utilities", "Healthcare", "Energy", "Industrials"]
    for i in range(5):
        s = Stock(
            ticker=f"T{i}", exchange="NMS", name=f"Stock {i}",
            sector=sectors[i], market_cap=int(1e10) + i * int(1e9),
        )
        db.add(s)
    db.commit()
    stocks = db.query(Stock).order_by(Stock.id).all()
    for i, s in enumerate(stocks):
        _seed_ohlcv(db, s.id, n_bars=250, drift=0.2 if i < 3 else -0.2)
        fund_map[s.ticker] = _build_fundamentals_for(s.ticker, good=i < 3)
    db.commit()

    ok, failed = score_service.recompute_all(db)
    assert ok == 5
    assert failed == 0
    rows = db.query(StockScore).all()
    assert len(rows) == 5
    by_ticker = {db.get(Stock, r.stock_id).ticker: r for r in rows}
    good_avg = sum(by_ticker[f"T{i}"].composite for i in range(3)) / 3
    bad_avg = sum(by_ticker[f"T{i}"].composite for i in range(3, 5)) / 2
    assert good_avg > bad_avg
    for r in rows:
        assert isinstance(json.loads(r.breakdown), dict)


def test_recompute_all_idempotent(db: Session, monkeypatch):
    monkeypatch.setattr(
        stock_fundamentals_service, "get_fundamentals",
        lambda ticker, force_refresh=False: Fundamentals(ticker=ticker),
    )
    monkeypatch.setattr(stock_news_service, "get_news", lambda ticker, limit=5: [])

    s = Stock(ticker="X", exchange="NMS", name="X", sector="Technology", market_cap=int(1e10))
    db.add(s)
    db.commit()
    _seed_ohlcv(db, s.id, n_bars=250)
    db.commit()

    score_service.recompute_all(db)
    score_service.recompute_all(db)
    assert db.query(StockScore).count() == 1


def test_recompute_all_updates_existing_score_in_place(db: Session, monkeypatch):
    fund: dict[str, Fundamentals] = {"X": Fundamentals(ticker="X")}
    monkeypatch.setattr(
        stock_fundamentals_service, "get_fundamentals",
        lambda ticker, force_refresh=False: fund.get(ticker, Fundamentals(ticker=ticker)),
    )
    monkeypatch.setattr(stock_news_service, "get_news", lambda ticker, limit=5: [])

    s = Stock(ticker="X", exchange="NMS", name="X", sector="Technology", market_cap=int(1e10))
    db.add(s)
    db.commit()
    _seed_ohlcv(db, s.id, n_bars=250)
    db.commit()

    score_service.recompute_all(db)
    first = db.query(StockScore).filter_by(stock_id=s.id).one()
    first_composite = first.composite

    fund["X"] = Fundamentals(
        ticker="X",
        micro=MicroData(
            return_on_equity=0.30,
            profit_margins=0.25,
            free_cashflow=int(50e9),
            debt_to_equity=40.0,
            current_ratio=2.5,
        ),
    )

    score_service.recompute_all(db)
    assert db.query(StockScore).count() == 1
    second = db.query(StockScore).filter_by(stock_id=s.id).one()
    assert second.composite != first_composite


# ---------------------------------------------------------------------------
# Regression: sector_stats pre-pass MUST emit heartbeats while it runs.
# Before this fix, two consecutive recomputes failed at +0.7s heartbeat
# because the slow yfinance retries on delisted tickers caused 30s+ of
# silence before _build_sector_stats returned. The stop endpoint's
# stale detector (>120s) then force-closed the row.
# ---------------------------------------------------------------------------

def test_recompute_all_passes_heartbeat_through_sector_stats_prepass(
    db: Session, monkeypatch
):
    """recompute_all MUST invoke on_progress at least once during the
    sector_stats pre-pass (i.e. BEFORE the per-stock scoring loop starts),
    so the runner's heartbeat keeps refreshing while _build_sector_stats
    is slow on yfinance retries."""
    monkeypatch.setattr(
        stock_fundamentals_service, "get_fundamentals",
        lambda ticker, force_refresh=False: Fundamentals(ticker=ticker),
    )
    monkeypatch.setattr(stock_news_service, "get_news", lambda ticker, limit=5: [])

    # Seed > heartbeat_every (default 20) stocks so the pre-pass triggers
    # the in-loop heartbeat at least once.
    for i in range(25):
        db.add(Stock(
            ticker=f"H{i}", exchange="NMS", name=f"Heartbeat test {i}",
            sector="Technology", market_cap=int(1e10),
        ))
    db.commit()

    heartbeats: list[tuple[int, int]] = []

    def fake_on_progress(done: int, total: int) -> None:
        heartbeats.append((done, total))

    ok, failed = score_service.recompute_all(db, on_progress=fake_on_progress)
    assert ok == 25
    assert failed == 0

    # MUST have multiple heartbeats. The first one is from the seed at the
    # very start of recompute_all (done=0). The pre-pass adds at least one
    # more (every 20 stocks → 1 for 25 stocks at the start + 1 final).
    # The scoring loop adds more (every 10 stocks → 2-3 more heartbeats).
    assert len(heartbeats) >= 3, (
        f"Expected >=3 heartbeats (1 seed + >=1 pre-pass + >=1 scoring), "
        f"got {len(heartbeats)}: {heartbeats}"
    )
    # First heartbeat MUST be done=0 (seed before pre-pass), regression
    # guard against the runner accidentally flipping phase too early.
    assert heartbeats[0] == (0, 25)


def test_recompute_all_cancellable_during_sector_stats(db: Session, monkeypatch):
    """The pre-pass MUST honour cancel_check too, not just the scoring
    loop. Otherwise a user clicking Stop during the slow yfinance retries
    waits for the pre-pass to complete (potentially minutes) before the
    runner reacts."""
    monkeypatch.setattr(
        stock_fundamentals_service, "get_fundamentals",
        lambda ticker, force_refresh=False: Fundamentals(ticker=ticker),
    )
    monkeypatch.setattr(stock_news_service, "get_news", lambda ticker, limit=5: [])

    for i in range(40):
        db.add(Stock(
            ticker=f"C{i}", exchange="NMS", name=f"Cancel test {i}",
            sector="Technology", market_cap=int(1e10),
        ))
    db.commit()

    # Cancel request fires on the very first check (i=0).
    cancel_calls = {"n": 0}

    def always_cancelled() -> bool:
        cancel_calls["n"] += 1
        return True

    with pytest.raises(score_service.RecomputeCancelled):
        score_service.recompute_all(db, cancel_check=always_cancelled)

    # The cancel MUST have been polled at least once (from inside the
    # pre-pass). Without the pre-pass cancel hook this assertion would fail
    # because the cancel_check was previously only consulted in the scoring
    # loop, never reached when the pre-pass raised.
    assert cancel_calls["n"] >= 1


# ---------------------------------------------------------------------------
# Regression: cancel must react WITHIN ONE STOCK of the request, not after
# a multi-stock window.
# ---------------------------------------------------------------------------

def test_cancel_check_polled_every_stock_in_prepass(db: Session, monkeypatch):
    """User-reported issue: clicking Stop during the sector_stats pre-pass
    took ~80s to react because cancel_check was tied to heartbeat_every=20
    and individual yfinance fetches could stall the loop for seconds. The
    fix decouples the two — cancel is now polled every stock (cheap set
    lookup), heartbeat stays at every 20 (DB commit).

    Guard: when cancel becomes true on the 3rd iteration, the runner must
    raise RecomputeCancelled before reaching iteration 4 — NOT wait until
    the next heartbeat boundary (which would be iteration 20)."""
    monkeypatch.setattr(
        stock_fundamentals_service, "get_fundamentals",
        lambda ticker, force_refresh=False: Fundamentals(ticker=ticker),
    )
    monkeypatch.setattr(stock_news_service, "get_news", lambda ticker, limit=5: [])

    for i in range(50):
        db.add(Stock(
            ticker=f"PC{i}", exchange="NMS", name=f"Pre-cancel test {i}",
            sector="Technology", market_cap=int(1e10),
        ))
    db.commit()

    calls_before_cancel = {"n": 0}

    def cancel_on_third() -> bool:
        calls_before_cancel["n"] += 1
        # Return True on the 3rd call (=== 3rd stock in the loop)
        return calls_before_cancel["n"] >= 3

    with pytest.raises(score_service.RecomputeCancelled):
        score_service.recompute_all(db, cancel_check=cancel_on_third)

    # MUST react on the 3rd call. Before the fix, with cancel checks only
    # at i % 20 == 0, the runner would have looped through all 20 stocks
    # before noticing — calls_before_cancel would be way higher than 3.
    # Now: i=0 (first check) ok, i=1 (second) ok, i=2 (third) → True → raise.
    assert calls_before_cancel["n"] == 3, (
        f"cancel_check should fire on every stock; only {calls_before_cancel['n']} "
        f"calls before cancel was honoured"
    )


def test_cancel_check_polled_every_stock_in_scoring_loop(db: Session, monkeypatch):
    """Same guarantee in the scoring loop. Even if the pre-pass passes
    quickly, the long phase is scoring (~940 stocks × DB I/O). User Stop
    during scoring must also react within one stock."""
    monkeypatch.setattr(
        stock_fundamentals_service, "get_fundamentals",
        lambda ticker, force_refresh=False: Fundamentals(ticker=ticker),
    )
    monkeypatch.setattr(stock_news_service, "get_news", lambda ticker, limit=5: [])

    for i in range(30):
        db.add(Stock(
            ticker=f"SC{i}", exchange="NMS", name=f"Scoring cancel test {i}",
            sector="Technology", market_cap=int(1e10),
        ))
    db.commit()

    # The pre-pass calls cancel_check 30 times (once per stock). Then the
    # scoring loop calls it 30 more times. We want to verify the cancel
    # fires within the scoring loop too, so we delay the True signal until
    # AFTER the pre-pass completes (call #31, first iteration of scoring).
    calls = {"n": 0}
    PREPASS_LEN = 30

    def cancel_first_scoring_iter() -> bool:
        calls["n"] += 1
        return calls["n"] > PREPASS_LEN  # Fire on iteration 31 (first scoring)

    with pytest.raises(score_service.RecomputeCancelled):
        score_service.recompute_all(db, cancel_check=cancel_first_scoring_iter)

    # Scoring loop reacts within the same iteration the cancel was requested.
    # Allow ±1 for the boundary between pre-pass last call and scoring first call.
    assert PREPASS_LEN < calls["n"] <= PREPASS_LEN + 2, (
        f"Expected cancel to react within 1-2 iterations of the scoring loop; "
        f"reacted after {calls['n']} total calls (pre-pass={PREPASS_LEN})"
    )
