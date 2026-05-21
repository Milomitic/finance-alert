# Stock Scoring Algorithm

A composite score per stock (0–100) from fundamentals, technicals, analyst
data, and news. Surfaced via dashboard "Top Picks" + a per-stock breakdown
card on the detail page.

> **Source of truth = `backend/app/services/score_service.py`.** This doc
> describes the model conceptually; the exact piecewise-linear ramps, sector
> blends, and weights live in code (they evolve via IC-validated retunes — see
> the methodology section). The weights below are current as of 2026-05.

---

## Composite score (0–100)

Weighted average of **six pillars**, each itself 0–100 (`PILLAR_WEIGHTS`):

| Pillar | Weight | What it measures |
|---|---|---|
| Profitability  | 0.15 | Margins, ROE/ROA — sector-aware (vs peer median) |
| Sustainability | 0.15 | Balance-sheet solidity, FCF quality, earnings stability, dividend safety |
| Growth         | 0.23 | Revenue/EPS growth (QoQ/YoY/5Y), earnings-beat consistency |
| Value          | 0.13 | Valuation multiples vs sector medians |
| Momentum       | 0.20 | 12-1 momentum, trend stack, distance-from-52w-high, RSI, MACD |
| Sentiment      | 0.14 | Analyst consensus, net upgrades, news tone |

(Profitability + Sustainability replaced the original single "Quality" pillar.)

**Missing-data renormalization** (`_aggregate`): a pillar — or a component
within a pillar — with no input is *excluded*, and the remaining weights
re-normalize. A stock with no analyst coverage still gets a composite from the
other five pillars; it is never penalized to zero for a gap.

Composite rounded to 0.1 for display. Stored composite is **EWMA-smoothed**
run-over-run with risk-tier hysteresis (`_apply_turnover_control`) to control
churn, and modulated by a bounded **risk-overlay factor** (vol/beta).

---

## Pillar internals (conceptual)

Each component maps a raw value to a 0–100 score via a piecewise-linear ramp
(`_ramp` / `_ramp3`) or a sector-aware blend (`_blended_hib` / `_blended_lib`:
absolute ramp blended with the value's distance from the sector median). The
goal is a "good / not good" signal, not ranking by raw magnitude.

- **Profitability** — gross_margin (0.30, top signal) · ROA (0.26) · ROE (0.18)
  · net margin (0.14) · operating margin (0.12). Weights IC-retuned: margin
  *levels* were demoted (flat/negative long-horizon IC), gross_margin + ROA
  promoted (validated positive).
- **Sustainability** — debt/equity, current/quick ratio, FCF positive, FCF/NI,
  earnings stability (5y), margin trend (3y), dividend coverage + payout
  sanity, Yahoo overall_risk. (A durability/risk filter, not an alpha source.)
- **Growth** — revenue & EPS growth (QoQ/YoY/5Y) with collinearity collapse,
  earnings-beat ratio. (rev_yoy is the strongest fundamental signal by IC.)
- **Value** — P/E and P/B vs sector medians, multiple-blend, dividend lane.
- **Momentum** — 12-1 (Jegadeesh-Titman skip-month, top weight) · trend stack
  (EMA20>50>200) · price vs EMA200 · distance-from-52w-high · 30-day return
  (contrarian: short-term reversal) · 90-day · RSI · MACD · Bollinger · ADX ·
  relative strength vs S&P (US only).
- **Sentiment** — analyst price-target upside · net upgrades−downgrades (90d) ·
  short interest · news tone.

The component breakdown (raw input + score + weight per component) is persisted
in `stock_scores.breakdown` so the UI can render a transparent "why this score".

---

## IC-validation methodology (how weights are set)

Weights are **evidence-based, not guessed.** `app/scripts/entry_ic_report.py`
is a read-only Information-Coefficient harness:

- For each candidate signal, at a monthly grid of historical observation dates,
  it computes the per-date Spearman **rank-IC** vs forward returns at
  **5 / 21 / 63 / 252-day** horizons (averaged across dates — not pooled, to
  avoid autocorrelation inflation), plus decile spread and hit rate.
- **Point-in-time discipline**: technical signals use OHLCV (inherently PIT);
  fundamental signals use SEC EDGAR companyfacts keyed on the `filed` date
  (`sec_fundamentals_history.py`) so a 2019 backtest sees only what was public
  in 2019 — no look-ahead.
- **Market-neutral**: forward returns are demeaned per date for the decile /
  conditional-return analyses, so they measure signal edge, not market drift.
- Retunes are validated **OLD-vs-NEW** before commit (e.g. the momentum retune
  lifted pillar IC +25-35% across horizons; the profitability retune flipped
  the 1-year IC from negative to positive).

Key findings driving the current model:
- Momentum (12-1) is the strongest single factor (IC ~0.05, IR ~0.27 @63d).
- 30-day return is a *reversal* (negative IC) → scored contrarian.
- Margin *levels* (net/operating) are flat-to-negative long-horizon; gross
  margin + ROA + rev_yoy are the validated fundamental signals.
- **Sector-relative ranking degrades** every predictive signal on this
  universe → the cross-sectional engine (`SCORE_ENGINE_XS`) stays **OFF**.
- Naive entry-timing setups (breakout/pullback via classic TA) had **negative**
  edge → no separate entry-timing pillar was built.

---

## Risk tier

Each stock is classified Conservative / Moderate / Aggressive, derived from:

- **Beta (5y)**: < 0.8 conservative; 0.8–1.3 moderate; > 1.3 aggressive
- **90-day return volatility**: < 1.5% conservative; 1.5–3% moderate; > 3% aggressive
- **Sector tilt**: defensive sectors (utilities, consumer staples, healthcare)
  bias toward Conservative; cyclical (tech, consumer discretionary) toward Aggressive
- **Market cap**: > $200B mega-cap shifts down one tier

Implementation: each input maps to {-1, 0, +1} (vs Moderate baseline), summed,
then thresholded to a tier. Lossy but explainable.

---

## Persistence

New table `stock_scores`:

```sql
CREATE TABLE stock_scores (
    stock_id        INTEGER PRIMARY KEY REFERENCES stocks(id) ON DELETE CASCADE,
    composite       REAL NOT NULL,
    profitability   REAL,
    sustainability  REAL,
    growth          REAL,
    value           REAL,
    momentum        REAL,
    sentiment       REAL,
    risk_tier       VARCHAR(16) NOT NULL,
    computed_at     DATETIME WITH TIMEZONE NOT NULL,
    breakdown       TEXT NOT NULL  -- JSON: per-pillar components (raw+score+weight),
                                   --   _meta (coverage), _meta_global, _xs annotations
);
CREATE INDEX ix_stock_scores_composite ON stock_scores(composite DESC);
CREATE INDEX ix_stock_scores_risk_tier ON stock_scores(risk_tier);
```

> A legacy `quality` column may persist for back-compat (= avg of
> profitability + sustainability); current code reads the 6 split pillars.

`breakdown` stores the per-component inputs + points so the UI can show a
transparent "why this score" view without re-fetching upstream data.

---

## Recomputation triggers

A score is **stale** if its `computed_at` is older than the most recent of:
- The stock's most recent OHLCV bar
- The stock's last fundamentals fetch (`stock_fundamentals_service` cache)

Triggers:
1. **End of the nightly `scan_alerts` job** — `recompute_all` re-scores the
   whole catalog (~1,000 stocks) in a two-phase pass (sector-stats pre-pass →
   per-stock score). Fundamentals come from the L1/L2 cache, so it's mostly
   in-memory arithmetic + OHLCV indicator computation.
2. **Manual**: `POST /api/scores/recompute` (background task; progress at
   `GET /api/scores/recompute-status`, cancel via `POST /api/scores/recompute-stop`)
   — the dashboard "Ricalcola" button. Also `POST /api/stocks/{ticker}/score/recompute`
   for a single stock.

`recompute_all` persists incrementally with `db.merge()` UPSERT semantics and
applies the EWMA turnover-control + cross-sectional annotation passes at the end.

---

## API

### `GET /api/stocks/{ticker}/score`

Returns the score + breakdown for one stock. Used by the per-stock
ScoreCard component.

```json
{
  "stock_id": 1,
  "ticker": "AAPL",
  "composite": 78.4,
  "sub_scores": {
    "profitability":  82.1,
    "sustainability": 75.3,
    "growth":         62.0,
    "value":          45.8,
    "momentum":       88.9,
    "sentiment":      91.3
  },
  "risk_tier": "moderate",
  "computed_at": "2026-05-22T15:13:39Z",
  "breakdown": {
    "profitability": {
      "gross_margin":     {"raw": 0.46, "score": 92.0, "weight": 0.30, "present": true, "sector_median": 0.41},
      "roa":              {"raw": 0.28, "score": 100.0, "weight": 0.26, "present": true},
      "roe":              {"raw": 1.50, "score": 100.0, "weight": 0.18},
      "profit_margin":    {"raw": 0.25, "score": 100.0, "weight": 0.14},
      "operating_margin": {"raw": 0.31, "score": 100.0, "weight": 0.12},
      "_meta":            {"coverage": 1.0}
    },
    "growth": { "...": "..." },
    "momentum": { "...": "..." },
    "_meta_global": {"coverage": 0.95},
    "_xs": {"composite": 80.1, "flag_on": false}
  }
}
```

### `GET /api/scores/top`

Returns top picks. Query params:
- `risk` — `conservative` | `moderate` | `aggressive` (omit for all)
- `category` — `composite` (default) | `profitability` | `sustainability` | `growth` | `value` | `momentum` | `sentiment`
- top picks are confidence-gated: stocks with `breakdown._meta_global.coverage < 0.70` are excluded
- `limit` — default 10, max 50

```json
{
  "category": "composite",
  "risk": "moderate",
  "items": [
    {
      "stock_id": 1,
      "ticker": "AAPL",
      "name": "Apple Inc.",
      "composite": 78.4,
      "risk_tier": "moderate",
      "sector": "Technology",
      "market_cap": 2.4e12,
      "change_pct": 1.23
    },
    ...
  ]
}
```

---

## UI surfaces

### Dashboard — `<TopPicksCard />`

Tabbed card on the dashboard:
- Tab strip: **Tutti** / **Conservative** / **Moderate** / **Aggressive**
- Each tab body: top 8 stocks ranked by composite score. Each row:
  ticker (link) + name + composite score (large number) + sub-score
  spark-bars (5 thin tone-colored bars) + risk-tier chip
- Click row → /stocks/:ticker

### Stock detail page — `<StockScoreCard />`

Inserted in the right sidebar (next to the price chart).
- **Composite score gauge** (radial / arc, 0–100) — big centerpiece
- **Risk tier chip** below
- **5 sub-score bars** with labels (Quality / Growth / Value / Momentum / Sentiment)
- Each bar hover-tooltips with the component breakdown (reuse the existing
  Radix Tooltip component already built for the Valuation card)
- **"Computed N min ago"** footer with manual recompute affordance for
  power users

### Stock browser table — score column (V1.5, optional)

Add a **Score** column to `/stocks` with server-side sort. Pre-existing
infra supports this (sort_by + sort_dir already accept new columns).
Skip in V1 to keep scope contained — easy follow-up.

---

## Implementation plan

Two sequential specialized agents (CLAUDE.md note: parallel agents on a
shared tree race on commits).

### Agent 1 — Backend

- New `StockScore` SQLAlchemy model + alembic migration
- New `score_service.py`:
  - `compute_score(db, stock_id) -> StockScore` (single)
  - `recompute_all(db) -> int` (batch, returns count)
  - Internal sub-score functions (`_quality`, `_growth`, `_value`,
    `_momentum`, `_sentiment`) — each returns `(points, max, breakdown_dict)`
  - `_classify_risk(stock, kpis, micro)` → `"conservative" | "moderate" | "aggressive"`
- Hook into `scan_runner.run_tracked_scan` success path
- Hook into `warmup_fundamentals` admin endpoint
- New `/api/scores/top` endpoint
- New `/api/stocks/{ticker}/score` endpoint
- Static sector P/E medians table (hardcoded V1 — can move to DB later)
- **Tests**:
  - Unit tests for each sub-score formula at boundary values (full/half/zero)
  - Integration test: `recompute_all` end-to-end on seeded fixtures
  - API tests for both endpoints

### Agent 2 — Frontend

- Add types: `StockScore`, `TopPickItem`, `ScoreCategory`, `RiskTier`
- New hooks: `useStockScore(ticker)`, `useTopPicks(opts)`
- New `<TopPicksCard />` for dashboard with tabs by risk tier
- New `<StockScoreCard />` for stock detail page (right sidebar)
- Reuse the existing Radix Tooltip for sub-score breakdown
- Slot the cards into HomePage and StockDetailPage

### Out of scope V1 (notes for follow-up)

- NLP news sentiment (requires model hosting infra)
- Score history / trends (would need a `stock_score_history` table)
- Score-based alerts ("notify me when ticker X's score crosses 80")
- Score column in `/stocks` browser (easy follow-up — backend sort
  infra is ready)
- Sector-relative scoring (V1 uses static thresholds; V2 could compare
  each stock to its sector peer median)
