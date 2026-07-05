"""Tests for the score-IC backtest script (B4-8, roadmap gate #9).

All synthetic — no network, no live DB. The three properties the task
demands are locked here:

  1. NO-LOOK-AHEAD (the core test): a fact FILED after the as-of date must
     not influence that date's pillar inputs — checked both at the
     `pillar_inputs_as_of` level and end-to-end through the observation
     frame (`_build_observations`).
  2. IC MATH SANITY: perfectly predictive synthetic scores → per-date
     Spearman IC ~ +1 (and -1 when anti-predictive); random scores → ~0;
     narrow cross-sections are skipped, not correlated.
  3. FORWARD-RETURN ALIGNMENT: entry bar = LAST bar with date <= as_of
     (weekend/holiday as-of snaps BACK, never forward), and the h-bar
     forward return is close[i+h]/close[i]-1 with no off-by-one.

Plus: the fetch_cache substrate seam (`_load_fact_histories` reads
kind='sec_facts_history' rows, TTL-free), the quarterly grid, the
>=2-pillars composite gate, and artifact write vs --dry-run.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from sqlalchemy.orm import Session

from app.models import FetchCache, OhlcvDaily, Stock
from app.scripts import score_ic_backtest as sib
from app.services.sec_fundamentals_history import FactPoint

# --------------------------------------------------------------------------- #
# Fixtures / helpers                                                          #
# --------------------------------------------------------------------------- #

_BAR0 = date(2020, 1, 1)


def _fp(end: str, val: float, filed: str, start: str | None = None) -> FactPoint:
    dur = None
    if start:
        dur = (date.fromisoformat(end) - date.fromisoformat(start)).days
    return FactPoint(end=end, val=val, filed=filed, form="10-K",
                     start=start, duration_days=dur)


def _annual(year: int, val: float, filed: str) -> FactPoint:
    """One annual (~365d duration) flow fact for fiscal `year`."""
    return _fp(f"{year}-12-31", val, filed, start=f"{year}-01-01")


def _instant(end: str, val: float, filed: str) -> FactPoint:
    """One balance-sheet (instant, no duration) fact."""
    return _fp(end, val, filed)


def _mk_bars(
    ticker: str, *, start: date = _BAR0, n: int = 60,
    closes: list[float] | None = None, step_days: int = 1, stock_id: int = 1,
) -> sib._StockBars:
    """In-memory _StockBars (no DB) for the pure observation-frame tests."""
    dates = [(start + timedelta(days=i * step_days)).isoformat() for i in range(n)]
    c = np.asarray(closes if closes is not None else [100.0] * n, dtype="float64")
    assert len(c) == n
    return sib._StockBars(stock_id=stock_id, ticker=ticker, dates=dates, closes=c)


def _seed_stock(db: Session, ticker: str, closes: list[float],
                start: date = _BAR0) -> Stock:
    stock = Stock(ticker=ticker, exchange="TST", name=ticker)
    db.add(stock)
    db.flush()
    for i, c in enumerate(closes):
        db.add(OhlcvDaily(
            stock_id=stock.id, date=start + timedelta(days=i),
            open=c, high=c + 1, low=max(c - 1, 0.01), close=c, volume=1_000,
        ))
    db.commit()
    return stock


def _synth_hist(k: int) -> dict[str, list[FactPoint]]:
    """Synthetic PIT history for stock `k` (1..12): EVERY reconstructed
    component strictly increasing in k (better fundamentals = higher k),
    so the pillar and composite ranks are exactly the k-order.

      gross_margin (100+20k)/1000, roa 10k/2000, roe 10k/500,
      net_margin 10k/1000, op_margin (50+15k)/1000        → increasing
      debt/equity (1000-50k)/500 decreasing → LIB score increasing
      fcf = 25k-5 > 0; fcf_to_ni = 2.5 - 0.5/k            → increasing
      rev_yoy = 0.02k; ni_yoy = 0.03k                     → increasing
      (5y CAGRs absent → weight renormalised away)

    FY2019 facts filed 2020-01-15 (visible at the 2020-04-01 as-of);
    FY2018 filed 2019-02-01 (feeds the knowledge-YoY prior TTM).
    """
    f19, f18 = "2020-01-15", "2019-02-01"
    return {
        "revenue": [_annual(2018, 1000.0 / (1 + 0.02 * k), f18),
                    _annual(2019, 1000.0, f19)],
        "net_income": [_annual(2018, 10.0 * k / (1 + 0.03 * k), f18),
                       _annual(2019, 10.0 * k, f19)],
        "gross_profit": [_annual(2019, 100.0 + 20.0 * k, f19)],
        "operating_income": [_annual(2019, 50.0 + 15.0 * k, f19)],
        "operating_cash_flow": [_annual(2019, 25.0 * k, f19)],
        "capex": [_annual(2019, 5.0, f19)],
        "equity": [_instant("2019-12-31", 500.0, f19)],
        "assets": [_instant("2019-12-31", 2000.0, f19)],
        "long_term_debt": [_instant("2019-12-31", 1000.0 - 50.0 * k, f19)],
    }


# --------------------------------------------------------------------------- #
# Quarterly grid                                                              #
# --------------------------------------------------------------------------- #

def test_quarterly_grid_snaps_forward_and_steps():
    # Mid-quarter start snaps FORWARD (never grants an earlier as-of).
    g = sib._quarterly_grid(date(2010, 2, 15), date(2011, 1, 1), every=1)
    assert g == [date(2010, 4, 1), date(2010, 7, 1),
                 date(2010, 10, 1), date(2011, 1, 1)]
    # Exact quarter start is kept; every=2 steps 6 months.
    g2 = sib._quarterly_grid(date(2010, 1, 1), date(2011, 1, 1), every=2)
    assert g2 == [date(2010, 1, 1), date(2010, 7, 1), date(2011, 1, 1)]
    # Empty when the window contains no quarter start.
    assert sib._quarterly_grid(date(2010, 1, 2), date(2010, 3, 31)) == []


# --------------------------------------------------------------------------- #
# 1. NO-LOOK-AHEAD — the core property                                        #
# --------------------------------------------------------------------------- #

def test_fact_filed_after_as_of_is_invisible():
    """A FY2019 net-income 5x jump filed 2020-02-01 must NOT touch the
    2019 as-of inputs; it appears only once filed."""
    hist = {
        "revenue": [_annual(2018, 1000.0, "2019-02-01"),
                    _annual(2019, 1000.0, "2020-02-01")],
        "net_income": [_annual(2018, 100.0, "2019-02-01"),
                       _annual(2019, 500.0, "2020-02-01")],
    }
    before = sib.pillar_inputs_as_of(hist, date(2019, 7, 1))
    after = sib.pillar_inputs_as_of(hist, date(2020, 7, 1))
    assert before["net_margin"] == pytest.approx(0.10)   # FY2018 only
    assert after["net_margin"] == pytest.approx(0.50)    # FY2019 now filed
    # Before ANY filing: every input is None (no silent zero-filling).
    nothing = sib.pillar_inputs_as_of(hist, date(2018, 6, 30))
    assert all(v is None for v in nothing.values())


def test_no_look_ahead_flows_through_observation_frame():
    """End-to-end: the observation rows for the SAME stock at two grid
    dates straddling a filing carry the PIT-correct values — and the
    composite is gated on >= 2 reconstructed pillars."""
    n = 430  # 2019-06-01 .. 2020-08-03, daily bars
    bars = _mk_bars("AAA", start=date(2019, 6, 1), n=n)
    hist = {
        "revenue": [_annual(2018, 1000.0, "2019-02-01"),
                    _annual(2019, 1000.0, "2020-02-01")],
        "net_income": [_annual(2018, 100.0, "2019-02-01"),
                       _annual(2019, 500.0, "2020-02-01")],
    }
    grid = [date(2019, 7, 1), date(2020, 7, 1)]
    obs = sib._build_observations([bars], {"AAA": hist}, grid, (5,))
    assert len(obs) == 2
    row1 = obs[obs["as_of"] == "2019-07-01"].iloc[0]
    row2 = obs[obs["as_of"] == "2020-07-01"].iloc[0]
    assert row1["net_margin"] == pytest.approx(0.10)
    assert row2["net_margin"] == pytest.approx(0.50)
    # 2019 as-of: only profitability is reconstructable (no prior-year TTM
    # for growth, no balance/cash-flow facts) → composite withheld.
    assert pd.isna(row1["composite"])
    # 2020 as-of: profitability + growth (ni_yoy=4.0, rev_yoy=0.0) → present.
    assert row2["ni_yoy"] == pytest.approx(4.0)
    assert not pd.isna(row2["composite"])


# --------------------------------------------------------------------------- #
# 2. IC math sanity                                                           #
# --------------------------------------------------------------------------- #

def _obs_frame(dates: list[str], score_fn, fwd_fn, width: int) -> pd.DataFrame:
    frames = []
    for d in dates:
        idx = np.arange(width, dtype="float64")
        frames.append(pd.DataFrame({
            "as_of": d, "score": score_fn(idx), "fwd": fwd_fn(idx),
        }))
    return pd.concat(frames, ignore_index=True)


def test_rank_ic_perfectly_predictive_is_one():
    obs = _obs_frame(["2020-01-01", "2020-04-01", "2020-07-01"],
                     lambda x: x, lambda x: x * 0.001, width=50)
    pairs = sib._rank_ic_by_date(obs, "score", "fwd")
    assert len(pairs) == 3
    assert all(ic == pytest.approx(1.0) for _, ic in pairs)
    stats = sib._ic_stats(pairs)
    assert stats["ic_mean"] == pytest.approx(1.0)
    assert stats["n_dates"] == 3
    # Anti-predictive → -1 (sign preserved, not folded).
    obs["fwd_neg"] = -obs["fwd"]
    pairs_neg = sib._rank_ic_by_date(obs, "score", "fwd_neg")
    assert all(ic == pytest.approx(-1.0) for _, ic in pairs_neg)


def test_rank_ic_random_is_near_zero():
    rng = np.random.default_rng(42)
    frames = []
    for q in range(8):
        frames.append(pd.DataFrame({
            "as_of": f"2020-{q + 1:02d}-01",
            "score": rng.normal(size=300),
            "fwd": rng.normal(size=300),
        }))
    obs = pd.concat(frames, ignore_index=True)
    stats = sib._ic_stats(sib._rank_ic_by_date(obs, "score", "fwd"))
    assert stats["n_dates"] == 8
    assert abs(stats["ic_mean"]) < 0.15
    assert stats["ic_std"] is not None and stats["t_stat"] is not None


def test_rank_ic_skips_narrow_cross_sections():
    """A 5-stock date is noise, not a cross-section — skipped entirely."""
    obs = _obs_frame(["2020-01-01"], lambda x: x, lambda x: x, width=5)
    assert sib._rank_ic_by_date(obs, "score", "fwd") == []
    assert sib._ic_stats([])["ic_mean"] is None


def test_decile_spread_positive_for_predictive_score():
    obs = _obs_frame(["2020-01-01", "2020-04-01"],
                     lambda x: x, lambda x: x * 0.001, width=40)
    # Demeaned excess column, as the script builds it.
    obs["xfwd"] = obs["fwd"] - obs.groupby("as_of")["fwd"].transform("mean")
    spread, mono = sib._decile_spread(obs, "score", "xfwd")
    assert spread is not None and spread > 0
    assert mono is True


# --------------------------------------------------------------------------- #
# 3. Forward-return alignment (no off-by-one)                                 #
# --------------------------------------------------------------------------- #

def test_forward_return_starts_at_entry_bar():
    """Bars every 2 days; as-of falls on a NON-trading day → entry snaps
    BACK to the last bar <= as_of (2020-01-09, index 4). fwd_5 must be
    close[9]/close[4]-1 exactly — any ±1 slip changes the value."""
    closes = [100.0 + i for i in range(30)]
    bars = _mk_bars("AAA", n=30, closes=closes, step_days=2)  # 01,03,05,...
    hist = {"revenue": [_annual(2019, 1000.0, "2020-01-05")],
            "net_income": [_annual(2019, 100.0, "2020-01-05")]}
    obs = sib._build_observations([bars], {"AAA": hist}, [date(2020, 1, 10)], (5,))
    assert len(obs) == 1
    row = obs.iloc[0]
    assert row["entry_date"] == "2020-01-09"
    assert row["fwd_5"] == pytest.approx(109.0 / 104.0 - 1.0)
    # Explicitly not the ±1 neighbours.
    assert row["fwd_5"] != pytest.approx(110.0 / 105.0 - 1.0)
    assert row["fwd_5"] != pytest.approx(108.0 / 103.0 - 1.0)


def test_observation_dropped_when_forward_window_incomplete():
    """A signal-date whose forward window runs past stored history yields
    NOTHING (structural no-look-ahead on the return side)."""
    bars = _mk_bars("AAA", n=20)
    hist = {"revenue": [_annual(2019, 1000.0, "2020-01-02")],
            "net_income": [_annual(2019, 100.0, "2020-01-02")]}
    # Entry would be bar 17 (2020-01-18); 17+5 >= 20 → dropped.
    obs = sib._build_observations([bars], {"AAA": hist}, [date(2020, 1, 18)], (5,))
    assert obs.empty


# --------------------------------------------------------------------------- #
# Substrate seam: fetch_cache kind='sec_facts_history', TTL-free              #
# --------------------------------------------------------------------------- #

def test_load_fact_histories_reads_cache_rows_ignoring_ttl(db: Session):
    payload = {"revenue": [_annual(2019, 1000.0, "2020-02-01").__dict__]}
    db.add(FetchCache(
        ticker="AAPL", kind="sec_facts_history",
        payload=json.dumps(payload),
        # Deliberately ancient: the backtest read must NOT enforce the
        # 7-day live-path freshness window.
        fetched_at=datetime(2020, 1, 1, tzinfo=UTC),
    ))
    db.add(FetchCache(
        ticker="BAD", kind="sec_facts_history",
        payload="{not json", fetched_at=datetime(2020, 1, 1, tzinfo=UTC),
    ))
    db.commit()
    out = sib._load_fact_histories(db, ["AAPL", "BAD", "MSFT"])
    assert set(out) == {"AAPL"}          # corrupt row skipped, missing absent
    pt = out["AAPL"]["revenue"][0]
    assert isinstance(pt, FactPoint)
    assert pt.val == 1000.0 and pt.filed == "2020-02-01"


# --------------------------------------------------------------------------- #
# End-to-end: run() on a seeded mini-universe + artifact write vs dry-run     #
# --------------------------------------------------------------------------- #

def _seed_monotone_universe(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """12 stocks; fundamentals quality AND forward return both strictly
    increasing in k: closes flat at 100 through the 2020-04-01 entry bar
    (index 91), then jump to 100+k → fwd_5 = k/100."""
    for k in range(1, 13):
        closes = [100.0] * 92 + [100.0 + k] * 28
        _seed_stock(db, f"S{k:02d}", closes)
    hists = {f"S{k:02d}": _synth_hist(k) for k in range(1, 13)}
    monkeypatch.setattr(sib, "_load_fact_histories", lambda _db, _tickers: hists)


def test_run_end_to_end_perfect_composite_ic(db, monkeypatch, tmp_path):
    _seed_monotone_universe(db, monkeypatch)
    artifact = tmp_path / "score_ic_report.json"
    monkeypatch.setattr(sib, "_ARTIFACT_PATH", artifact)

    payload = sib.run(start=date(2020, 2, 1), every=1, horizons=(5,),
                      min_bars=50, dry_run=False)

    # Exactly one usable cross-section (2020-04-01; later grid dates lack
    # the forward window), all 12 stocks observed.
    cov = payload["coverage"]
    assert cov["n_observations"] == 12
    assert cov["n_dates_observed"] == 1
    assert cov["pillars_excluded"].keys() == {"value", "sentiment"}

    res = payload["results"]["5"]
    # Fundamentals rank == forward-return rank by construction → IC = 1
    # for every reconstructed pillar and the composite.
    for label in ("profitability", "sustainability", "growth", "composite"):
        assert res[label]["ic_mean"] == pytest.approx(1.0), label
        assert res[label]["n_dates"] == 1
    assert res["composite"]["decile_spread"] > 0
    assert res["composite"]["ic_by_date"] == [["2020-04-01", 1.0]]
    # Single date → std/t undefined, reported as None (not fabricated).
    assert res["composite"]["ic_std"] is None
    assert res["composite"]["t_stat"] is None

    # Artifact written and identical to the returned payload.
    assert artifact.exists()
    assert json.loads(artifact.read_text(encoding="utf-8")) == payload
    # Atomic-write leftover must not linger.
    assert not artifact.with_suffix(".json.tmp").exists()


def test_run_dry_run_writes_nothing(db, monkeypatch, tmp_path):
    _seed_stock(db, "AAA", [100.0] * 60)
    monkeypatch.setattr(sib, "_load_fact_histories", lambda _db, _t: {})
    artifact = tmp_path / "score_ic_report.json"
    monkeypatch.setattr(sib, "_ARTIFACT_PATH", artifact)

    payload = sib.run(start=date(2020, 1, 1), every=1, horizons=(5,),
                      min_bars=50, dry_run=True)

    assert payload["results"] == {}          # no PIT facts → honest empty
    assert payload["coverage"]["with_pit_facts"] == 0
    assert not artifact.exists()
