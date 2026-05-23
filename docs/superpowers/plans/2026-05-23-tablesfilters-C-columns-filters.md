# Tables & Filters — Plan C: column show/hide + enriched filters

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** (1) Right-click a table header to show/hide columns (persisted), on both the alerts and screener tables. (2) Enrich the filters: screener gets composite-range + per-pillar minimums; alerts get signal-kind + tone + confidence.

**Architecture:** Backend adds the new filter params (alerts tone/confidence via snapshot `json_extract`; screener composite-max + 6 pillar mins on `StockFilter`). Frontend adds a reusable `useColumnVisibility` hook (localStorage) + a `ColumnVisibilityMenu` (dropdown-menu) opened on header right-click, applied to both tables, plus the enriched filter UIs.

**Tech Stack:** FastAPI/SQLAlchemy + pytest; React/Vite/TS (shadcn `dropdown-menu` + `popover` exist).

**Conventions:** backend tests `cd backend && ./.venv/Scripts/python.exe -m pytest <path> -q`; frontend `cd frontend && npm run build`.

---

### Task C1: backend — alerts tone/confidence filters + screener composite-range/pillar filters

**Files:**
- Modify: `backend/app/services/alert_service.py` (`list_alerts`), `backend/app/api/alerts.py`
- Modify: `backend/app/services/stock_service.py` (`StockFilter`, `search_stocks`), `backend/app/api/stocks.py`
- Test: `backend/tests/test_alert_service.py`, `backend/tests/test_stock_service.py`

- [ ] **Step 1: Write the failing tests**
  - alerts: seed alerts with tones bull/bear + confidences; `list_alerts(tone="bull")` returns only bull; `list_alerts(confidence_min=70)` returns only conf>=70.
  - screener: `search_stocks(StockFilter(momentum_min=80))` returns only stocks with momentum>=80; `score_max` caps composite.
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement**
  - `list_alerts`: add `tone: str | None = None` → `stmt.where(func.json_extract(Alert.snapshot, "$.tone") == tone)`; `confidence_min: float | None = None` → `stmt.where(func.cast(func.json_extract(Alert.snapshot, "$.confidence"), Float) >= confidence_min)`. Wire both as query params in `api/alerts.py` (validate tone in {"bull","bear"}; confidence_min in [0,100]).
  - `StockFilter` (stock_service): add `score_max: float | None = None` and the 6 pillar minimums `profitability_min/sustainability_min/growth_min/value_min/momentum_min/sentiment_min: float | None = None`. In `search_stocks` add the corresponding `where` clauses (`StockScore.<pillar> >= <pillar>_min`, `StockScore.composite <= score_max`). Wire as query params in `api/stocks.py` `search` (each in [0,100]).
- [ ] **Step 4: Run + commit**
```bash
git add backend/app/services/alert_service.py backend/app/api/alerts.py backend/app/services/stock_service.py backend/app/api/stocks.py backend/tests/
git commit -m "feat(filters): alerts tone/confidence + screener composite-range/pillar filters (backend)"
```

---

### Task C2: frontend — right-click column show/hide (both tables)

**Files:**
- Create: `frontend/src/hooks/useColumnVisibility.ts`
- Create: `frontend/src/components/ui/column-visibility-menu.tsx`
- Modify: `frontend/src/components/AlertsTable.tsx`, `frontend/src/components/stocks/StockBrowserTable.tsx`
- Test: `cd frontend && npm run build`

- [ ] **Step 1: `useColumnVisibility(tableId, columns)` hook**
```ts
// frontend/src/hooks/useColumnVisibility.ts
import { useCallback, useEffect, useState } from "react";

export interface ColumnDef { id: string; label: string; }

/** Per-table column show/hide, persisted in localStorage. `columns` is the
 *  full set of toggleable columns; hidden ids are stored under
 *  `colvis:<tableId>`. Returns helpers to query + toggle visibility. */
export function useColumnVisibility(tableId: string, columns: ColumnDef[]) {
  const key = `colvis:${tableId}`;
  const [hidden, setHidden] = useState<Set<string>>(() => {
    try {
      const raw = localStorage.getItem(key);
      return new Set<string>(raw ? JSON.parse(raw) : []);
    } catch {
      return new Set();
    }
  });
  useEffect(() => {
    try { localStorage.setItem(key, JSON.stringify([...hidden])); } catch { /* ignore */ }
  }, [key, hidden]);
  const toggle = useCallback((id: string) => {
    setHidden((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);
  const isVisible = useCallback((id: string) => !hidden.has(id), [hidden]);
  return { columns, isVisible, toggle, hidden };
}
```

- [ ] **Step 2: `ColumnVisibilityMenu`** — a dropdown-menu (shadcn `@/components/ui/dropdown-menu`) of checkbox items, one per column, bound to `toggle`/`isVisible`. It is opened by RIGHT-CLICK on the table header: the table wraps its `<TableHeader>` (or the header `<TableRow>`) with `onContextMenu={(e)=>{e.preventDefault(); openMenu(e.clientX,e.clientY);}}`. Implement the menu as a controlled `DropdownMenu` positioned at the cursor (a 0-size trigger placed at the click coords, or a `DropdownMenuContent` with a manual anchor). Each item: `DropdownMenuCheckboxItem checked={isVisible(col.id)} onCheckedChange={()=>toggle(col.id)}`. Keep it simple + reusable (props: `columns`, `isVisible`, `toggle`, open state).

- [ ] **Step 3: Wire into both tables**
  - `AlertsTable`: define the toggleable columns (`data_segnale`, `rilevato`, `titolo`, `regola`, `catena`, `tono`, `prezzo`, `confidenza` — checkbox + non-embedded only). Use `useColumnVisibility("alerts", COLS)`; gate each column's `<TableHead>` AND its body `<TableCell>` behind `isVisible(id)`; recompute `colSpan` from the visible count. Right-click the header opens the menu.
  - `StockBrowserTable` (desktop): same — toggleable columns include the 6 pillars + score + the meta columns; `useColumnVisibility("screener", COLS)`; gate header + body cells; right-click opens the menu. (Keep the identity/ticker column always-on, non-hideable, so a row is never anonymous.)
  - Persisting per `tableId` means each table remembers its own hidden set.

- [ ] **Step 4: Build + commit**
`cd frontend && npm run build` → clean.
```bash
git add frontend/src/hooks/useColumnVisibility.ts frontend/src/components/ui/column-visibility-menu.tsx frontend/src/components/AlertsTable.tsx frontend/src/components/stocks/StockBrowserTable.tsx
git commit -m "feat(tables): right-click header to show/hide columns (persisted)"
```

---

### Task C3: frontend — enriched filter UIs

**Files:**
- Modify: `frontend/src/components/AlertFilters.tsx`, `frontend/src/api/alerts.ts` (params)
- Modify: `frontend/src/components/stocks/StockFiltersCard.tsx`, `frontend/src/api/stocks.ts` (params) + `frontend/src/pages/StocksBrowserPage.tsx` (filter state)
- Test: `cd frontend && npm run build`

- [ ] **Step 1: AlertFilters** — add controls (wired to `AlertListParams`, which gains `tone?`, `confidence_min?`, and reuse the existing `rule_kind?`):
  - **Tipo segnale**: a Select of the signal kinds (`signal:volume_breakout`, …, the 17 — derive the list from a small constant, label via `SIGNAL_META`/friendly names) → sets `rule_kind`.
  - **Tono**: a Select Tutti / Rialzista (bull) / Ribassista (bear) → sets `tone`.
  - **Confidenza minima**: a small number input or slider 0-100 → sets `confidence_min`.
  - Add "active filter" chips for each (consistent with the existing chip pattern) so the user can clear them.
- [ ] **Step 2: StockFiltersCard** — add (wired to the screener filter state + `api/stocks` search params, which gain `score_max?` + `<pillar>_min?`):
  - **Composite**: a min/max range (the existing `min_score` + a new `score_max`).
  - **Per-pillar minimums**: 6 compact number inputs/sliders (Profittabilità … Sentiment) → `<pillar>_min`. Group them under a "Punteggi pillar" sub-section so the card stays scannable.
- [ ] **Step 3: Wire params** — `api/alerts.ts` `AlertListParams` + `toQuery`: add `tone`, `confidence_min`. `api/stocks.ts` search params + the screener page filter state: add `score_max` + the 6 `<pillar>_min`.
- [ ] **Step 4: Build + commit**
`cd frontend && npm run build` → clean (rebuilds dist).
```bash
git add frontend/src/components/AlertFilters.tsx frontend/src/api/alerts.ts frontend/src/components/stocks/StockFiltersCard.tsx frontend/src/api/stocks.ts frontend/src/pages/StocksBrowserPage.tsx
git commit -m "feat(filters-ui): alerts kind/tone/confidence + screener composite-range/pillar filters"
```

---

## Self-review notes
- Backend filters reuse the same `json_extract` (alerts tone/confidence) + the existing `StockScore` join (screener pillars) as the sort work — consistent. ✓
- Column visibility is a reusable hook + menu, persisted per-table; the identity column stays non-hideable so rows are never anonymous. ✓
- Filter UIs reuse the existing Select / chip / MultiSelect patterns; alerts kind filter reuses the already-present `rule_kind` param (signal kinds). ✓
- After C: hard-reload; the tables & filters batch is complete. The annotated-chart feature (FOLLOWUPS) resumes next.
