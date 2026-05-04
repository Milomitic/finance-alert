# Economic Calendar Page

A month-grid calendar of upcoming + recent **earnings releases** (per-stock)
and **macro events** (FOMC, CPI, NFP, ECB, etc.). Surfaced at `/calendar`
with a polished, designerly UI.

The goal is a "what's happening this week/month" surface — an analyst's
glance answer to "do I need to be paying attention to anything tomorrow?"

---

## Data sources

### Earnings (per-stock, dynamic)

We already have everything needed in the `stock_fundamentals_service`:

- `Fundamentals.next_earnings_date` — ISO `YYYY-MM-DD`, the upcoming release
- `Fundamentals.next_eps_estimate` — consensus EPS estimate (when available)
- `Fundamentals.next_revenue_estimate` — consensus revenue estimate
- `Fundamentals.earnings[]` — historical releases, each with `date` +
  `eps_estimate` / `eps_reported` / `surprise_pct`

Aggregation: walk the catalog (or a subset by sector / index / watchlist),
fetch each stock's fundamentals (cached 24h), and bucket events by date.

V1 scope: **all scored stocks** (those that already went through the score
service — typically the top-50-by-mkt-cap seed plus whatever the next
batch recompute fills). This naturally limits the set to "stocks the user
cares enough about for us to have computed" without cluttering the calendar
with thousands of tickers most users will never look at.

### Macros (static V1, hardcoded)

A compact, hand-curated list of **high-importance** macro events for the
visible 6-month window. Each entry:
- `date` (ISO date)
- `label` (e.g. "FOMC decision", "CPI release", "NFP")
- `importance` (`"high"` | `"medium"` | `"low"`)
- `region` (`"US"` | `"EU"` | `"UK"` | `"JP"` | etc.)

Hardcoded in a single Python module (`backend/app/services/calendar_macros.py`).
V2 follow-up: integrate FRED / Trading Economics for live macro feed.

Initial seed: ~20 events covering the next 3 months — FOMC (8 per year),
ECB rate decisions, US CPI/PPI, NFP/JOLTS, GDP advance/final, plus a few
heavyweight central-bank meetings (BoE, BoJ).

---

## API

### `GET /api/calendar`

Query params:
- `from` (ISO date, default today)
- `to` (ISO date, default today + 30 days)
- `kinds`: comma-separated subset of `earnings,macro` (default both)
- `importance`: comma-separated `high,medium,low` (filters macros only)

Response:
```json
{
  "from": "2026-05-04",
  "to": "2026-06-04",
  "events": [
    {
      "date": "2026-05-08",
      "kind": "earnings",
      "ticker": "AAPL",
      "name": "Apple Inc.",
      "eps_estimate": 1.43,
      "revenue_estimate": 90250000000,
      "sector": "Technology",
      "market_cap": 2400000000000
    },
    {
      "date": "2026-05-13",
      "kind": "macro",
      "label": "US CPI release",
      "importance": "high",
      "region": "US"
    }
  ]
}
```

Sort: ascending by date, then within a date earnings first (more
actionable), then macros by descending importance.

Caching: the per-stock fundamentals fetches are already cached 24h by
`stock_fundamentals_service`. The aggregator can iterate the catalog
without paying per-stock yfinance roundtrips when the cache is warm.
For cold caches, the aggregator should NOT trigger network — it should
read what's available in cache and let `recompute_all` warm it via
its own schedule.

---

## UI surface

### Layout

Full-width page with three sections stacked top → bottom:

1. **Page header**: "Calendario eventi" title + month-pivot navigation (◀
   prev / **May 2026** / next ▶) + "Oggi" CTA + filter chip strip.
2. **Month grid**: standard 7-col × 5-or-6-row calendar layout. Each cell
   has the date number in the top-left, plus a vertical stack of event
   chips (max 3 visible, "+N altri" expander otherwise).
3. **Event detail panel** (bottom or side, depending on viewport): when
   the user hovers/clicks a cell or chip, show a richer view of that day's
   events with EPS estimates, links to stock detail pages, etc.

### Event chip styling (the design-y bit)

- **Earnings chips**: small ticker pill with the stock logo + ticker text,
  tone-colored by sector (Technology = sky, Financials = amber,
  Healthcare = emerald, etc. — same palette already in `lib/sectorMeta.ts`
  if it exists, otherwise a small inline map).
- **Macro chips**: distinctive — different shape (rounded-square vs
  pill?), different color (importance-tier bg: red for high, orange for
  medium, slate for low), and a small icon (Calendar / TrendingUp / etc.).

### Cell visuals

- **Today's cell**: stronger border + subtle bg tint
- **Weekend cells**: muted bg (no events expected; visually dialed down)
- **Days in adjacent months** (the leading/trailing greys): rendered
  but with low opacity + no event chips (cleaner header/footer rows)

### Interactions

- Click a date cell → expand to show a full list of events for that day
- Click a ticker chip → navigate to `/stocks/{ticker}`
- Hover a chip → small Radix tooltip with EPS estimate / macro label
- Keyboard: arrow keys move focus between cells (a11y bonus)

---

## Implementation plan

Two specialized agents, **sequential**:

### Agent 1 — Backend (`feat(calendar): API + macros`)

1. New `app/services/calendar_macros.py` — hardcoded macro events list +
   helper to filter by date range and importance
2. New `app/services/calendar_service.py` — `get_events(db, from, to,
   kinds, importance)` aggregating earnings (from fundamentals cache)
   + macros
3. New `app/api/calendar.py` router with `GET /api/calendar`
4. New `app/schemas/calendar.py` Pydantic shapes
5. Mount the router in `app/main.py`
6. Tests: stub fundamentals cache, assert aggregation correctness +
   filter handling + range boundaries

### Agent 2 — Frontend (`feat(calendar): designed UI`)

Use the `frontend-design` skill (mounted in this codebase) to create a
distinctive, production-quality month-grid calendar page. Specifically:

1. New `frontend/src/api/calendar.ts` + types
2. New `frontend/src/hooks/useCalendar.ts`
3. New `frontend/src/pages/CalendarPage.tsx` (route added in `App.tsx`)
4. New `frontend/src/components/calendar/*` (CalendarGrid, EventChip,
   DayDetailPanel, MonthNav, etc.)
5. Add `/calendar` to the sidebar nav (Layout.tsx) with a Calendar icon
6. Tone palettes: reuse alert/score tone systems from `lib/alertMeta`
   and `lib/scoreMeta`. Sector palette defined inline.
7. Use the existing Tooltip component (`@/components/ui/tooltip`) for
   chip hovers.

---

## Out of scope V1

- Live macro feed (FRED / Trading Economics integration)
- Per-user customization (which sectors / indices to show)
- Notifications ("alert me 1 day before AAPL earnings")
- Earnings call audio/transcript links
- Add-to-watchlist from the calendar
- ICS export / Google Calendar sync
