# Plan #1 — Earnings pre/after-market icon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render ☀ (pre-market) / ☾ (after-market) icon next to the "prossima" row in the FundamentalsCard quarterly table on Stock Detail.

**Architecture:** Backend extracts the existing `_classify_session_timing` helper into a shared module (`earnings_session_timing.py`), exposes a new `next_earnings_when` field on the `FundamentalsOut` API response computed via that helper, and the frontend renders the same glyph used by the calendar's `EventChip`.

**Tech Stack:** FastAPI + SQLAlchemy backend, pytest for tests, React + TypeScript frontend (no test framework wired — verify via `npm run build` + manual smoke).

---

## File Structure

**Created:**
- `backend/app/services/earnings_session_timing.py` — shared classifier, ~30 LOC
- `backend/tests/test_earnings_session_timing.py` — unit tests for the classifier
- `backend/tests/test_stock_detail_next_earnings_when.py` — integration test on the API endpoint

**Modified:**
- `backend/app/services/calendar_service.py` — drop the inline `_classify_session_timing`, import from the new module
- `backend/app/schemas/stock_detail.py` — add `next_earnings_when` field to `FundamentalsOut`
- `backend/app/api/stocks.py` — populate `next_earnings_when` in `get_stock_fundamentals`
- `frontend/src/api/types.ts` — add `next_earnings_when` to `Fundamentals` interface
- `frontend/src/components/stock/FundamentalsCard.tsx` — pass prop into `QuarterlyTabBody` and render glyph in the "prossima" row

---

### Task 1: Extract `classify_session_timing` to shared module

**Files:**
- Create: `backend/app/services/earnings_session_timing.py`
- Test: `backend/tests/test_earnings_session_timing.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_earnings_session_timing.py`:

```python
"""Tests for earnings_session_timing.classify_session_timing.

The function maps (UTC HH:MM, country) → "pre" | "after" | None.
US session: 14:30-21:00 UTC. Anything < 14:30 = pre, ≥ 21:00 = after,
mid-session prints (extremely rare in practice) = None.
Non-US countries currently fall through to None — no session model yet.
"""
from app.services.earnings_session_timing import classify_session_timing


def test_us_pre_market_classified_as_pre() -> None:
    assert classify_session_timing("13:30", "US") == "pre"


def test_us_just_before_open_classified_as_pre() -> None:
    # 14:29 is still pre — open is at 14:30
    assert classify_session_timing("14:29", "US") == "pre"


def test_us_at_open_returns_none() -> None:
    # 14:30 is the open boundary — classified as in-session (None)
    assert classify_session_timing("14:30", "US") is None


def test_us_mid_session_returns_none() -> None:
    assert classify_session_timing("17:00", "US") is None


def test_us_at_close_classified_as_after() -> None:
    # 21:00 is the close boundary — earnings at exactly 21:00 are after
    assert classify_session_timing("21:00", "US") == "after"


def test_us_after_market_classified_as_after() -> None:
    assert classify_session_timing("22:30", "US") == "after"


def test_none_time_returns_none() -> None:
    assert classify_session_timing(None, "US") is None


def test_none_country_returns_none() -> None:
    assert classify_session_timing("13:30", None) is None


def test_unparseable_time_returns_none() -> None:
    assert classify_session_timing("not-a-time", "US") is None


def test_non_us_country_returns_none_for_now() -> None:
    # Future work: model UK/EU sessions. For now we return None to avoid
    # showing a wrong icon.
    assert classify_session_timing("17:00", "GB") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_earnings_session_timing.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.earnings_session_timing'`.

- [ ] **Step 3: Create the new module with the extracted function**

Create `backend/app/services/earnings_session_timing.py`:

```python
"""Country-aware classifier for earnings release timing.

Given a UTC HH:MM string for when an earnings was released and the listing
country, return "pre" | "after" | None to drive the sun/moon icon in the
calendar and stock-detail UIs.

This logic was originally inlined in `calendar_service._classify_session_timing`
— extracted here so the stock-detail API can reuse it without importing
calendar_service (which itself imports stock_fundamentals_service, creating
a dependency hairball).

The thresholds are deliberately wide (using winter-DST UTC offsets) so the
icon is informational rather than authoritative:
  - US: 14:30 UTC = NYSE/NASDAQ open, 21:00 UTC = close.
    Times < 14:30 → "pre"; times ≥ 21:00 → "after"; mid-session → None.
  - Other countries: currently None (no session model yet — we'd rather
    show no icon than a wrong one).
"""
from typing import Literal


def classify_session_timing(
    time_utc: str | None, country: str | None
) -> Literal["pre", "after"] | None:
    """Return "pre" | "after" | None for the given earnings release timestamp."""
    if not time_utc or not country:
        return None
    try:
        h, m = time_utc.split(":")
        minutes = int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None
    if country == "US":
        # 14:30 UTC = 870 minutes (NYSE open); 21:00 UTC = 1260 minutes (close)
        if minutes < 14 * 60 + 30:
            return "pre"
        if minutes >= 21 * 60:
            return "after"
        return None
    # Other markets: heuristic only — we don't model their sessions yet.
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_earnings_session_timing.py -v`

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/earnings_session_timing.py backend/tests/test_earnings_session_timing.py
git commit -m "earnings: extract session-timing classifier to shared module

Pulled out of calendar_service._classify_session_timing so the stock-detail
API can reuse it without importing calendar_service. Behavior unchanged;
adds 10 unit tests covering US session boundaries and edge cases."
```

---

### Task 2: Replace inline definition in `calendar_service.py`

**Files:**
- Modify: `backend/app/services/calendar_service.py:237-264` (remove `_classify_session_timing`), `backend/app/services/calendar_service.py:196` (update call site)

- [ ] **Step 1: Run existing calendar tests to capture green baseline**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -k calendar -q`

Expected: all pass (existing baseline).

- [ ] **Step 2: Replace the inline function with an import**

In `backend/app/services/calendar_service.py`:

1. Near the top of the file (with the other imports), add:
   ```python
   from app.services.earnings_session_timing import classify_session_timing
   ```

2. At the call site (currently L196):
   ```python
   earnings_when=_classify_session_timing(time_utc, stock.country),
   ```
   change to:
   ```python
   earnings_when=classify_session_timing(time_utc, stock.country),
   ```

3. Delete the entire `def _classify_session_timing(...)` function block (currently L237-L264, including its docstring).

- [ ] **Step 3: Run calendar tests to verify nothing broke**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -k calendar -q`

Expected: all pass — same count as in Step 1.

- [ ] **Step 4: Run full backend suite to catch any other importer**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -x -q`

Expected: 281+ pass, 0 fail.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/calendar_service.py
git commit -m "calendar: switch to shared classify_session_timing import

Drops the inline _classify_session_timing definition now that
earnings_session_timing.classify_session_timing exists. Pure refactor —
no behavior change."
```

---

### Task 3: Add `next_earnings_when` to `FundamentalsOut` schema

**Files:**
- Modify: `backend/app/schemas/stock_detail.py:212-220` (add field to `FundamentalsOut`)

- [ ] **Step 1: Add the field to the schema**

In `backend/app/schemas/stock_detail.py`, find `FundamentalsOut` (~L212). Locate the line `next_earnings_date: str | None = None` (~L217). Immediately AFTER it, add:

```python
    # When the next earnings is released relative to the trading session.
    # "pre" → ☀ icon (released before market open),
    # "after" → ☾ icon (released after market close),
    # None → no icon (mid-session release, non-US country, or unknown).
    # Computed via earnings_session_timing.classify_session_timing.
    next_earnings_when: Literal["pre", "after"] | None = None
```

Also confirm that `Literal` is imported at the top of the file. If not, add `from typing import Literal` near the existing typing imports.

- [ ] **Step 2: Verify import resolution**

Run: `cd backend && ./.venv/Scripts/python.exe -c "from app.schemas.stock_detail import FundamentalsOut; print(FundamentalsOut.model_fields['next_earnings_when'])"`

Expected: prints a FieldInfo describing the new field, no ImportError.

- [ ] **Step 3: Commit (will commit jointly with Task 4)**

Hold the commit — Task 4 populates the field. Combining the schema add and the populator into one commit keeps the diff coherent.

---

### Task 4: Populate `next_earnings_when` in `get_stock_fundamentals`

**Files:**
- Modify: `backend/app/api/stocks.py:253-289` (add to `FundamentalsOut(...)` construction)
- Test: `backend/tests/test_stock_detail_next_earnings_when.py`

- [ ] **Step 1: Write the failing integration test**

Create `backend/tests/test_stock_detail_next_earnings_when.py`:

```python
"""Verify GET /api/stocks/{ticker}/fundamentals exposes next_earnings_when
derived from the cached fundamentals' next_earnings_time_utc + stock country."""
from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.db import SessionLocal
from app.models import Stock
from app.services.stock_fundamentals_service import (
    FundamentalsData, MicroData, CompanyProfile, AnalystPriceTarget,
)


@pytest.fixture
def aapl_us_after_market(db_session) -> Stock:
    """A US stock with cached fundamentals reporting at 22:00 UTC (after-close)."""
    stock = Stock(ticker="AAPL_TEST", name="Apple Test", country="US",
                  exchange="NASDAQ", sector="Tech", currency="USD")
    db_session.add(stock)
    db_session.commit()
    return stock


def _make_fundamentals(time_utc: str | None) -> FundamentalsData:
    """Build a minimal FundamentalsData with the given next_earnings_time_utc."""
    return FundamentalsData(
        ticker="AAPL_TEST",
        next_earnings_date="2026-07-31",
        next_earnings_time_utc=time_utc,
        next_eps_estimate=2.10,
        next_revenue_estimate=95_000_000_000.0,
        micro=MicroData(),
        profile=CompanyProfile(),
        price_target=AnalystPriceTarget(),
    )


def test_after_market_us_stock_returns_after(
    aapl_us_after_market, auth_client: TestClient,
) -> None:
    with patch(
        "app.api.stocks.stock_fundamentals_service.get_fundamentals",
        return_value=_make_fundamentals("22:00"),
    ):
        r = auth_client.get(f"/api/stocks/{aapl_us_after_market.ticker}/fundamentals")
    assert r.status_code == 200
    assert r.json()["next_earnings_when"] == "after"


def test_pre_market_us_stock_returns_pre(
    aapl_us_after_market, auth_client: TestClient,
) -> None:
    with patch(
        "app.api.stocks.stock_fundamentals_service.get_fundamentals",
        return_value=_make_fundamentals("13:00"),
    ):
        r = auth_client.get(f"/api/stocks/{aapl_us_after_market.ticker}/fundamentals")
    assert r.status_code == 200
    assert r.json()["next_earnings_when"] == "pre"


def test_no_time_returns_null(
    aapl_us_after_market, auth_client: TestClient,
) -> None:
    with patch(
        "app.api.stocks.stock_fundamentals_service.get_fundamentals",
        return_value=_make_fundamentals(None),
    ):
        r = auth_client.get(f"/api/stocks/{aapl_us_after_market.ticker}/fundamentals")
    assert r.status_code == 200
    assert r.json()["next_earnings_when"] is None
```

Note: the `auth_client` and `db_session` fixtures already exist in `backend/tests/conftest.py`. If the fixture names differ, look at conftest and adjust this test before running.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_stock_detail_next_earnings_when.py -v`

Expected: 3 FAIL because the API doesn't include `next_earnings_when` in the response yet (or KeyError on `r.json()["next_earnings_when"]`).

- [ ] **Step 3: Wire up the field in the API**

In `backend/app/api/stocks.py`, find `get_stock_fundamentals` (L253). Add the import at the top of the file:

```python
from app.services.earnings_session_timing import classify_session_timing
```

In the function body, immediately before the `return FundamentalsOut(...)` line (~L274), add:

```python
    next_earnings_when = classify_session_timing(
        f.next_earnings_time_utc, stock.country
    )
```

Then in the `FundamentalsOut(...)` constructor, after `next_earnings_date=f.next_earnings_date,` add:

```python
        next_earnings_when=next_earnings_when,
```

- [ ] **Step 4: Run integration test to verify it passes**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_stock_detail_next_earnings_when.py -v`

Expected: 3 passed.

- [ ] **Step 5: Run full backend suite**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -x -q`

Expected: 284+ pass (281 existing + 10 from Task 1 + 3 from Task 4).

- [ ] **Step 6: Commit (combines Task 3 + Task 4)**

```bash
git add backend/app/schemas/stock_detail.py backend/app/api/stocks.py backend/tests/test_stock_detail_next_earnings_when.py
git commit -m "stocks: expose next_earnings_when on /fundamentals endpoint

Computed via the shared classify_session_timing helper. Returns 'pre' /
'after' / null based on next_earnings_time_utc + stock.country. Used by
the frontend to render the sun/moon glyph in the QuarterlyTabBody
'prossima' row."
```

---

### Task 5: Add `next_earnings_when` to frontend `Fundamentals` type

**Files:**
- Modify: `frontend/src/api/types.ts:685-...` (`Fundamentals` interface)

- [ ] **Step 1: Add the field**

In `frontend/src/api/types.ts`, find `export interface Fundamentals {` (~L685). Locate the line `next_earnings_date: string | null;` (~L690). Immediately AFTER it, add:

```typescript
  /** When the next earnings is released relative to the session.
   *  "pre" → render ☀ glyph; "after" → ☾; null → no glyph.
   *  Computed server-side from yfinance UTC time + listing country.
   *  Currently populated only for US stocks; non-US returns null. */
  next_earnings_when?: "pre" | "after" | null;
```

- [ ] **Step 2: Verify typecheck**

Run: `cd frontend && npx tsc -b`

Expected: no errors.

- [ ] **Step 3: Hold the commit**

Combined with Task 6 below.

---

### Task 6: Render glyph in QuarterlyTabBody "prossima" row

**Files:**
- Modify: `frontend/src/components/stock/FundamentalsCard.tsx:307-315` (add prop), `frontend/src/components/stock/FundamentalsCard.tsx:395-404` (render glyph), `frontend/src/components/stock/FundamentalsCard.tsx:594-596` (pass prop from parent)

- [ ] **Step 1: Add the prop to `QuarterlyTabBody`**

In `FundamentalsCard.tsx`, find `function QuarterlyTabBody({` (~L307). Update the destructured params and the type annotation:

```typescript
function QuarterlyTabBody({
  quarterly, earnings, nextEarningsDate, nextEarningsWhen, nextEpsEstimate, nextRevenueEstimate,
}: {
  quarterly: FundamentalsQuarterly[];
  earnings: FundamentalsEarnings[];
  nextEarningsDate: string | null;
  nextEarningsWhen: "pre" | "after" | null;
  nextEpsEstimate: number | null;
  nextRevenueEstimate: number | null;
}) {
```

- [ ] **Step 2: Render the glyph in the "prossima" row**

Find the row rendering block (~L395-L404 — the `<tr>` with `bg-blue-50/60 dark:bg-blue-950/20`). Inside the first `<td>`, AFTER the `</span>` that contains `{shortDate(nextEarningsDate!)}` and BEFORE the `<span>` containing `prossima`, add:

```tsx
                  {nextEarningsWhen === "pre" && (
                    <span
                      className="ml-1 text-[11px] leading-none shrink-0 text-amber-500"
                      title="Pre-market: earnings rilasciati prima dell'apertura della sessione"
                      aria-label="pre-market"
                    >
                      ☀
                    </span>
                  )}
                  {nextEarningsWhen === "after" && (
                    <span
                      className="ml-1 text-[11px] leading-none shrink-0 opacity-80"
                      title="After-market: earnings rilasciati dopo la chiusura della sessione"
                      aria-label="after-market"
                    >
                      ☾
                    </span>
                  )}
```

(The `text-amber-500` keeps the sun visually warm; `opacity-80` for the moon mirrors the calendar's EventChip styling at L120.)

- [ ] **Step 3: Pass the prop from the parent**

Find the `<QuarterlyTabBody ...` invocation (~L591-L597 — inside the `effective === "quarterly" && hasQuarterly` branch). Add the new prop:

```tsx
            <QuarterlyTabBody
              quarterly={f.quarterly}
              earnings={f.earnings}
              nextEarningsDate={f.next_earnings_date}
              nextEarningsWhen={f.next_earnings_when ?? null}
              nextEpsEstimate={f.next_eps_estimate}
              nextRevenueEstimate={f.next_revenue_estimate}
            />
```

- [ ] **Step 4: Run typecheck**

Run: `cd frontend && npx tsc -b`

Expected: no errors.

- [ ] **Step 5: Run full build**

Run: `cd frontend && npm run build`

Expected: build success, no warnings related to our changes.

- [ ] **Step 6: Commit (combines Task 5 + Task 6)**

```bash
git add frontend/src/api/types.ts frontend/src/components/stock/FundamentalsCard.tsx
git commit -m "stocks: render sun/moon glyph in next-earnings row of QuarterlyTabBody

Mirrors the calendar EventChip pattern. Reads the new next_earnings_when
field from the /fundamentals payload. ☀ = pre-market, ☾ = after-market.
No icon when null (mid-session release or non-US country)."
```

---

### Task 7: Manual smoke verification

**Files:** none.

- [ ] **Step 1: Restart the backend**

Per CLAUDE.md guidance, kill the current uvicorn:

```bash
netstat -ano | findstr :8000 | findstr LISTENING
# note the PID, then:
taskkill //PID <PID> //F
# ignore the "Background command failed" notification (kill ack — see CLAUDE.md)
```

Then start a fresh uvicorn (run in background):

```bash
cd backend && ./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Wait for health to come up:

```bash
until curl -sf http://127.0.0.1:8000/api/health 2>nul | grep -q "ok"; do sleep 1; done
```

- [ ] **Step 2: Verify a US ticker with after-market earnings**

Pick any US ticker that's reported recently (e.g., AAPL). Hit:

```bash
curl -s http://127.0.0.1:8000/api/stocks/AAPL/fundamentals | python -c "import sys, json; d = json.load(sys.stdin); print(d.get('next_earnings_date'), d.get('next_earnings_when'))"
```

Expected output: a date and either `"after"` or `null`. If yfinance has a future earnings, `next_earnings_when` should not error.

- [ ] **Step 3: Verify the frontend rendering**

Build + open the dev server (or rebuild + reload), navigate to `/stocks/AAPL`, switch the FundamentalsCard tab to "Trimestrale", confirm the "prossima" row shows ☾ (or ☀ depending on the company's reporting habits, or no icon if `next_earnings_when` is null).

- [ ] **Step 4: Spot-check a `.L` ticker (should show no icon for now)**

Navigate to `/stocks/IAG.L`. The "prossima" row should render with no icon (because `country=GB` falls through to None in the classifier — by design until we model UK sessions).

- [ ] **Step 5: Mark plan complete**

No commit at this step (smoke only). Update the todo list.

---

## Self-Review

**Spec coverage:**
- §4.1 shared module → Task 1 ✓
- §4.1 calendar_service refactor → Task 2 ✓
- §4.2 schema field → Task 3 ✓
- §4.3 endpoint populator → Task 4 ✓
- §4.4 frontend types → Task 5 ✓
- §4.5 frontend rendering → Task 6 ✓
- §5.1 backend tests (unit + integration) → Task 1 + Task 4 ✓
- §5.2 manual smoke → Task 7 ✓
- §6 release: single PR, no migration — every task commits atomically ✓
- §7 ordering: Task 1→2→3→4→5→6→7 mirrors the spec's ordering ✓

**Placeholder scan:** none — every code block is concrete.

**Type consistency:** `classify_session_timing` (no leading underscore) used consistently in tests, calendar_service, and api/stocks.py. `next_earnings_when` field name identical between schema, types.ts, and JSX.

**Risks:**
- Test fixture names (`db_session`, `auth_client`) assumed but not verified. Task 4 Step 1 instructs the engineer to check conftest if names differ.
- `f.next_earnings_time_utc` exists on `FundamentalsData` (verified in spec doc § "Backend"), but the test uses a partial constructor — if FundamentalsData has additional required positional fields, the test build will fail and the engineer needs to add `field_name=...` defaults.
