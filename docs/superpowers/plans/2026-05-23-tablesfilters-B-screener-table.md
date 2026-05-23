# Tables & Filters — Plan B: screener identity cell + 6 pillar columns

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** In the screener table, format the stock identity as logo + ticker (top) + name (below) — like the alerts table — and drop the separate "Nome" column; then add the 6 individual pillar-score columns (Profittabilità, Sostenibilità, Crescita, Valore, Momentum, Sentiment) to the right of the composite score, sortable.

**Architecture:** The `stock_scores` table already persists all 6 pillars and the search already LEFT-JOINs it. So the backend just surfaces them on the screener row + adds them to the sortable-columns map; the frontend merges the identity cell and renders the 6 columns.

**Tech Stack:** FastAPI/SQLAlchemy + pytest; React/Vite/TS.

**Conventions:** backend tests `cd backend && ./.venv/Scripts/python.exe -m pytest <path> -q`; frontend `cd frontend && npm run build`. Pillar filters + column-hide are Plan C.

**The 6 pillars** (Italian labels via `CATEGORY_LABEL` in `scoreMeta.ts`): profitability=Profittabilità · sustainability=Sostenibilità · growth=Crescita · value=Valore · momentum=Momentum · sentiment=Sentiment.

---

### Task B1: backend — surface the 6 pillars on the screener row + pillar sort

**Files:**
- Modify: `backend/app/services/stock_service.py` (`StockScoreRef`, `SORTABLE_COLUMNS`, `search_stocks`)
- Modify: `backend/app/api/stocks.py` (`StockScoreRefOut` mapping) and `backend/app/schemas/stock.py` (the `StockScoreRefOut` schema)
- Test: `backend/tests/test_stock_service.py` or `test_api_search*`

- [ ] **Step 1: Write the failing test** — seed a stock + a StockScore with distinct pillar values; assert `search_stocks` returns them on the row, and that `sort_by="momentum"` orders correctly.
```python
# add to backend/tests/test_stock_service.py (adapt imports to the file)
from datetime import datetime, timezone
from app.models import Stock, StockScore
from app.services.stock_service import search_stocks, StockFilter


def _seed_scored(db, ticker, **pillars):
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US")
    db.add(s); db.flush()
    db.add(StockScore(stock_id=s.id, composite=pillars.get("composite", 50.0),
                      profitability=pillars.get("profitability"),
                      sustainability=pillars.get("sustainability"),
                      growth=pillars.get("growth"), value=pillars.get("value"),
                      momentum=pillars.get("momentum"), sentiment=pillars.get("sentiment"),
                      risk_tier="moderate", computed_at=datetime.now(timezone.utc), breakdown="{}"))
    db.commit()


def test_search_returns_pillars_and_sorts_by_pillar(db):
    _seed_scored(db, "AAA", momentum=90.0, value=10.0)
    _seed_scored(db, "BBB", momentum=10.0, value=90.0)
    page = search_stocks(db, StockFilter(sort_by="momentum", sort_dir="desc"))
    assert [i.stock.ticker for i in page.items[:2]] == ["AAA", "BBB"]
    assert page.items[0].score.momentum == 90.0
```
(Adapt `StockFilter(...)` to its real constructor — it's a dataclass with `sort_by`/`sort_dir`/`risk_tiers`/`min_score`/etc.)

- [ ] **Step 2: Run, verify fail** — `StockScoreRef` has no `momentum` (AttributeError) and "momentum" not in SORTABLE_COLUMNS.

- [ ] **Step 3: Implement**
- `SORTABLE_COLUMNS` (stock_service.py): add the 6 entries — `"profitability": StockScore.profitability, "sustainability": StockScore.sustainability, "growth": StockScore.growth, "value": StockScore.value, "momentum": StockScore.momentum, "sentiment": StockScore.sentiment`.
- `StockScoreRef` dataclass: add `profitability/sustainability/growth/value/momentum/sentiment: float | None = None`.
- `search_stocks`: where it builds each row's `StockScoreRef`, populate the 6 from the joined `StockScore` row (the query already LEFT-JOINs `stock_scores`; read the columns — if the query selects the ORM `StockScore` or specific columns, ensure these 6 are available, then map them). Unscored stocks → all None.
- `app/schemas/stock.py` `StockScoreRefOut`: add the 6 `float | None` fields. `app/api/stocks.py`: in the response build (currently `StockScoreRefOut(composite=item.score.composite, risk_tier=item.score.risk_tier)`), also pass the 6 pillars from `item.score`.

- [ ] **Step 4: Run + commit** — targeted + full suite green.
```bash
git add backend/app/services/stock_service.py backend/app/api/stocks.py backend/app/schemas/stock.py backend/tests/
git commit -m "feat(screener): surface 6 pillar sub-scores on the row + pillar sort"
```

---

### Task B2: frontend — identity cell merge + drop Nome + 6 pillar columns

**Files:**
- Modify: `frontend/src/api/types.ts` (`StockSearchItem.score`)
- Modify: `frontend/src/components/stocks/StockBrowserTable.tsx`
- Test: `cd frontend && npm run build`

- [ ] **Step 1: Types** — extend `StockSearchItem.score` (currently `{composite, risk_tier}`) with `profitability/sustainability/growth/value/momentum/sentiment: number | null`.

- [ ] **Step 2: StockBrowserTable** (it has a mobile + a desktop variant — update BOTH):
- **Identity cell:** render `<StockLogo ticker={s.ticker} size="sm" />` + a stacked block: ticker (top, bold, `Link` to `/stocks/{ticker}`) and company name (below, muted, truncated) — mirror the alerts table "Titolo" cell. **Remove the standalone "Nome" column**: delete the `{ key: "name", label: "Nome" }` entry from the sortable-columns list AND its `<SortableHeader column="name" .../>` header AND the separate name `<TableCell>`. The identity column header can stay the ticker/search header (sort by `ticker`).
- **6 pillar columns**, to the RIGHT of the composite score column. For each pillar in order [profitability, sustainability, growth, value, momentum, sentiment]:
  - Header: `<SortableHeader column="<pillar>" label="<short label>" .../>` (use compact labels to fit: e.g. "Profitt." / "Sosten." / "Cresc." / "Valore" / "Mom." / "Sent." — or the full `CATEGORY_LABEL` if space allows; pick compact for the desktop table).
  - Cell: the pillar value `item.score.<pillar>` shown as a number (e.g. `.toFixed(0)`), colored with `scoreColor(value)` (import from `scoreMeta`), `—` when null. Right-aligned, tabular-nums, `text-xs`.
- Keep the existing composite column. The pillar columns are desktop-table; on the mobile variant they'd overflow — show them only on desktop (or a condensed subset on mobile). Decision: pillars on the DESKTOP table only; the mobile card keeps composite (note this in the report).

- [ ] **Step 3: Build + commit**
`cd frontend && npm run build` → clean (rebuilds dist).
```bash
git add frontend/src/api/types.ts frontend/src/components/stocks/StockBrowserTable.tsx
git commit -m "feat(screener-ui): logo+ticker/name identity cell + 6 pillar columns"
```

---

## Self-review notes
- Data already persisted (`StockScore` has the 6 pillars) + JOIN already present → backend just surfaces + sorts. ✓
- Identity cell mirrors the alerts "Titolo" pattern; standalone Nome column removed (freed space → pillar columns). ✓
- 6 pillar columns sortable via the existing `SortableHeader` + the new SORTABLE_COLUMNS keys; colored via `scoreColor`. ✓
- Pillars desktop-only (mobile would overflow). ✓
- Pillar/composite FILTERS + right-click column-hide → Plan C. ✓
