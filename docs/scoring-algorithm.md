# Stock Scoring Algorithm

A composite score per stock (0–100) computed from fundamentals, technicals,
analyst sentiment, and news activity. Surfaced via dashboard "Top Picks"
and a per-stock breakdown card on the detail page.

---

## Composite score (0–100)

Weighted average of five sub-scores, each itself 0–100:

| Sub-score | Weight | What it measures                                   |
|-----------|--------|----------------------------------------------------|
| Quality   | 25%    | Margin profile, returns on capital, balance sheet  |
| Growth    | 25%    | Top/bottom-line growth, earnings beat consistency  |
| Value     | 15%    | Valuation multiples vs benchmarks                  |
| Momentum  | 20%    | Price trend + technical signals                    |
| Sentiment | 15%    | Analyst consensus + news activity                  |

NULL sub-scores (missing data) are excluded and remaining weights
re-normalized — a stock with no analyst coverage still gets a composite
from the other four pillars.

The composite is rounded to the nearest 0.1 for display.

---

## Sub-score formulas

Each formula maps raw values to a 0–100 component score using piecewise-linear
ramps. Caps are intentional — the goal is "good / not good" signal, not
ranking by absolute magnitude.

### Quality (max 100)

| Component       | Max pts | Full when      | Half when    | Zero when    |
|-----------------|---------|----------------|--------------|--------------|
| ROE             | 30      | ≥ 20%          | 10%          | ≤ 0%         |
| Profit margin   | 25      | ≥ 20%          | 10%          | ≤ 0%         |
| Free cash flow  | 20      | > 0            | —            | ≤ 0          |
| Debt/Equity     | 15      | ≤ 50%          | 100%         | ≥ 200%       |
| Current ratio   | 10      | ≥ 2            | 1            | ≤ 0.7        |

### Growth (max 100)

| Component                    | Max pts | Full when | Half when | Zero when    |
|------------------------------|---------|-----------|-----------|--------------|
| Revenue growth (YoY)         | 35      | ≥ 20%     | 0%        | ≤ -10%       |
| EPS growth (YoY)             | 35      | ≥ 20%     | 0%        | ≤ -10%       |
| Earnings-beat ratio (last 4) | 30      | 4/4 beats | 2/4       | 0/4          |

### Value (max 100)

| Component       | Max pts | Logic                                                                |
|-----------------|---------|----------------------------------------------------------------------|
| P/E (TTM)       | 40      | Below sector median = full; above = scaled down. Use static sector medians table for V1 |
| PEG             | 30      | ≤ 1 = full, 2 = 50%, ≥ 3 = 0                                         |
| Dividend yield  | 30      | > 3% = full, 0% = 0; minor weight (not all stocks pay dividends)     |

### Momentum (max 100)

| Component                | Max pts | Logic                                                |
|--------------------------|---------|------------------------------------------------------|
| 52-week change           | 30      | ≥ 50% = full, 0% = 50%, ≤ -30% = 0                   |
| RSI                      | 20      | 30–70 = 50%, oversold (< 30) = 80% (bounce), overbought (> 70) = 20% |
| MACD trend (line vs sig) | 20      | line > signal AND hist > 0 = full; else 0            |
| 30-day momentum          | 30      | ≥ 10% = full, 0% = 50%, ≤ -10% = 0                   |

### Sentiment (max 100)

| Component                          | Max pts | Logic                                       |
|------------------------------------|---------|---------------------------------------------|
| Analyst price-target upside        | 50      | ≥ 20% above current = full, 0% = 50%, ≤ -10% = 0 |
| Recent upgrades − downgrades (90d) | 30      | ≥ +3 net upgrades = full, 0 = 50%, ≤ -3 = 0 |
| News volume (last 30d)             | 20      | ≥ 20 articles = full, 0 = 0 (linear)        |

NLP-based news *sentiment* (positive/negative tone) is **out of scope for V1** —
adds infrastructure (model hosting, batch processing) without clear ROI.
News *volume* is a coarse proxy: more coverage ≈ more attention.

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
    stock_id     INTEGER PRIMARY KEY REFERENCES stocks(id) ON DELETE CASCADE,
    composite    REAL NOT NULL,
    quality      REAL,
    growth       REAL,
    value        REAL,
    momentum     REAL,
    sentiment    REAL,
    risk_tier    VARCHAR(16) NOT NULL,
    computed_at  DATETIME WITH TIMEZONE NOT NULL,
    breakdown    TEXT NOT NULL  -- JSON: per-component raw inputs + points
);
CREATE INDEX ix_stock_scores_composite ON stock_scores(composite DESC);
CREATE INDEX ix_stock_scores_risk_tier ON stock_scores(risk_tier);
```

`breakdown` stores the per-component inputs + points so the UI can show a
transparent "why this score" view without re-fetching upstream data.

---

## Recomputation triggers

A score is **stale** if its `computed_at` is older than the most recent of:
- The stock's most recent OHLCV bar
- The stock's last fundamentals fetch (`stock_fundamentals_service` cache)

Triggers (order of priority):
1. **At end of `scan_runner` success path** — recompute all stocks (~1132)
   in one pass. Each computation is in-memory arithmetic + a fundamentals
   lookup; should run in well under a minute.
2. **After `warmup_fundamentals`** — same batch recompute.
3. **Manual**: `POST /api/admin/recompute-scores` for testing or when a
   user wants fresh values without waiting for the next scan.

The batch recompute is a single transaction with `UPSERT` semantics
(via `INSERT ... ON CONFLICT(stock_id) DO UPDATE`).

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
    "quality":   85.2,
    "growth":    62.0,
    "value":     45.8,
    "momentum":  88.9,
    "sentiment": 91.3
  },
  "risk_tier": "moderate",
  "computed_at": "2026-05-04T15:13:39Z",
  "breakdown": {
    "quality": {
      "roe":           {"raw": 0.27, "points": 30, "max": 30},
      "profit_margin": {"raw": 0.24, "points": 25, "max": 25},
      "fcf":           {"raw": 102e9, "points": 20, "max": 20},
      "debt_equity":   {"raw": 145.2, "points": 7.5, "max": 15},
      "current_ratio": {"raw": 0.92, "points": 2.0, "max": 10}
    },
    "growth": { ... },
    ...
  }
}
```

### `GET /api/scores/top`

Returns top picks. Query params:
- `risk` — `conservative` | `moderate` | `aggressive` (omit for all)
- `category` — `composite` (default) | `quality` | `growth` | `value` | `momentum` | `sentiment`
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
