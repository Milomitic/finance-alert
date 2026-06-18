# Screener: clickable breadth tiles + rich organized filters — design

**Date:** 2026-06-19
**Status:** approved-direction (key decisions made), pending spec review.

## Goal

Two user-facing capabilities on the screener (`StocksBrowserPage`):

1. **Clickable breadth tiles** — clicking a stat tile in the index panorama strip
   (`%>EMA200`, `%>EMA50`, `RSI<30`, `RSI>70`, `52W HI`, `52W LO`, `VOL×`, `A/D`)
   toggles the matching row-level filter on the table below.
2. **Much richer filters**, reorganized into 4 collapsible areas, covering
   classification, fundamental, technical, and price/volume criteria.

## The foundational gap

The metrics that power the breadth tiles (`last_close`, `change_pct`,
`ema50/200`, `rsi14`, `high_252/low_252`, `vol_ratio`) are computed **per stock
at scan time** inside `market_stats_service` (the `StockMetrics` it builds to
aggregate breadth), then discarded. The screener endpoint `/api/stocks/search`
only exposes each stock's *score* + *technical sub-scores* — never its RSI, EMA
position, or change%. So neither ask is wireable today: **the per-row data isn't
persisted or returned.**

**Solution:** persist a per-stock metrics layer and join it in search. This one
addition unlocks both asks (filter + sort on the metrics; tiles become
predicates).

## Freshness model

The persisted metrics are **EOD — as of the last scan**, refreshed every scan.
Filtering "RSI < 30" means "as of the last close." Live-tick price stays in
MERCATI LIVE / top-movers; the screener is intentionally EOD. This is a
deliberate, documented choice.

## Architecture

### New table: `stock_metrics` (one row per stock, upserted each scan)

| column | type | notes |
|---|---|---|
| `stock_id` | int PK / FK `stocks.id` | one row per stock |
| `computed_at` | datetime | scan timestamp |
| `last_close` | float | latest daily close |
| `change_pct` | float | daily % change vs prev close |
| `ema50` | float | 50-day EMA |
| `ema200` | float | 200-day EMA |
| `rsi14` | float | 14-day RSI |
| `high_252` | float | 252-bar (52w) high |
| `low_252` | float | 252-bar (52w) low |
| `vol_today` | bigint | today's volume |
| `vol_avg_20` | float | 20-day avg volume |
| `vol_ratio` | float | `vol_today / vol_avg_20` |

Nullable (a stock with <required bars gets a row with NULL metrics or no row;
`LEFT JOIN` keeps it in results). Migration via alembic (batch_alter for SQLite).

### Persistence point

In `market_stats_service.recompute_snapshot()` (already iterates every stock and
builds `StockMetrics`), add an idempotent UPSERT into `stock_metrics` per stock.
No new computation — just persist what's already computed. Runs at scan end, so
the metrics are exactly as fresh as the breadth snapshot.

### Search endpoint (`/api/stocks/search`, `stock_service.py`)

`LEFT JOIN stock_metrics` and add filter params (all optional):

- **Price/volume:** `price_min`, `price_max`, `change_min`, `change_max`,
  `volume_min`, `vol_spike` (bool → `vol_ratio > 2.0`).
- **Technical:** `rsi_min`, `rsi_max`, `above_ema50` (bool → `last_close >
  ema50`), `above_ema200` (bool), `near_52w_high` (bool → `last_close >= 0.95 *
  high_252`), `near_52w_low` (bool → `last_close <= 1.05 * low_252`),
  `has_signals` (bool → stock has ≥1 active/non-archived alert).
- **Fundamental:** `market_cap_min`, `market_cap_max` (on `Stock.market_cap`).

Bool params: present+true applies the predicate; absent = no filter. Range
params validate numeric; 422 on bad input (mirror existing `min_score`).

Add to `SORTABLE_COLUMNS`: `last_close` (price), `change_pct`, `rsi14`,
`vol_ratio`. This also retires the current client-side `change_pct` sort hack.

Add a `metrics` block to the row response (`StockSearchItemOut`): `last_close,
change_pct, rsi14, ema50, ema200, high_252, low_252, vol_ratio` (all
`float|null`). The table reads these directly instead of merging the
market-summary snapshot client-side.

### Frontend

- **`StockFiltersCard`** → 4 collapsible `<details>`-style areas, each
  open/closable, remembering open state in localStorage:
  - **Mercato:** Indice · Settore · Industry · Exchange · Paese (existing).
  - **Fondamentali:** Score min–max · Rischio · 5 pilastri ≥ · **Market cap range** (new).
  - **Tecnici** (new): Tecnico range · Postura · **RSI range** · **sopra/sotto
    EMA50** · **sopra/sotto EMA200** · **vicino max/min 52s** · **con segnali**.
  - **Prezzo & Volume** (new): **Prezzo range** · **Δ% range** · **volume spike
    >2×** · **volume min**.
  - Keep the existing "Attivi:" removable-chip row; it auto-covers the new
    filters (each filter renders a chip).
- **Filter state:** extend `FiltersState` + URL-param parse/serialize
  (`toQuery`) for every new param. Same React-state→URL mirror mechanism.
- **`IndexPanoramaCard`** tiles → clickable buttons. State lifts to
  `StocksBrowserPage` via an `onTileFilter(filterPatch)` callback that
  merges the predicate into `FiltersState` (toggle: re-click clears). Mapping:
  - `%>EMA200`→`above_ema200`, `%>EMA50`→`above_ema50`, `RSI<30`→`rsi_max=30`,
    `RSI>70`→`rsi_min=70`, `52W HI`→`near_52w_high`, `52W LO`→`near_52w_low`,
    `VOL×`→`vol_spike`, `A/D`→`change_min=0` (advancers, Δ%>0).
  - `N STOCKS` and `AVG Δ%` stay non-clickable (pure aggregates).
  - Active tile gets the `border-info` highlight; tooltip still on hover.
- **`StockBrowserTable`** → add toggleable columns for `RSI`, `Δ%` (from
  metrics), `vol×`; keep the existing column-visibility menu.

## Phasing

- **Phase A — backend substrate + filters:** `stock_metrics` table + migration +
  persist in `recompute_snapshot` + search params/validation + response metrics
  block + sortable columns + tests.
- **Phase B — frontend:** filter state/URL + 4 collapsible areas + new controls +
  tile-click wiring + new columns + dist rebuild.

A one-off `recompute_snapshot` (or the next scan) populates `stock_metrics`
before Phase B is testable end-to-end.

## Testing

- Backend (`pytest`): metrics-persist upsert test; one search-filter test per new
  param (price range, change range, rsi range, above_ema50/200, near_52w_*,
  vol_spike, volume_min, market_cap range, has_signals); sort tests for the new
  columns; 422 validation tests for bad numeric input.
- Frontend: `npm run build` (tsc + vite) green; manual smoke — click each tile,
  confirm the chip + table narrow; open/close each area.

## Out of scope (note, don't build)

- Raw fundamentals filters (P/E, margins, dividend) — those live in the
  `fetch_cache` JSON, not in `StockScore`; exposing them needs extracting into
  `stock_metrics` too. Deferred; can extend the same table later.
- Live-tick filtering — EOD is the chosen model.
