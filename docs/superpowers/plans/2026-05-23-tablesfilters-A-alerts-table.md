# Tables & Filters — Plan A: sortable alerts table + year + event-chain column

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** Make the alerts table sortable by column (server-side, correct across pagination), restore the year on the "Rilevato" date, and add a compact "Catena" (event-chain) column right of "Regola".

**Architecture:** Backend adds `sort_by`/`sort_dir` to the alerts list (confidence/tone read from the snapshot JSON via `json_extract`). Frontend wires sortable headers (same pattern as the screener/breadth tables) + the new column + the date format.

**Tech Stack:** FastAPI/SQLAlchemy (SQLite) + pytest; React/Vite/TS.

**Conventions:** backend tests `cd backend && ./.venv/Scripts/python.exe -m pytest <path> -q`; frontend `cd frontend && npm run build`. After FE changes rebuild dist.

**Scope note:** tone/confidence FILTERS + the right-click column-hide are Plan C; the screener is Plan B. Plan A is the alerts TABLE (sort + year + chain) only.

---

### Task A1: backend — sort_by/sort_dir on the alerts list

**Files:**
- Modify: `backend/app/services/alert_service.py` (`list_alerts`)
- Modify: `backend/app/api/alerts.py` (the list endpoint params)
- Test: `backend/tests/test_alert_service.py` (or test_api_alerts.py)

- [ ] **Step 1: Write the failing test** — sorting by trigger_price asc/desc and by confidence orders rows correctly; an invalid sort_by is rejected. Seed 3 signal alerts with different trigger_price + snapshot confidence; assert order.
```python
# add to backend/tests/test_alert_service.py
from datetime import date, datetime, timezone
import json
from app.models import Alert, Stock
from app.services.alert_service import list_alerts


def _seed(db, ticker, price, conf):
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US")
    db.add(s); db.flush()
    db.add(Alert(stock_id=s.id, trigger_price=price, signal_date=date(2026, 5, 1),
                 signal_name="volume_breakout",
                 snapshot=json.dumps({"tone": "bull", "confidence": conf, "chain": []})))
    db.commit()


def test_list_alerts_sort_by_price_and_confidence(db):
    _seed(db, "AAA", 10.0, 90)
    _seed(db, "BBB", 30.0, 50)
    _seed(db, "CCC", 20.0, 70)
    items, _total, _more = list_alerts(db, sort_by="trigger_price", sort_dir="asc")
    assert [round(i["trigger_price"], 0) for i in items] == [10, 20, 30]
    items, _, _ = list_alerts(db, sort_by="confidence", sort_dir="desc")
    assert [i["ticker"] for i in items] == ["AAA", "CCC", "BBB"]
```

- [ ] **Step 2: Run, verify fail** — `list_alerts` has no `sort_by` kwarg (TypeError).

- [ ] **Step 3: Implement** — add `sort_by: str = "triggered_at"`, `sort_dir: str = "desc"` to `list_alerts`. Build a sortable-columns map and apply `order_by` before limit/offset. confidence/tone come from the snapshot JSON:
```python
from sqlalchemy import func, asc, desc

_SORTABLE = {
    "triggered_at": Alert.triggered_at,
    "signal_date": Alert.signal_date,
    "ticker": Stock.ticker,
    "trigger_price": Alert.trigger_price,
    "kind": Alert.signal_name,
    "confidence": func.cast(func.json_extract(Alert.snapshot, "$.confidence"), __import__("sqlalchemy").Float),
    "tone": func.json_extract(Alert.snapshot, "$.tone"),
}
# inside list_alerts, after filters, before limit/offset:
col = _SORTABLE.get(sort_by, Alert.triggered_at)
direction = asc if sort_dir == "asc" else desc
stmt = stmt.order_by(direction(col).nullslast(), Alert.id.desc())
```
(Keep the existing default ordering = triggered_at desc when no sort given. The `Stock.ticker` sort relies on the existing join to Stock for ticker/name — confirm the list query already joins Stock; it does, for the ticker/name columns.)
In `app/api/alerts.py` add `sort_by: str = "triggered_at"` and `sort_dir: str = "desc"` query params to the list endpoint, validate `sort_dir in ("asc","desc")` (422 otherwise) and `sort_by` in the allowlist keys (422 otherwise), and pass them to `list_alerts`.

- [ ] **Step 4: Run + commit** — targeted test green; full suite green.
```bash
git add backend/app/services/alert_service.py backend/app/api/alerts.py backend/tests/
git commit -m "feat(alerts): server-side sort_by/sort_dir (incl. confidence/tone via json_extract)"
```

---

### Task A2: frontend — sortable headers + year + Catena column

**Files:**
- Modify: `frontend/src/api/alerts.ts` (`AlertListParams` + `toQuery`)
- Modify: `frontend/src/components/AlertsTable.tsx`
- Modify: `frontend/src/pages/AlertsPage.tsx`
- Test: `cd frontend && npm run build`

- [ ] **Step 1: API params** — in `api/alerts.ts`, add `sort_by?: string;` and `sort_dir?: "asc" | "desc";` to `AlertListParams`, and include them in `toQuery` when present.

- [ ] **Step 2: AlertsTable sortable headers + year + Catena.**
- Add props: `sortBy: string; sortDir: "asc" | "desc"; onSort: (col: string) => void;` (only used in non-embedded mode).
- Add a small local `SortableHeader` (replicate the pattern used in `StockBrowserTable`/`BreadthMatrixTable`: a clickable `TableHead` showing the label + an up/down chevron when active; clicking toggles dir or switches column). Apply it to: Data segnale (`signal_date`), Rilevato (`triggered_at`), Titolo (`ticker`), Prezzo (`trigger_price`), Confidenza (`confidence`). (Tono/Regola can stay non-sortable, or sort kind by `kind` — optional.)
- **Rilevato with year:** change the Rilevato cell from `formatDayMonth(a.triggered_at)` back to `formatShortDate(a.triggered_at)` (DD/MM/YY, still no time). Update the import (drop `formatDayMonth`, add `formatShortDate` — note `formatShortDate` is already imported for signal_date, so just remove the now-unused `formatDayMonth`).
- **Catena column** (right of Regola): a new `<TableHead>Catena</TableHead>` (non-embedded) + a cell rendering a compact chain summary:
  ```tsx
  {!embedded && (
    <TableCell className="max-w-[260px]">
      {(() => {
        const chain = (a.snapshot as Record<string, unknown> | undefined)?.chain;
        if (!Array.isArray(chain) || chain.length === 0) {
          return <span className="text-muted-foreground">—</span>;
        }
        const labels = (chain as { label?: string }[]).map((s) => s.label ?? "").filter(Boolean);
        const summary = labels.join(" → ");
        return (
          <span className="text-xs text-muted-foreground truncate block" title={summary}>
            {summary}
          </span>
        );
      })()}
    </TableCell>
  )}
  ```
  Place this `<TableCell>` immediately AFTER the Regola cell (the `<TableCell><AlertKindChip/></TableCell>`), and the matching `<TableHead>` after the "Regola" head. Bump `colSpan` non-embedded 8 → 9.

- [ ] **Step 3: AlertsPage wiring** — hold sort state `const [sortBy,setSortBy]=useState("triggered_at"); const [sortDir,setSortDir]=useState<"asc"|"desc">("desc");`. Pass `sort_by: sortBy, sort_dir: sortDir` into `useAlertsList({ ...filters, sort_by, sort_dir, offset })`. Pass `sortBy/sortDir/onSort` to `<AlertsTable>`. `onSort(col)` = if same col toggle dir else set col + default "desc" (or "asc" for ticker). Reset `page` to 0 on sort change.

- [ ] **Step 4: Build + commit**
`cd frontend && npm run build` → clean (rebuilds dist).
```bash
git add frontend/src/api/alerts.ts frontend/src/components/AlertsTable.tsx frontend/src/pages/AlertsPage.tsx
git commit -m "feat(alerts-ui): sortable columns + year on Rilevato + Catena column"
```

---

## Self-review notes
- Server-side sort (correct across pagination); confidence/tone via SQLite `json_extract` (the only place those live). ✓
- Reuses the established SortableHeader pattern (local copy, like the other 2 tables — no unrelated refactor). ✓
- Rilevato year restored via the already-imported `formatShortDate`. ✓
- Catena = compact arrow-joined labels + full on hover (the user's "inline column" choice). colSpan 8→9. ✓
- Tone/confidence FILTERS + column-hide deferred to Plan C; screener to Plan B. ✓
