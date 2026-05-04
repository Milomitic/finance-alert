"""Tests for app.services.score_service.

Three layers:
1. Sub-score boundary tests (pure functions on stub Stock + MicroData inputs).
2. Risk classification edge cases (defensive sector + low beta + mega cap →
   conservative; high beta + small cap → aggressive).
3. recompute_all integration: seed N stocks + OHLCV + stub fundamentals, run
   the batch, assert StockScore rows exist with sensible values.
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
    micro = MicroData(
        return_on_equity=0.30, profit_margins=0.25, free_cashflow=1e10,
        debt_to_equity=30.0, current_ratio=2.5,
    )
    pts, mx, br = _quality(_stock(), micro)
    assert mx == 100.0
    assert pts == pytest.approx(100.0, abs=0.01)
    # Components should each be at max:
    assert br["roe"]["points"] == 30.0
    assert br["fcf"]["points"] == 20.0
    assert br["current_ratio"]["points"] == 10.0


def test_quality_all_bad_zero_score():
    micro = MicroData(
        return_on_equity=-0.05, profit_margins=-0.10, free_cashflow=-1e9,
        debt_to_equity=300.0, current_ratio=0.5,
    )
    pts, mx, br = _quality(_stock(), micro)
    assert mx == 100.0
    assert pts == pytest.approx(0.0, abs=0.01)


def test_quality_half_points_at_midpoint():
    micro = MicroData(
        return_on_equity=0.10, profit_margins=0.10, free_cashflow=1.0,
        debt_to_equity=100.0, current_ratio=1.0,
    )
    pts, mx, br = _quality(_stock(), micro)
    # ROE half (15) + PM half (12.5) + FCF full (20) + DE half (7.5) + CR half (5) = 60
    assert pts == pytest.approx(60.0, abs=0.5)


def test_quality_missing_micro_returns_no_input():
    pts, mx, br = _quality(_stock(), None)
    assert mx == 0.0
    assert br == {}


# ---------------------------------------------------------------------------
# Growth
# ---------------------------------------------------------------------------

def test_growth_all_good():
    micro = MicroData(revenue_growth=0.25, earnings_growth=0.30)
    earnings = [
        EarningsPoint(date="2025-01-01", eps_estimate=1.0, eps_reported=1.2, surprise_pct=20.0),
        EarningsPoint(date="2025-04-01", eps_estimate=1.1, eps_reported=1.3, surprise_pct=18.0),
        EarningsPoint(date="2025-07-01", eps_estimate=1.2, eps_reported=1.4, surprise_pct=16.0),
        EarningsPoint(date="2025-10-01", eps_estimate=1.3, eps_reported=1.5, surprise_pct=15.0),
    ]
    f = Fundamentals(ticker="TEST", micro=micro, earnings=earnings)
    pts, mx, br = _growth(_stock(), f)
    assert pts == pytest.approx(100.0, abs=0.01)
    assert br["earnings_beat"]["raw"] == 4


def test_growth_zero_when_all_negative():
    micro = MicroData(revenue_growth=-0.20, earnings_growth=-0.20)
    earnings = [
        EarningsPoint(date=f"2025-0{i}-01", eps_estimate=1.0, eps_reported=0.5, surprise_pct=-50.0)
        for i in range(1, 5)
    ]
    f = Fundamentals(ticker="TEST", micro=micro, earnings=earnings)
    pts, _, br = _growth(_stock(), f)
    assert pts == pytest.approx(0.0, abs=0.5)
    assert br["earnings_beat"]["raw"] == 0


def test_growth_no_earnings_history_means_no_input_for_that_component():
    micro = MicroData(revenue_growth=0.20, earnings_growth=0.20)
    f = Fundamentals(ticker="TEST", micro=micro, earnings=[])
    pts, mx, br = _growth(_stock(), f)
    # 35 + 35 + 0 (no beats history) = 70
    assert pts == pytest.approx(70.0, abs=0.01)
    assert br["earnings_beat"]["raw"] is None


# ---------------------------------------------------------------------------
# Value
# ---------------------------------------------------------------------------

def test_value_full_at_or_below_sector_median_pe():
    # Tech median is 28; a P/E of 25 should give full P/E points.
    micro = MicroData(trailing_pe=25.0, peg_ratio=0.9, dividend_yield=0.04)
    pts, mx, br = _value(_stock(sector="Technology"), micro, last_close=200.0)
    assert br["pe"]["points"] == 40.0
    assert br["peg"]["points"] == 30.0   # PEG ≤ 1 → full
    # 4% dividend > 3% → full 30
    assert br["dividend_yield"]["points"] == 30.0
    assert pts == pytest.approx(100.0, abs=0.01)


def test_value_pe_double_median_zero_points():
    micro = MicroData(trailing_pe=56.0, peg_ratio=3.5, dividend_yield=0.0)
    pts, mx, br = _value(_stock(sector="Technology"), micro, last_close=200.0)
    assert br["pe"]["points"] == pytest.approx(0.0, abs=0.01)
    assert br["peg"]["points"] == pytest.approx(0.0, abs=0.01)
    assert br["dividend_yield"]["points"] == pytest.approx(0.0, abs=0.01)


def test_value_unknown_sector_uses_universe_median():
    micro = MicroData(trailing_pe=22.0, peg_ratio=2.0, dividend_yield=0.015)
    _, _, br = _value(_stock(sector=None), micro, last_close=100.0)
    assert br["pe"]["sector_median"] == 22.0
    # P/E exactly at median → full 40
    assert br["pe"]["points"] == 40.0


# ---------------------------------------------------------------------------
# Momentum
# ---------------------------------------------------------------------------

def _strong_uptrend_closes(n: int = 260, start: float = 100.0, drift: float = 0.5) -> pd.Series:
    """Linear ramp upward — strong 52w + 30d momentum, typical RSI in overbought."""
    return pd.Series([start + drift * i for i in range(n)])


def _strong_downtrend_closes(n: int = 260, start: float = 200.0, drift: float = -0.5) -> pd.Series:
    return pd.Series([max(1.0, start + drift * i) for i in range(n)])


def test_momentum_strong_uptrend_high_score():
    """Linear-ramp uptrend with drift=0.5 → 52w full + RSI overbought + MACD
    bullish. 30-day momentum on a linear trend is small in percent terms
    (~5%), so it sits on the half-to-full ramp rather than at the cap. The
    point of the assert is "high score, all components signalling up", not
    a specific number — 70+ is enough to assert that."""
    closes = _strong_uptrend_closes()
    micro = MicroData(fifty_two_week_change=0.60)
    pts, mx, br = _momentum(_stock(), micro, closes)
    assert pts >= 70.0
    assert br["change_52w"]["points"] == 30.0     # 52w full
    assert br["rsi"]["points"] == 4.0             # overbought (linear ramp → RSI ~ 100)
    assert br["macd"]["state"] == "bullish"
    assert br["macd"]["points"] == 20.0


def test_momentum_strong_downtrend_low_score():
    closes = _strong_downtrend_closes()
    micro = MicroData(fifty_two_week_change=-0.40)
    pts, mx, br = _momentum(_stock(), micro, closes)
    # 0 (52w zero) + 16 (RSI oversold → bounce) + 0 (MACD bearish) + 0 (mom30 zero) = 16
    assert pts == pytest.approx(16.0, abs=1.0)
    assert br["macd"]["state"] == "bearish_or_flat"


def test_momentum_no_inputs_returns_zero_max():
    pts, mx, br = _momentum(_stock(), None, None)
    assert mx == 0.0
    assert br == {}


# ---------------------------------------------------------------------------
# Sentiment
# ---------------------------------------------------------------------------

def test_sentiment_full_score():
    today = date.today()
    actions = [
        AnalystAction(
            date=(today - timedelta(days=10)).isoformat(),
            firm="GS", to_grade="Buy", from_grade="Hold", action="up",
        ),
        AnalystAction(
            date=(today - timedelta(days=20)).isoformat(),
            firm="MS", to_grade="Buy", from_grade="Hold", action="up",
        ),
        AnalystAction(
            date=(today - timedelta(days=30)).isoformat(),
            firm="JPM", to_grade="Buy", from_grade="Hold", action="up",
        ),
    ]
    f = Fundamentals(
        ticker="TEST",
        price_target=AnalystPriceTarget(mean=240.0),
        analyst_actions=actions,
    )
    pts, mx, br = _sentiment(_stock(), f, news_count=25, last_close=200.0)
    # upside = 20% → full 50; net upgrades = +3 → full 30; news 25 → full 20.
    assert pts == pytest.approx(100.0, abs=0.01)


def test_sentiment_zero_score():
    today = date.today()
    actions = [
        AnalystAction(
            date=(today - timedelta(days=10)).isoformat(),
            firm="GS", to_grade="Hold", from_grade="Buy", action="down",
        ),
        AnalystAction(
            date=(today - timedelta(days=20)).isoformat(),
            firm="MS", to_grade="Sell", from_grade="Hold", action="down",
        ),
        AnalystAction(
            date=(today - timedelta(days=30)).isoformat(),
            firm="JPM", to_grade="Sell", from_grade="Hold", action="down",
        ),
    ]
    f = Fundamentals(
        ticker="TEST",
        price_target=AnalystPriceTarget(mean=180.0),  # 200 → 180 = -10% downside
        analyst_actions=actions,
    )
    pts, _, _ = _sentiment(_stock(), f, news_count=0, last_close=200.0)
    assert pts == pytest.approx(0.0, abs=0.5)


def test_sentiment_old_actions_ignored():
    """Actions older than 90 days don't count — should yield None for the
    net-upgrades component, leaving it as a missing-data entry (0 points)."""
    today = date.today()
    actions = [
        AnalystAction(
            date=(today - timedelta(days=120)).isoformat(),
            firm="GS", to_grade="Buy", from_grade="Hold", action="up",
        ),
    ]
    f = Fundamentals(ticker="TEST", analyst_actions=actions)
    _, _, br = _sentiment(_stock(), f, news_count=10, last_close=200.0)
    assert br["net_upgrades_90d"]["raw"] is None


# ---------------------------------------------------------------------------
# Renormalization
# ---------------------------------------------------------------------------

def test_renormalize_skips_missing_pillars():
    sub = {
        "quality": 80.0, "growth": 60.0, "value": 50.0,
        "momentum": 70.0, "sentiment": None,
    }
    w = _renormalize_weights(sub)
    # Missing sentiment (15%) is dropped; remaining 85% renormalises to 1.0.
    assert w["sentiment"] == 0.0
    assert sum(w.values()) == pytest.approx(1.0, abs=1e-9)
    # Quality's effective weight: 0.25 / 0.85 ≈ 0.294
    assert w["quality"] == pytest.approx(0.25 / 0.85, abs=1e-9)


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
    # Utility + low beta + low vol + > $200B cap → all four nudge to conservative.
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


# ---------------------------------------------------------------------------
# Pure compute path: _build_score
# ---------------------------------------------------------------------------

def test_build_score_all_pillars_present():
    closes = _strong_uptrend_closes()
    micro = MicroData(
        return_on_equity=0.25, profit_margins=0.20, free_cashflow=1e10,
        debt_to_equity=40.0, current_ratio=2.0,
        revenue_growth=0.20, earnings_growth=0.20,
        trailing_pe=20.0, peg_ratio=1.0, dividend_yield=0.03,
        beta=1.0, fifty_two_week_change=0.50,
    )
    earnings = [
        EarningsPoint(date=f"2025-0{i}-01", eps_estimate=1.0, eps_reported=1.2, surprise_pct=20.0)
        for i in range(1, 5)
    ]
    actions = [
        AnalystAction(
            date=(date.today() - timedelta(days=15)).isoformat(),
            firm=f"F{i}", to_grade="Buy", from_grade="Hold", action="up",
        )
        for i in range(3)
    ]
    f = Fundamentals(
        ticker="TEST", micro=micro, earnings=earnings, analyst_actions=actions,
        price_target=AnalystPriceTarget(mean=closes.iloc[-1] * 1.30),  # 30% upside
    )
    cs = _build_score(_stock(sector="Technology"), f, closes, news_count=25)
    assert 70.0 <= cs.composite <= 100.0
    # All five sub-scores present (no None).
    assert all(v is not None for v in cs.sub_scores.values())
    # Breakdown has all five pillar dicts + weights.
    for pillar in ("quality", "growth", "value", "momentum", "sentiment"):
        assert pillar in cs.breakdown
    assert "weights_used" in cs.breakdown


def test_build_score_missing_pillar_renormalises():
    """Stock with no fundamentals at all → only momentum has data."""
    closes = _strong_uptrend_closes()
    cs = _build_score(_stock(), None, closes, news_count=None)
    # Only momentum should be non-None.
    assert cs.sub_scores["momentum"] is not None
    assert cs.sub_scores["quality"] is None
    assert cs.sub_scores["growth"] is None
    assert cs.sub_scores["value"] is None
    # Sentiment: with fundamentals=None, _sentiment returns no input.
    assert cs.sub_scores["sentiment"] is None
    # Composite should equal momentum (its weight renormalises to 1.0).
    assert cs.composite == pytest.approx(cs.sub_scores["momentum"], abs=0.1)


def test_build_score_breakdown_is_json_serialisable():
    """breakdown must round-trip through json.dumps without NaN/Infinity."""
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
    """Seed 5 stocks with varying fundamentals, run recompute_all, assert rows."""
    # Stub upstream services so the test is hermetic.
    fund_map: dict[str, Fundamentals] = {}
    monkeypatch.setattr(
        stock_fundamentals_service, "get_fundamentals",
        lambda ticker, force_refresh=False: fund_map.get(ticker, Fundamentals(ticker=ticker)),
    )
    monkeypatch.setattr(stock_news_service, "get_news", lambda ticker, limit=5: [])

    # 5 stocks: 3 "good", 2 "bad".
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

    n = score_service.recompute_all(db)
    assert n == 5
    rows = db.query(StockScore).all()
    assert len(rows) == 5
    by_ticker = {db.get(Stock, r.stock_id).ticker: r for r in rows}
    # Good stocks (T0..T2) should score higher than bad (T3..T4).
    good_avg = sum(by_ticker[f"T{i}"].composite for i in range(3)) / 3
    bad_avg = sum(by_ticker[f"T{i}"].composite for i in range(3, 5)) / 2
    assert good_avg > bad_avg
    # All breakdowns are valid JSON.
    for r in rows:
        assert isinstance(json.loads(r.breakdown), dict)


def test_recompute_all_idempotent(db: Session, monkeypatch):
    """Running twice doesn't duplicate rows — second run UPSERTs in place."""
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
