"""Score-IC backtest for the Qualità composite pillars (B4-8, roadmap gate #9).

WHY THIS SCRIPT EXISTS
══════════════════════
The standing rule (CLAUDE.md, Engine Quality v1): NO weighting change to the
Qualità composite is allowed without an IC backtest showing the change helps.
The obvious substrate — `score_history` (persisted composite/pillar snapshots
per scan day) — has only ~15 capture days as of 2026-07; a meaningful IC study
needs 6-12 MONTHS of cross-sections at minimum. This script instead uses a
substrate that works TODAY: point-in-time SEC fundamentals.

SUBSTRATE (explored 2026-07 — where the point-in-time data actually lives)
══════════════════════════════════════════════════════════════════════════
- `app/services/sec_fundamentals_history.py` fetches SEC EDGAR XBRL
  `companyfacts` per ticker and parses it into a compact
  `{concept: [FactPoint(end, val, filed, form, start, duration_days)]}` map.
  The `filed` date is the PIT marker: the day the number became PUBLIC.
  De-dup keeps the EARLIEST `filed` per (end, val) so amendments can't
  inflate look-back.
- The parsed history is persisted in the `fetch_cache` table under
  `kind='sec_facts_history'` (constant `_CACHE_KIND` in that module). This
  script reads THOSE CACHED ROWS ONLY — no network, no TTL check (a filed
  2012 10-K does not go stale for backtesting purposes). The cache is
  populated by any prior run of `get_fact_history` (e.g. the
  `entry_ic_report --validate-fundamentals` study, which resolved ~552 US
  stocks of the 999-name universe; non-US names have no SEC filings and are
  skipped gracefully — they simply have no cache row).
- Filed dates go back to ~2007-2009 (XBRL is reliable from ~2009), so a
  quarterly as-of grid from 2010 gives ~65 cross-sections.
- Forward returns come from stored `ohlcv_daily` closes (no network).
- IC conventions reuse `app/scripts/entry_ic_report.py`'s methodology:
  per-date Spearman rank-IC then averaged across dates (Grinold-Kahn; a
  pooled correlation would be inflated by autocorrelation), decile spread on
  market-neutral (per-date demeaned) forward returns with per-date bucketing.

PILLAR RECONSTRUCTION MAP (honest coverage — the core of the exercise)
══════════════════════════════════════════════════════════════════════
Each reconstructed component uses ONLY facts with `filed <= as_of`. Pillars
that cannot be rebuilt point-in-time are EXCLUDED, not approximated with
today's data (that would be the exact look-ahead this gate exists to prevent).

  profitability  — RECONSTRUCTED (all 5 weighted components):
      gross_margin (0.30), roa (0.26), roe (0.18), net_margin (0.14),
      operating_margin (0.12) from TTM gross_profit / net_income /
      operating_income / revenue + instant assets / equity. The 0-weight
      insider/institutional components are informational in production and
      irrelevant here.
  sustainability — PARTIAL: debt_to_equity (0.13), fcf_positive (0.15),
      fcf_to_ni (0.12) from long_term_debt / equity / OCF / capex.
      NOT reconstructable (concepts not in CONCEPT_TAGS / not filed):
      current_ratio, quick_ratio, dividend_coverage, payout sanity,
      earnings_stability_5y, margin_trend_3y, Yahoo overall_risk.
      Weights renormalised over the present components.
  growth         — PARTIAL: rev_yoy (0.18), ni_yoy (0.18), rev_cagr_5y
      (0.15), ni_cagr_5y (0.15) from TTM-vs-TTM comparisons.
      NOT reconstructable: analyst-projected growth (production
      revenue_growth prefers the consensus projection), eps_forward vs
      trailing, earnings beats (no filed record of historical estimates),
      QoQ lanes (kept out — the M1 study already demoted them as noise).
  value          — EXCLUDED. P/E and P/B mix split-ADJUSTED ohlcv_daily
      prices with SEC's UNADJUSTED as-reported per-share / share-count
      facts; without a split-history reconciliation the ratio is corrupt
      (same reason entry_ic_report._FUND_SIGNALS excludes it).
  sentiment      — EXCLUDED. No filed record of historical analyst
      estimates/targets/ratings exists in the SEC substrate (documented
      known gap in sec_fundamentals_history).

The composite tested here is the EQUAL-WEIGHT mean of the reconstructed
pillar scores (requires >= 2 pillars present per observation) — it is a
proxy for the production composite, not a replica: 2 of 5 production
pillars are missing and the production PILLAR_WEIGHTS are not applied
(applying them to a 3-pillar subset would misrepresent both).

METHOD CAVEATS (read before trusting the numbers)
═════════════════════════════════════════════════
- Percentile-rank proxy: production components map raw values through
  monotone ramps (`_ramp3` / `_blended_hib`) and sector blends; here each
  component becomes its per-date cross-sectional percentile (sign-flipped
  for lower-is-better). Per-component rank-IC is IDENTICAL under any
  monotone transform; the pillar/composite IC can differ from production
  only via the weighting of components, which we mirror.
- Survivorship bias: the universe is TODAY's stocks table — 2012 names that
  delisted are absent, so absolute IC levels are optimistic. Relative
  pillar-vs-pillar comparisons are less affected. State this when quoting.
- Knowledge-YoY: rev_yoy compares "TTM known at t" vs "TTM known at t-1y"
  (both PIT-filtered at their own date) — same conservative convention as
  entry_ic_report._fund_signals_as_of.
- Entry bar = last trading bar with date <= as_of; facts filed on as_of are
  knowable by that bar's close. Forward return = close[i+h]/close[i] - 1
  over h TRADING bars.

USAGE (integrator runs it; do NOT run while a replay is hogging the machine)
════════════════════════════════════════════════════════════════════════════
    cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.score_ic_backtest
      --start YYYY-MM-DD  first as-of quarter (default 2010-01-01; snapped
                          forward to the next quarter start)
      --every N           quarters between as-of dates (default 1)
      --horizons a,b,c    forward horizons in trading bars (default 21,63,126)
      --sample N          cap eligible stocks to the first N by id
      --min-bars N        require >= N ohlcv bars (default 252)
      --dry-run           compute + print, do NOT write the artifact

Emits `app/data/score_ic_report.json` + a console table.
"""
from __future__ import annotations

import argparse
import json
from bisect import bisect_right
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy import bindparam, select, text

from app.models import FetchCache
from app.services import sec_fundamentals_history as sf
from app.services.sec_fundamentals_history import FactPoint

# Artifact destination (next to signal_calibration.json, same convention as
# replay_outcomes_summary.json). Module-level so tests monkeypatch it.
_ARTIFACT_PATH = Path(__file__).resolve().parents[1] / "data" / "score_ic_report.json"

_DEFAULT_HORIZONS = (21, 63, 126)
_N_BUCKETS = 10          # deciles for the spread analysis
_MIN_XS_WIDTH = 10       # min per-date cross-section width for a valid IC
_MIN_PILLARS = 2         # composite needs >= 2 reconstructed pillars present

# Per-pillar component map: (component, direction, weight). Directions and
# weights mirror score_service's pillar definitions (see the module docstring
# for what each pillar is missing). direction=-1 → lower is better.
_PILLAR_COMPONENTS: dict[str, list[tuple[str, int, float]]] = {
    "profitability": [
        ("gross_margin", +1, 0.30),
        ("roa", +1, 0.26),
        ("roe", +1, 0.18),
        ("net_margin", +1, 0.14),
        ("operating_margin", +1, 0.12),
    ],
    "sustainability": [
        ("debt_to_equity", -1, 0.13),
        ("fcf_positive", +1, 0.15),
        ("fcf_to_ni", +1, 0.12),
    ],
    "growth": [
        ("rev_yoy", +1, 0.18),
        ("ni_yoy", +1, 0.18),
        ("rev_cagr_5y", +1, 0.15),
        ("ni_cagr_5y", +1, 0.15),
    ],
}
# Binary components carry their own absolute 0/100 meaning — percentiling a
# constant-1 column would turn "everyone FCF-positive" into a meaningless tie.
_BINARY_COMPONENTS = {"fcf_positive"}

# Documented exclusions, embedded in the artifact so the JSON is self-honest.
_EXCLUDED_PILLARS = {
    "value": "split-adjusted OHLCV price vs SEC unadjusted per-share/share-count"
             " facts — ratio corrupt without split reconciliation",
    "sentiment": "no filed record of historical analyst estimates/targets",
}


@dataclass
class _StockBars:
    """Per-stock chronological close series with ISO dates."""
    stock_id: int
    ticker: str
    dates: list[str]      # ISO, sorted ascending
    closes: np.ndarray    # float64, same length


def _load_universe(db, *, min_bars: int = 252, sample: int | None = None) -> list[_StockBars]:
    """Stocks with >= min_bars of stored OHLCV, plus their full close series.
    `sample` caps the eligible ids (by id, deterministic) BEFORE the heavy
    bar load so a capped run is actually cheap."""
    sql = """
        SELECT s.id, s.ticker
        FROM stocks s
        WHERE (SELECT COUNT(*) FROM ohlcv_daily o WHERE o.stock_id = s.id)
              >= :min_bars
        ORDER BY s.id
    """
    params: dict = {"min_bars": min_bars}
    if sample is not None:
        sql += " LIMIT :cap"
        params["cap"] = sample
    rows = db.execute(text(sql), params).all()
    if not rows:
        return []
    ids = [r[0] for r in rows]
    ticker_by_id = {r[0]: r[1] for r in rows}

    bars = db.execute(
        text(
            """
            SELECT stock_id, date, close
            FROM ohlcv_daily
            WHERE stock_id IN :ids
            ORDER BY stock_id, date
            """
        ).bindparams(bindparam("ids", expanding=True)),
        {"ids": ids},
    ).all()

    out: list[_StockBars] = []
    cur_id: int | None = None
    cur_dates: list[str] = []
    cur_closes: list[float] = []

    def _flush() -> None:
        if cur_id is None or len(cur_closes) < min_bars:
            return
        out.append(_StockBars(
            stock_id=cur_id,
            ticker=ticker_by_id.get(cur_id, str(cur_id)),
            dates=list(cur_dates),
            closes=np.asarray(cur_closes, dtype="float64"),
        ))

    for sid, d, close in bars:
        if sid != cur_id:
            _flush()
            cur_id = sid
            cur_dates = []
            cur_closes = []
        cur_dates.append(str(d)[:10])
        cur_closes.append(float(close) if close is not None else np.nan)
    _flush()
    return out


def _load_fact_histories(db, tickers: list[str]) -> dict[str, dict[str, list[FactPoint]]]:
    """Read the cached `sec_facts_history` rows DIRECTLY from fetch_cache —
    no network, no TTL (filed history does not go stale for a backtest; the
    7-day freshness window in the service exists for the LIVE read path).
    Tickers without a row (non-US / never fetched) are simply absent."""
    rows = db.execute(
        select(FetchCache).where(
            FetchCache.kind == sf._CACHE_KIND,
            FetchCache.ticker.in_(tickers),
        )
    ).scalars().all()
    out: dict[str, dict[str, list[FactPoint]]] = {}
    for r in rows:
        try:
            payload = json.loads(r.payload)
            hist = {
                concept: [FactPoint(**fp) for fp in pts]
                for concept, pts in payload.items()
            }
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.warning(f"[score-ic] corrupt sec_facts_history for {r.ticker}: {e}")
            continue
        if hist:
            out[r.ticker] = hist
    return out


def _quarterly_grid(start: date, end: date, every: int = 1) -> list[date]:
    """Quarter-start as-of dates (Jan/Apr/Jul/Oct 1st) from the first quarter
    start on/after `start` through `end`, stepping `every` quarters."""
    qm = ((start.month - 1) // 3) * 3 + 1
    d = date(start.year, qm, 1)
    if d < start:  # snap FORWARD (never grant an as-of earlier than asked)
        d = _add_quarters(d, 1)
    out: list[date] = []
    while d <= end:
        out.append(d)
        d = _add_quarters(d, every)
    return out


def _add_quarters(d: date, q: int) -> date:
    m_total = d.month + 3 * q
    return date(d.year + (m_total - 1) // 12, (m_total - 1) % 12 + 1, 1)


def pillar_inputs_as_of(
    hist: dict[str, list[FactPoint]], as_of: date,
) -> dict[str, float | None]:
    """Raw component values for the reconstructable pillars, using ONLY facts
    with filed <= as_of (delegated to the PIT-disciplined `ttm_flow` /
    `latest_instant` helpers). Division guards return None on missing/zero/
    negative denominators rather than inf or sign-flipped garbage."""
    def _ttm(concept: str, d: date = as_of) -> float | None:
        return sf.ttm_flow(hist, concept, d)

    def _inst(concept: str) -> float | None:
        fp = sf.latest_instant(hist, concept, as_of)
        return fp.val if fp else None

    rev = _ttm("revenue")
    ni = _ttm("net_income")
    gp = _ttm("gross_profit")
    oi = _ttm("operating_income")
    ocf = _ttm("operating_cash_flow")
    capex = _ttm("capex")
    eq = _inst("equity")
    assets = _inst("assets")
    debt = _inst("long_term_debt")

    def _div(a: float | None, b: float | None) -> float | None:
        """a/b requiring a POSITIVE denominator (negative equity/revenue
        makes every ratio here uninterpretable)."""
        if a is None or b is None or b <= 0:
            return None
        return a / b

    fcf = (ocf - capex) if (ocf is not None and capex is not None) else None
    # capex in companyfacts is a positive outflow magnitude; FCF = OCF - capex.

    # Knowledge-YoY: prior TTM is PIT-filtered at its OWN date (conservative;
    # same convention as entry_ic_report._fund_signals_as_of).
    prev = as_of - timedelta(days=365)
    five = as_of - timedelta(days=round(5 * 365.25))
    rev_prev = _ttm("revenue", prev)
    ni_prev = _ttm("net_income", prev)
    rev_5 = _ttm("revenue", five)
    ni_5 = _ttm("net_income", five)

    return {
        # profitability
        "gross_margin": _div(gp, rev),
        "roa": _div(ni, assets),
        "roe": _div(ni, eq),
        "net_margin": _div(ni, rev),
        "operating_margin": _div(oi, rev),
        # sustainability (partial)
        "debt_to_equity": _div(debt, eq),
        "fcf_positive": (1.0 if fcf > 0 else 0.0) if fcf is not None else None,
        # FCF/NI only meaningful with positive NI (sign flips otherwise).
        "fcf_to_ni": _div(fcf, ni) if (ni is not None and ni > 0) else None,
        # growth (partial)
        "rev_yoy": (rev / rev_prev - 1.0) if (rev and rev_prev and rev_prev > 0) else None,
        "ni_yoy": (ni / ni_prev - 1.0) if (ni is not None and ni_prev and ni_prev > 0) else None,
        "rev_cagr_5y": (
            (rev / rev_5) ** 0.2 - 1.0
            if (rev and rev_5 and rev > 0 and rev_5 > 0) else None
        ),
        "ni_cagr_5y": (
            (ni / ni_5) ** 0.2 - 1.0
            if (ni and ni_5 and ni > 0 and ni_5 > 0) else None
        ),
    }


def _build_observations(
    universe: list[_StockBars],
    histories: dict[str, dict[str, list[FactPoint]]],
    grid: list[date],
    horizons: tuple[int, ...],
) -> pd.DataFrame:
    """Long observation frame: one row per (stock, as_of) with the raw PIT
    component values + forward returns. Entry bar = LAST bar with
    date <= as_of (facts filed on as_of are knowable by that close);
    observations whose forward window is not fully in stored history are
    dropped (structural no-look-ahead — same rule as the replay scripts).
    Then scores the cross-sections (percentiles → pillars → composite) and
    adds per-date demeaned excess forward returns for the decile spread."""
    max_h = max(horizons)
    rows: list[dict] = []
    for s in universe:
        hist = histories.get(s.ticker)
        if not hist:
            continue
        n = len(s.closes)
        for as_of in grid:
            i = bisect_right(s.dates, as_of.isoformat()) - 1
            if i < 0 or i + max_h >= n:
                continue
            entry = s.closes[i]
            if not np.isfinite(entry) or entry <= 0:
                continue
            inputs = pillar_inputs_as_of(hist, as_of)
            if all(v is None for v in inputs.values()):
                continue
            row: dict = {
                "stock_id": s.stock_id, "ticker": s.ticker,
                "as_of": as_of.isoformat(), "entry_date": s.dates[i],
            }
            row.update(inputs)
            for h in horizons:
                row[f"fwd_{h}"] = float(s.closes[i + h] / entry - 1.0)
            rows.append(row)
    if not rows:
        return pd.DataFrame()
    obs = pd.DataFrame(rows)
    _score_cross_sections(obs)
    # Market-neutral excess forward returns (per-date demeaned) — used by
    # the decile spread so it measures signal edge, not market direction.
    # Rank-IC is invariant to the per-date shift, so it's unaffected.
    for h in horizons:
        col = f"fwd_{h}"
        obs[f"xfwd_{h}"] = obs[col] - obs.groupby("as_of")[col].transform("mean")
    return obs


def _score_cross_sections(obs: pd.DataFrame) -> None:
    """In-place: per-date component percentiles (0-100, sign-adjusted) →
    weighted-present pillar scores → equal-weight composite. Mirrors
    score_service._aggregate's missing-data neutralisation: absent
    components drop out and their weight is renormalised."""
    for pillar, comps in _PILLAR_COMPONENTS.items():
        num = pd.Series(0.0, index=obs.index)
        den = pd.Series(0.0, index=obs.index)
        for name, direction, w in comps:
            # A column that is all-None comes out object-dtype from the row
            # dicts — coerce to float so rank/arithmetic behave.
            vals = pd.to_numeric(obs[name], errors="coerce")
            if name in _BINARY_COMPONENTS:
                score = vals * 100.0
            else:
                pct = vals.groupby(obs["as_of"]).rank(pct=True)
                score = pct * 100.0 if direction > 0 else (1.0 - pct) * 100.0
            present = score.notna()
            num = num + score.where(present, 0.0) * w
            den = den + present.astype(float) * w
        obs[f"pillar_{pillar}"] = (num / den).where(den > 0)
    pillar_cols = [f"pillar_{p}" for p in _PILLAR_COMPONENTS]
    present_n = obs[pillar_cols].notna().sum(axis=1)
    obs["composite"] = obs[pillar_cols].mean(axis=1).where(present_n >= _MIN_PILLARS)


def _rank_ic_by_date(
    obs: pd.DataFrame, col: str, fwd_col: str, *, min_width: int = _MIN_XS_WIDTH,
) -> list[tuple[str, float]]:
    """Per-as-of-date Spearman rank-IC (pandas rank + np.corrcoef, same as
    entry_ic_report). Dates with a cross-section narrower than `min_width`
    valid pairs are skipped — a 3-stock correlation is noise, not signal."""
    out: list[tuple[str, float]] = []
    for d, grp in obs.groupby("as_of"):
        x = grp[col]
        y = grp[fwd_col]
        mask = x.notna() & y.notna()
        if int(mask.sum()) < min_width:
            continue
        xr = x[mask].rank()
        yr = y[mask].rank()
        if xr.nunique() < 2 or yr.nunique() < 2:
            continue
        ic = float(np.corrcoef(xr, yr)[0, 1])
        if np.isfinite(ic):
            out.append((str(d), ic))
    return out


def _ic_stats(pairs: list[tuple[str, float]]) -> dict:
    """mean / std / t-stat of the per-date IC series. t = mean/(std/sqrt(n)):
    the standard per-date-IC significance test (each cross-section treated
    as a quasi-independent draw)."""
    if not pairs:
        return {"n_dates": 0, "ic_mean": None, "ic_std": None, "t_stat": None}
    arr = np.array([ic for _, ic in pairs])
    mean = float(arr.mean())
    if len(arr) < 2:
        return {"n_dates": len(arr), "ic_mean": round(mean, 4),
                "ic_std": None, "t_stat": None}
    std = float(arr.std(ddof=1))
    t = mean / (std / np.sqrt(len(arr))) if std > 0 else None
    return {
        "n_dates": len(arr),
        "ic_mean": round(mean, 4),
        "ic_std": round(std, 4),
        "t_stat": round(float(t), 2) if t is not None else None,
    }


def _decile_spread(
    obs: pd.DataFrame, col: str, xfwd_col: str,
) -> tuple[float | None, bool]:
    """Per-date decile bucketing (relative rank THAT day, not pooled-regime),
    means pooled across dates, spread = top - bottom on the market-neutral
    excess return. Returns (spread, monotonic)."""
    sub = obs[["as_of", col, xfwd_col]].dropna()
    if len(sub) < _N_BUCKETS:
        return None, False
    sub = sub.copy()

    def _bucket(g: pd.Series) -> pd.Series:
        if g.nunique() < _N_BUCKETS:
            return pd.Series([np.nan] * len(g), index=g.index)
        try:
            return pd.qcut(g.rank(method="first"), _N_BUCKETS, labels=False)
        except ValueError:
            return pd.Series([np.nan] * len(g), index=g.index)

    sub["bucket"] = sub.groupby("as_of")[col].transform(_bucket)
    sub = sub.dropna(subset=["bucket"])
    if sub.empty:
        return None, False
    means = sub.groupby("bucket")[xfwd_col].mean()
    if len(means) < _N_BUCKETS:
        return None, False
    spread = float(means.iloc[-1] - means.iloc[0])
    diffs = means.diff().dropna()
    monotonic = bool((diffs > 0).all() or (diffs < 0).all())
    return spread, monotonic


def compute_ic_report(
    db,
    *,
    start: date,
    every: int = 1,
    horizons: tuple[int, ...] = _DEFAULT_HORIZONS,
    sample: int | None = None,
    min_bars: int = 252,
) -> dict:
    """Pure computation over the given Session — no writes, no network.
    The caller (run / tests) decides whether to persist the payload."""
    logger.info(f"[score-ic] loading universe (min_bars={min_bars}, sample={sample}) ...")
    universe = _load_universe(db, min_bars=min_bars, sample=sample)
    logger.info(f"[score-ic] {len(universe)} stocks with >= {min_bars} bars")

    histories = _load_fact_histories(db, [s.ticker for s in universe])
    logger.info(f"[score-ic] {len(histories)} stocks with cached PIT SEC facts")

    grid = _quarterly_grid(start, date.today(), every)
    logger.info(f"[score-ic] {len(grid)} as-of dates "
                f"({grid[0] if grid else '—'} .. {grid[-1] if grid else '—'})")

    obs = _build_observations(universe, histories, grid, horizons)

    score_cols = [(f"pillar_{p}", p) for p in _PILLAR_COMPONENTS] + [("composite", "composite")]
    results: dict[str, dict] = {}
    if not obs.empty:
        for h in horizons:
            fwd = f"fwd_{h}"
            block: dict[str, dict] = {}
            for col, label in score_cols:
                pairs = _rank_ic_by_date(obs, col, fwd)
                block[label] = _ic_stats(pairs)
            spread, mono = _decile_spread(obs, "composite", f"xfwd_{h}")
            block["composite"]["decile_spread"] = (
                round(spread, 4) if spread is not None else None
            )
            block["composite"]["decile_monotonic"] = mono
            # Per-date IC series for the composite — the raw evidence a
            # future weighting decision should eyeball, not just the mean.
            block["composite"]["ic_by_date"] = [
                [d, round(ic, 4)]
                for d, ic in _rank_ic_by_date(obs, "composite", fwd)
            ]
            results[str(h)] = block

    return {
        "version": "1",
        "generated_by": "app.scripts.score_ic_backtest",
        "generated_at": datetime.now(UTC).isoformat(),
        "params": {
            "start": start.isoformat(),
            "every_quarters": every,
            "horizons": list(horizons),
            "sample": sample,
            "min_bars": min_bars,
        },
        "coverage": {
            "universe_stocks": len(universe),
            "with_pit_facts": len(histories),
            "n_as_of_dates": len(grid),
            "n_observations": int(len(obs)),
            "n_dates_observed": int(obs["as_of"].nunique()) if not obs.empty else 0,
            "pillars_reconstructed": list(_PILLAR_COMPONENTS),
            "pillars_excluded": dict(_EXCLUDED_PILLARS),
            # Quotable caveat, embedded so the artifact can't be read naively.
            "caveats": [
                "survivorship: universe is today's stocks table — delisted "
                "names absent, absolute IC levels optimistic",
                "composite = equal-weight over 3 reconstructed pillars, NOT "
                "the production 5-pillar PILLAR_WEIGHTS composite",
                "components are per-date percentile proxies of the "
                "production ramp scores (rank-IC invariant per component)",
            ],
        },
        "results": results,
    }


def write_artifact(payload: dict) -> Path:
    """Atomically persist the payload (tmp + rename, indent=2 like the other
    generated study artifacts so the git diff stays readable)."""
    out = _ARTIFACT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(out)
    return out


def _print_report(payload: dict) -> None:
    cov = payload["coverage"]
    print(f"\n{'#' * 78}\n#  SCORE-IC BACKTEST (Qualità pillars, point-in-time SEC facts)")
    print(f"#  universe={cov['universe_stocks']}  with_pit_facts={cov['with_pit_facts']}"
          f"  obs={cov['n_observations']:,}  dates={cov['n_dates_observed']}"
          f"\n{'#' * 78}")
    print("  excluded pillars: "
          + "; ".join(f"{k} ({v.split(' — ')[0]})"
                      for k, v in cov["pillars_excluded"].items()))
    if not payload["results"]:
        print("\n  NO OBSERVATIONS — check that fetch_cache has "
              "sec_facts_history rows (run entry_ic_report "
              "--validate-fundamentals once to populate).\n")
        return
    labels = list(_PILLAR_COMPONENTS) + ["composite"]
    for h, block in payload["results"].items():
        print(f"\n  horizon {h} bars "
              f"{'(~1 month)' if h == '21' else '(~1 quarter)' if h == '63' else '(~6 months)' if h == '126' else ''}")
        print(f"  {'pillar':<16}{'n_dates':>8}{'IC mean':>10}{'IC std':>9}{'t-stat':>8}")
        print("  " + "-" * 51)
        for label in labels:
            st = block[label]
            mean = f"{st['ic_mean']:+.4f}" if st["ic_mean"] is not None else "n/a"
            std = f"{st['ic_std']:.4f}" if st["ic_std"] is not None else "n/a"
            t = f"{st['t_stat']:+.2f}" if st["t_stat"] is not None else "n/a"
            print(f"  {label:<16}{st['n_dates']:>8}{mean:>10}{std:>9}{t:>8}")
        spread = block["composite"].get("decile_spread")
        mono = block["composite"].get("decile_monotonic")
        sp = f"{spread * 100:+.2f}%" if spread is not None else "n/a"
        print(f"  composite decile spread (mkt-neutral): {sp}"
              f"{'  [monotonic]' if mono else ''}")
    print("\n  Rule of thumb (entry_ic_report): |IC| 0.03-0.05 useful, "
          "0.05-0.08 strong, >0.10 suspicious.\n")


def run(
    *,
    start: date,
    every: int = 1,
    horizons: tuple[int, ...] = _DEFAULT_HORIZONS,
    sample: int | None = None,
    min_bars: int = 252,
    dry_run: bool = False,
) -> dict:
    """CLI entrypoint body. Returns the computed payload (tests inspect it)."""
    import app.core.db as dbm  # noqa: PLC0415 — test monkeypatch seam (conftest swaps SessionLocal)

    with dbm.SessionLocal() as db:
        payload = compute_ic_report(
            db, start=start, every=every, horizons=horizons,
            sample=sample, min_bars=min_bars,
        )
    _print_report(payload)
    if dry_run:
        print("  [dry-run] artifact NOT written\n")
    else:
        out = write_artifact(payload)
        print(f"  wrote {out}\n")
    return payload


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=str, default="2010-01-01",
                    help="first as-of date (snapped to next quarter start)")
    ap.add_argument("--every", type=int, default=1,
                    help="quarters between as-of dates")
    ap.add_argument("--horizons", type=str, default="21,63,126",
                    help="comma-separated forward horizons in trading bars")
    ap.add_argument("--sample", type=int, default=None,
                    help="cap eligible stocks to the first N by id")
    ap.add_argument("--min-bars", type=int, default=252)
    ap.add_argument("--dry-run", action="store_true",
                    help="compute + print, do not write the artifact")
    args = ap.parse_args()
    run(
        start=date.fromisoformat(args.start),
        every=max(1, args.every),
        horizons=tuple(int(h.strip()) for h in args.horizons.split(",") if h.strip()),
        sample=args.sample,
        min_bars=args.min_bars,
        dry_run=args.dry_run,
    )
