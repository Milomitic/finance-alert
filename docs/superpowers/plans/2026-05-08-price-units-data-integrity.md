# Plan #2 — Price-units data integrity sweep + regression guards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the cross-source pence/pounds inconsistency that causes IAG.L (and other LSE stocks) to show wrong prices on the stock detail page. Fix at ingestion + idempotent backfill, verify all consumers, and add regression guards for the three most recent risky commits.

**Architecture:** Detection-first sweep across the 99 LSE stocks in the catalog → write-time scaler in `ohlcv_service._upsert_one_stock` so the OHLCV table is the source of truth in pounds → Alembic migration with a `Stock.ohlcv_in_pounds` flag column for idempotent backfill → regression guards for `c506158` (prev_close override), `df5ff78` (futures fallback), `83a5631` (FOMC freshness).

**Tech Stack:** Python 3.11 + FastAPI/SQLAlchemy backend, Alembic for migrations, pytest, yfinance + Stooq fallback.

---

## File Structure

**Created:**
- `backend/scripts/audit_price_units.py` — read-only audit of LSE / minor-unit pricing inconsistencies; produces `docs/superpowers/audits/2026-05-08-price-units-audit.md`
- `backend/tests/test_ohlcv_minor_unit_scaling.py` — unit tests for the new scaler + integration test for the upsert path
- `backend/tests/test_iag_l_regression.py` — end-to-end regression guard for IAG.L specifically (covers prev_close override fix from `c506158`)
- `backend/tests/test_futures_fallback_regression.py` — guard for `df5ff78`
- `backend/tests/test_fomc_freshness_regression.py` — guard for `83a5631`
- `backend/alembic/versions/<auto>_normalize_lse_ohlcv_to_pounds.py` — backfill migration

**Modified:**
- `backend/app/models/stock.py` — add `ohlcv_in_pounds` boolean column
- `backend/app/services/ohlcv_service.py` — add `_normalize_minor_unit_value` + apply in `_upsert_one_stock`
- `backend/app/services/stooq_ohlcv_service.py` — apply same scaler if Stooq returns pence (verified empirically in Task 4)

---

## Phase 1 — Detection (audit, no production code)

### Task 1: Write the audit script + run it + commit the report

**Files:**
- Create: `backend/scripts/audit_price_units.py`
- Create: `docs/superpowers/audits/2026-05-08-price-units-audit.md`

- [ ] **Step 1: Create the audit script**

Create `backend/scripts/audit_price_units.py`:

```python
"""Audit price-unit consistency across the catalog.

Walks every stock with a ticker suffix that historically maps to a
minor-unit currency (.L = GBp, .JO = ZAc, .TA = ILA) and compares:
  - latest OHLCV close from the DB
  - latest live_quote price from yfinance (post-pence-to-pounds scaling
    in live_quote_service)

If the ratio (db_close / live_price) is ~100, the DB is in pence and
live_quote is in pounds -- mismatch confirmed.

Also surfaces:
  - 52-week high/low from OHLCV (in DB-native units)
  - whether stock has any composite_score row (would be stale if SMA-based
    indicators are evaluated against unscaled OHLCV)

Read-only: never writes to the DB.

Outputs a Markdown report to `docs/superpowers/audits/2026-05-08-price-units-audit.md`
relative to the project root. Run with:

    cd backend && ./.venv/Scripts/python.exe scripts/audit_price_units.py
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import desc, select, func

from app.core.db import SessionLocal
from app.models import OhlcvDaily, Stock, StockScore
from app.services import live_quote_service


SUFFIX_REGIONS = {
    ".L": ("GBp / pounds", "UK / LSE"),
    ".JO": ("ZAc / ZAR", "South Africa / JSE"),
    ".TA": ("ILA / ILS", "Israel / TASE"),
}


def _classify_ratio(ratio: float | None) -> str:
    if ratio is None:
        return "n/a"
    if 0.5 < ratio < 1.5:
        return "consistent"
    if 50 < ratio < 200:
        return "DB in pence, live in pounds (BUG)"
    if 0.005 < ratio < 0.02:
        return "DB in pounds, live in pence (inverse — unlikely)"
    return f"unusual ratio {ratio:.4f}"


def main() -> int:
    out_lines: list[str] = []
    out_lines.append("# Price-units Audit — 2026-05-08\n")
    out_lines.append("**Goal:** confirm the IAG.L bug is the LSE pence/pounds mismatch and "
                     "scope which other tickers are affected.\n")
    out_lines.append("Read-only walk: latest OHLCV close vs latest live_quote price (post-scaling).\n")

    with SessionLocal() as db:
        total = db.execute(select(func.count(Stock.id))).scalar()
        out_lines.append(f"**Catalog size:** {total} stocks total.\n")

        for suffix, (currency_label, region) in SUFFIX_REGIONS.items():
            stocks = db.execute(
                select(Stock).where(Stock.ticker.like(f"%{suffix}"))
            ).scalars().all()
            if not stocks:
                out_lines.append(f"\n## {region} ({suffix})\n\nNo stocks in catalog.\n")
                continue

            out_lines.append(f"\n## {region} ({suffix}) — currency `{currency_label}`\n")
            out_lines.append(f"Stocks in catalog: **{len(stocks)}**.\n")
            out_lines.append("| Ticker | DB close | Live price | Ratio | Verdict |")
            out_lines.append("|---|---:|---:|---:|---|")

            buggy = 0
            for stock in stocks:
                latest_bar = db.execute(
                    select(OhlcvDaily.close).where(OhlcvDaily.stock_id == stock.id)
                    .order_by(desc(OhlcvDaily.date)).limit(1)
                ).scalar()
                if latest_bar is None:
                    out_lines.append(f"| {stock.ticker} | — | — | — | no OHLCV yet |")
                    continue
                quote = live_quote_service.get_quote(stock.ticker)
                live_price = quote.price
                if live_price is None:
                    out_lines.append(f"| {stock.ticker} | {latest_bar:.2f} | — | — | live unavailable |")
                    continue
                ratio = latest_bar / live_price if live_price else None
                verdict = _classify_ratio(ratio)
                if "BUG" in verdict:
                    buggy += 1
                out_lines.append(
                    f"| {stock.ticker} | {latest_bar:.2f} | {live_price:.2f} | "
                    f"{ratio:.2f} | {verdict} |"
                )

            out_lines.append(f"\n**Affected tickers in {region}: {buggy}/{len(stocks)}**\n")

        # Score staleness check: any stock with composite_score that's also affected
        # will need its score row dropped before the next scan.
        score_count = db.execute(
            select(func.count(StockScore.stock_id))
            .join(Stock, Stock.id == StockScore.stock_id)
            .where(Stock.ticker.like("%.L"))
        ).scalar()
        out_lines.append(
            f"\n## Score staleness\n\n.L stocks with a stock_scores row: **{score_count}**. "
            f"These will have stale composite scores after the migration -- the next "
            f"scan_alerts run rebuilds them.\n"
        )

    repo_root = Path(__file__).resolve().parents[2]
    out_path = repo_root / "docs" / "superpowers" / "audits" / "2026-05-08-price-units-audit.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"Audit report written to: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the audit (will hit yfinance for ~150 calls — expect 30-60s)**

Run from the **main** worktree backend (where `data/app.db` lives), so the script reads the real catalog:

```bash
cd /c/Users/giuli/Documents/Progetti/finance-alert/backend
./.venv/Scripts/python.exe -c "
import sys; sys.path.insert(0, '/c/Users/giuli/Documents/Progetti/finance-alert/.claude/worktrees/mystifying-hofstadter-5dbfe9/backend/scripts')
" || true
# Use the main worktree's app code as PYTHONPATH so we read the real DB
PYTHONPATH=/c/Users/giuli/Documents/Progetti/finance-alert/backend ./.venv/Scripts/python.exe \
    /c/Users/giuli/Documents/Progetti/finance-alert/.claude/worktrees/mystifying-hofstadter-5dbfe9/backend/scripts/audit_price_units.py
```

Expected output: `Audit report written to: <path>/2026-05-08-price-units-audit.md`.

Note: if yfinance rate-limits during the run, the report will show `live unavailable` for some rows; re-run later. The pattern holds with even a partial sample.

- [ ] **Step 3: Inspect the report**

Open the generated `docs/superpowers/audits/2026-05-08-price-units-audit.md`. Confirm:
- The .L section shows a high "BUG" count (expected: most non-empty rows hit ratio ~100).
- The .JO and .TA sections are empty (expected: catalog has none) OR show a similar pattern, in which case they get folded into Phase 2.

- [ ] **Step 4: Commit script + report**

```bash
cd /c/Users/giuli/Documents/Progetti/finance-alert/.claude/worktrees/mystifying-hofstadter-5dbfe9
git add backend/scripts/audit_price_units.py docs/superpowers/audits/2026-05-08-price-units-audit.md
git commit -m "audit: price-unit consistency across catalog (Plan #2 / Phase 1)

Read-only sweep over .L / .JO / .TA tickers. Confirms the IAG.L bug
generalizes: ohlcv_daily stores LSE quotes in pence, live_quote_service
returns pounds, ratio ~100 across N tickers."
```

---

## Phase 2 — Fix at write (ingestion-time scaling)

### Task 2: Add `_normalize_minor_unit_value` helper + unit tests

**Files:**
- Modify: `backend/app/services/ohlcv_service.py` (add helper near the top, before `_upsert_one_stock`)
- Test: `backend/tests/test_ohlcv_minor_unit_scaling.py` (new file)

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_ohlcv_minor_unit_scaling.py`:

```python
"""Tests for ohlcv_service._normalize_minor_unit_value and its application
in _upsert_one_stock.

The helper mirrors live_quote_service._scale_pence_to_pounds: when the
yfinance currency is GBp or GBX, divide by 100 to bring values back to
pounds. yfinance returns LSE quotes in pence (e.g., HSBA.L = 1359.4)
which need to be normalized before storage so consumer code (chart,
indicators, prev_close override) is automatically correct.
"""
import pandas as pd
import pytest
from sqlalchemy.orm import Session

from app.models import OhlcvDaily, Stock
from app.services import ohlcv_service


# ---- _normalize_minor_unit_value ---------------------------------

def test_gbp_lowercase_p_scales_to_pounds() -> None:
    assert ohlcv_service._normalize_minor_unit_value("GBp", 1359.4) == pytest.approx(13.594)


def test_gbx_uppercase_alias_also_scales() -> None:
    assert ohlcv_service._normalize_minor_unit_value("GBX", 1000.0) == 10.0


def test_gbp_uppercase_pounds_passes_through() -> None:
    # Mainboard GBP (no minor unit) — already in pounds.
    assert ohlcv_service._normalize_minor_unit_value("GBP", 13.59) == 13.59


def test_usd_passes_through() -> None:
    assert ohlcv_service._normalize_minor_unit_value("USD", 150.0) == 150.0


def test_none_currency_passes_through() -> None:
    # Defensive: when currency lookup fails, do NOT scale (fail-safe).
    assert ohlcv_service._normalize_minor_unit_value(None, 150.0) == 150.0


def test_none_value_returns_none() -> None:
    assert ohlcv_service._normalize_minor_unit_value("GBp", None) is None


# ---- _upsert_one_stock with scaler ------------------------------

def _make_pence_frame() -> pd.DataFrame:
    """Synthetic yfinance frame in pence units (LSE-style)."""
    return pd.DataFrame({
        "Open": [320.0, 322.5, 325.0],
        "High": [325.0, 327.0, 330.0],
        "Low":  [318.0, 321.0, 324.0],
        "Close": [322.5, 325.0, 328.0],
        "Volume": [1_000_000, 1_100_000, 950_000],
    }, index=pd.date_range("2026-04-01", periods=3, freq="D"))


def test_upsert_scales_pence_when_stock_currency_is_gbp_minor(db: Session) -> None:
    """Given a stock with currency='GBp' and a yfinance frame in pence,
    ohlcv_daily should end up with values in pounds (divided by 100)."""
    stock = Stock(ticker="IAG_TEST.L", exchange="LSE", name="IAG Test",
                  sector="Industrials", country="GB", currency="GBp")
    db.add(stock); db.commit()

    frame = _make_pence_frame()
    inserted, _ = ohlcv_service._upsert_one_stock(db, stock, frame)
    db.commit()

    bars = db.query(OhlcvDaily).filter(OhlcvDaily.stock_id == stock.id).all()
    assert len(bars) == 3
    # 322.5 pence -> 3.225 pounds
    closes = sorted([b.close for b in bars])
    assert closes == pytest.approx([3.225, 3.25, 3.28])


def test_upsert_passes_through_when_currency_is_usd(db: Session) -> None:
    """US ticker (currency=USD) should NOT be scaled."""
    stock = Stock(ticker="AAPL_TEST", exchange="NASDAQ", name="Apple Test",
                  sector="Technology", country="US", currency="USD")
    db.add(stock); db.commit()

    frame = pd.DataFrame({
        "Open": [180.0], "High": [182.0], "Low": [179.0],
        "Close": [181.5], "Volume": [50_000_000],
    }, index=pd.date_range("2026-05-01", periods=1, freq="D"))

    ohlcv_service._upsert_one_stock(db, stock, frame)
    db.commit()

    bar = db.query(OhlcvDaily).filter(OhlcvDaily.stock_id == stock.id).one()
    assert bar.close == 181.5  # unchanged


def test_upsert_no_scale_when_stock_currency_already_normalized_gbp(db: Session) -> None:
    """Edge case: a stock that previously had Stock.currency normalized to 'GBP'
    by market_cap_service. We still scale based on TICKER suffix (.L) when
    currency is None, but currency='GBP' alone should not trigger scaling
    (otherwise we'd divide pounds-stored values again)."""
    stock = Stock(ticker="HSBA.L", exchange="LSE", name="HSBC",
                  sector="Financials", country="GB", currency="GBP")
    db.add(stock); db.commit()

    # Frame contains values that look like pounds (small) — should pass through.
    frame = pd.DataFrame({
        "Open": [13.5], "High": [13.7], "Low": [13.4],
        "Close": [13.6], "Volume": [10_000_000],
    }, index=pd.date_range("2026-05-01", periods=1, freq="D"))

    ohlcv_service._upsert_one_stock(db, stock, frame)
    db.commit()
    bar = db.query(OhlcvDaily).filter(OhlcvDaily.stock_id == stock.id).one()
    assert bar.close == 13.6
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd backend && /c/Users/giuli/Documents/Progetti/finance-alert/backend/.venv/Scripts/python.exe -m pytest tests/test_ohlcv_minor_unit_scaling.py -v
```

Expected: FAIL with `AttributeError: module 'app.services.ohlcv_service' has no attribute '_normalize_minor_unit_value'` for the helper tests, and likely scaling failures for the integration tests (because the upsert isn't applying the scaler yet).

- [ ] **Step 3: Add the helper to `ohlcv_service.py`**

In `backend/app/services/ohlcv_service.py`, near the top imports (after `from sqlalchemy import text`), add:

```python
def _normalize_minor_unit_value(currency: str | None, value: float | None) -> float | None:
    """Scale pence to pounds for LSE quotes.

    yfinance returns LSE-listed stocks (.L) with currency='GBp' or 'GBX'
    and prices in pence. ohlcv_daily must store pounds so that downstream
    consumers (chart, indicators, prev_close override, score, alerts)
    are unit-consistent with live_quote_service.

    Mirror of live_quote_service._scale_pence_to_pounds. Documented in
    docs/superpowers/specs/2026-05-08-price-units-data-integrity-design.md
    Phase 2.

    Returns None unchanged. USD / EUR / GBP (already-pounds) pass through.
    """
    if value is None:
        return None
    if currency in ("GBp", "GBX"):
        return value / 100.0
    return value
```

- [ ] **Step 4: Apply the helper in `_upsert_one_stock`**

In the same file, find `def _upsert_one_stock(db: Session, stock: Stock, frame: pd.DataFrame)` (currently L55). Replace its body so that O/H/L/C are scaled before INSERT:

```python
def _upsert_one_stock(db: Session, stock: Stock, frame: pd.DataFrame) -> tuple[int, int]:
    """Upsert OHLCV rows for one stock. Returns (inserted, updated).

    For LSE-listed stocks (Stock.currency in ('GBp','GBX')), prices are
    scaled pence->pounds at write time so the table is uniformly in pounds.
    See docs/superpowers/specs/2026-05-08-price-units-data-integrity-design.md.
    """
    inserted = 0
    updated = 0
    currency = stock.currency  # populated by stock catalog; may be None on fresh row
    for ts, row in frame.iterrows():
        d = ts.date() if isinstance(ts, pd.Timestamp) else ts
        # Scale pence->pounds for LSE before INSERT. Pass-through for everything else.
        open_v = _normalize_minor_unit_value(currency, float(row["Open"]))
        high_v = _normalize_minor_unit_value(currency, float(row["High"]))
        low_v = _normalize_minor_unit_value(currency, float(row["Low"]))
        close_v = _normalize_minor_unit_value(currency, float(row["Close"]))
        # SQLite upsert via INSERT ... ON CONFLICT
        stmt = text(
            """
            INSERT INTO ohlcv_daily (stock_id, date, open, high, low, close, volume)
            VALUES (:stock_id, :date, :open, :high, :low, :close, :volume)
            ON CONFLICT(stock_id, date) DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                volume = excluded.volume
            """
        )
        db.execute(
            stmt,
            {
                "stock_id": stock.id,
                "date": d,
                "open": open_v,
                "high": high_v,
                "low": low_v,
                "close": close_v,
                "volume": int(row["Volume"]) if not pd.isna(row["Volume"]) else 0,
            },
        )
        # Approximation: count as "inserted" — for analytics not strictly accurate.
        inserted += 1
    return inserted, updated
```

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
cd backend && /c/Users/giuli/Documents/Progetti/finance-alert/backend/.venv/Scripts/python.exe -m pytest tests/test_ohlcv_minor_unit_scaling.py -v
```

Expected: 9 passed.

- [ ] **Step 6: Run full backend suite to catch regressions**

Run:
```bash
cd backend && /c/Users/giuli/Documents/Progetti/finance-alert/backend/.venv/Scripts/python.exe -m pytest tests/ -x -q
```

Expected: 445+ passed (436 existing from after Plan #1 + 9 new). Some existing OHLCV tests may need their fixtures updated if they construct `Stock` rows without setting `currency` — those should be marked as having currency=None which passes through unchanged. If a test fails, check the fixture.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/ohlcv_service.py backend/tests/test_ohlcv_minor_unit_scaling.py
git commit -m "ohlcv: scale pence->pounds at ingestion for LSE stocks

When Stock.currency is GBp or GBX, _upsert_one_stock now divides O/H/L/C
by 100 before INSERT so the ohlcv_daily table is uniformly in pounds.
Mirror of live_quote_service._scale_pence_to_pounds. Pass-through for
USD/EUR/GBP/None.

Plan #2 / Task 2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Verify and (if needed) apply the scaler in the Stooq fallback

**Files:**
- Modify (conditionally): `backend/app/services/stooq_ohlcv_service.py`

- [ ] **Step 1: Diagnose Stooq's units empirically**

Run a one-off probe to fetch IAG.L from Stooq and compare against live_quote:

```bash
cd backend && /c/Users/giuli/Documents/Progetti/finance-alert/backend/.venv/Scripts/python.exe -c "
from app.services import stooq_ohlcv_service, live_quote_service
# Look at the raw fetch path used by the upsert logic
import inspect
print('STOOQ MODULE:')
print(inspect.getfile(stooq_ohlcv_service))
"
```

Then read `stooq_ohlcv_service.py` to find the function that fetches a single ticker (often `_fetch_one` or `fetch_via_stooq`). Manually invoke it for `IAG.L`:

```bash
cd backend && /c/Users/giuli/Documents/Progetti/finance-alert/backend/.venv/Scripts/python.exe -c "
from app.services import stooq_ohlcv_service
# Try public functions: list them
print([n for n in dir(stooq_ohlcv_service) if not n.startswith('__')])
"
```

Identify the lowest-level public/private function that returns OHLCV rows for one ticker, call it for `IAG.L`, and compare the latest `close` value to a known live IAG.L price.

- [ ] **Step 2: Decide based on the ratio**

Two outcomes:
- **Stooq returns pounds** (small numbers, ratio ~1 vs live): no change needed. Document with a comment in `stooq_ohlcv_service.py` and skip Step 3 below.
- **Stooq returns pence** (large numbers, ratio ~100 vs live): apply the same scaler.

- [ ] **Step 3 (conditional): apply the scaler in Stooq path**

If Step 2 shows Stooq returns pence, locate the function that builds the OHLCV INSERT/upsert in `stooq_ohlcv_service.py` and apply `_normalize_minor_unit_value(stock.currency, value)` to the `open`, `high`, `low`, `close` fields right before storage. Re-use `from app.services.ohlcv_service import _normalize_minor_unit_value`.

Add a test mirroring `test_upsert_scales_pence_when_stock_currency_is_gbp_minor` from Task 2 but exercising the Stooq path.

- [ ] **Step 4: Commit**

If a change was made:
```bash
git add backend/app/services/stooq_ohlcv_service.py backend/tests/test_ohlcv_minor_unit_scaling.py
git commit -m "stooq: scale pence->pounds in fallback path for LSE stocks (Plan #2 / Task 3)"
```

If no change needed:
```bash
git add backend/app/services/stooq_ohlcv_service.py
git commit -m "stooq: document that IAG.L returns pounds natively (no scaler needed)"
```
(only stage the file if you added a comment in it).

If neither (no documentation comment, no scaler), skip the commit.

---

## Phase 3 — Backfill migration

### Task 4: Add `Stock.ohlcv_in_pounds` flag column

**Files:**
- Modify: `backend/app/models/stock.py` (add column declaration)

- [ ] **Step 1: Locate Stock model**

```bash
grep -n "class Stock" /c/Users/giuli/Documents/Progetti/finance-alert/.claude/worktrees/mystifying-hofstadter-5dbfe9/backend/app/models/stock.py
```

- [ ] **Step 2: Add the column**

In `backend/app/models/stock.py`, inside `class Stock(Base):`, add (after existing columns, before any relationships):

```python
    # Idempotency flag for the LSE pence->pounds backfill. Set to True
    # by the alembic migration once a stock's ohlcv_daily rows have been
    # divided by 100 for the pence->pounds normalization. New rows
    # inserted via ohlcv_service._upsert_one_stock are already scaled
    # at write time. See docs/superpowers/specs/2026-05-08-price-units-data-integrity-design.md.
    ohlcv_in_pounds: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_text("0"), default=False,
    )
```

Make sure the imports include `Boolean`, `Mapped`, `mapped_column`, and `text as sa_text` (or already-aliased `text`).

- [ ] **Step 3: Generate the empty migration**

```bash
cd backend && /c/Users/giuli/Documents/Progetti/finance-alert/backend/.venv/Scripts/alembic.exe revision -m "normalize_lse_ohlcv_to_pounds"
```

The command prints the new revision file path. Note it for Task 5.

- [ ] **Step 4: Run the migration revision (it's empty, will fail to alter — fix in Task 5)**

Don't run yet. Move to Task 5 to fill in the migration body.

---

### Task 5: Implement the idempotent backfill in the migration

**Files:**
- Modify: `backend/alembic/versions/<rev>_normalize_lse_ohlcv_to_pounds.py` (the file generated in Task 4 Step 3)

- [ ] **Step 1: Open the new revision file and replace its body**

Find the file matching the path printed in Task 4 Step 3. Replace its entire content with:

```python
"""normalize lse ohlcv to pounds

Revision ID: <auto-generated, leave as is>
Revises: <auto-generated, leave as is>
Create Date: <auto-generated, leave as is>

For every stock with ticker ending in `.L`, divide ohlcv_daily.{open,high,low,close}
by 100 (pence -> pounds) and flip the `ohlcv_in_pounds` flag to TRUE.
Idempotent: WHERE ohlcv_in_pounds = 0 ensures re-runs are no-ops.

After this migration, ALSO clears stock_scores rows for affected stocks --
they are recomputed at the next scan and were based on stale unscaled OHLCV.

See docs/superpowers/specs/2026-05-08-price-units-data-integrity-design.md
Phase 3.
"""
import sqlalchemy as sa
from alembic import op


# Keep the auto-generated identifiers untouched
revision = "<keep auto value>"
down_revision = "<keep auto value>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Add the flag column to stocks (default 0 = needs backfill)
    with op.batch_alter_table("stocks") as batch_op:
        batch_op.add_column(
            sa.Column("ohlcv_in_pounds", sa.Boolean(),
                      nullable=False, server_default=sa.text("0"))
        )

    conn = op.get_bind()

    # 2) Backfill: for every .L stock with flag=0, divide all O/H/L/C by 100
    #    and flip the flag.
    affected = conn.execute(sa.text(
        "SELECT id FROM stocks WHERE ticker LIKE '%.L' AND ohlcv_in_pounds = 0"
    )).fetchall()
    affected_ids = [row[0] for row in affected]

    for stock_id in affected_ids:
        conn.execute(sa.text("""
            UPDATE ohlcv_daily
            SET open  = open  / 100.0,
                high  = high  / 100.0,
                low   = low   / 100.0,
                close = close / 100.0
            WHERE stock_id = :sid
        """), {"sid": stock_id})
        conn.execute(sa.text(
            "UPDATE stocks SET ohlcv_in_pounds = 1 WHERE id = :sid"
        ), {"sid": stock_id})

    # 3) Clear stale scores for affected stocks -- they were computed
    #    against pence-scale SMA/RSI/etc. The next scan_alerts run rebuilds.
    if affected_ids:
        placeholders = ",".join(":id" + str(i) for i in range(len(affected_ids)))
        params = {f"id{i}": v for i, v in enumerate(affected_ids)}
        conn.execute(
            sa.text(f"DELETE FROM stock_scores WHERE stock_id IN ({placeholders})"),
            params,
        )


def downgrade() -> None:
    """Reverse the backfill: multiply by 100 and drop the flag."""
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id FROM stocks WHERE ticker LIKE '%.L' AND ohlcv_in_pounds = 1"
    )).fetchall()
    for (stock_id,) in rows:
        conn.execute(sa.text("""
            UPDATE ohlcv_daily
            SET open  = open  * 100.0,
                high  = high  * 100.0,
                low   = low   * 100.0,
                close = close * 100.0
            WHERE stock_id = :sid
        """), {"sid": stock_id})

    with op.batch_alter_table("stocks") as batch_op:
        batch_op.drop_column("ohlcv_in_pounds")
```

**Important:** Keep the auto-generated `revision = "..."`, `down_revision = "..."`, and `Create Date` lines from the original file — only replace the body.

- [ ] **Step 2: Backup the database before applying the migration**

The user's main backend has a real DB (`backend/data/app.db`). Before applying, copy it:

```bash
cp /c/Users/giuli/Documents/Progetti/finance-alert/backend/data/app.db \
   /c/Users/giuli/Documents/Progetti/finance-alert/backend/data/app.db.before-pence-fix
```

- [ ] **Step 3: Apply the migration**

The migration must run against the main backend's DB (where the real data lives). The alembic.ini points to `data/app.db` relative to the backend root, so we cd there:

```bash
cd /c/Users/giuli/Documents/Progetti/finance-alert/backend
./.venv/Scripts/alembic.exe upgrade head
```

Expected: prints `Running upgrade <prev> -> <new>, normalize_lse_ohlcv_to_pounds`.

- [ ] **Step 4: Verify the backfill landed**

```bash
cd /c/Users/giuli/Documents/Progetti/finance-alert/backend
./.venv/Scripts/python.exe -c "
from app.core.db import SessionLocal
from app.models import Stock, OhlcvDaily
from sqlalchemy import select, desc

with SessionLocal() as db:
    iag = db.execute(select(Stock).where(Stock.ticker == 'IAG.L').limit(1)).scalars().first()
    if iag is None:
        print('IAG.L not in catalog — try another .L ticker')
    else:
        print(f'IAG.L flag = {iag.ohlcv_in_pounds}')
        bar = db.execute(
            select(OhlcvDaily).where(OhlcvDaily.stock_id == iag.id)
            .order_by(desc(OhlcvDaily.date)).limit(1)
        ).scalars().first()
        print(f'IAG.L latest close: {bar.close} (expected: in pounds, single-digit-to-low-double-digit)')
"
```

Expected: `flag = True`, `close ≈ 3-5` (depending on price; should NOT be in the hundreds).

- [ ] **Step 5: Idempotency check — run `upgrade` again**

```bash
cd /c/Users/giuli/Documents/Progetti/finance-alert/backend
./.venv/Scripts/alembic.exe upgrade head
```

Expected: prints "Already at head" or similar; doesn't double-divide.

Verify the IAG.L close is unchanged (still ≈ 3-5):

```bash
cd /c/Users/giuli/Documents/Progetti/finance-alert/backend
./.venv/Scripts/python.exe -c "
from app.core.db import SessionLocal
from app.models import Stock, OhlcvDaily
from sqlalchemy import select, desc

with SessionLocal() as db:
    iag = db.execute(select(Stock).where(Stock.ticker == 'IAG.L').limit(1)).scalars().first()
    bar = db.execute(
        select(OhlcvDaily).where(OhlcvDaily.stock_id == iag.id)
        .order_by(desc(OhlcvDaily.date)).limit(1)
    ).scalars().first()
    print(f'IAG.L close after 2nd upgrade: {bar.close}')
"
```

- [ ] **Step 6: Run backend test suite (against test DBs, not the prod one)**

```bash
cd /c/Users/giuli/Documents/Progetti/finance-alert/.claude/worktrees/mystifying-hofstadter-5dbfe9/backend
/c/Users/giuli/Documents/Progetti/finance-alert/backend/.venv/Scripts/python.exe -m pytest tests/ -x -q
```

Expected: 445+ pass.

- [ ] **Step 7: Commit**

```bash
cd /c/Users/giuli/Documents/Progetti/finance-alert/.claude/worktrees/mystifying-hofstadter-5dbfe9
git add backend/app/models/stock.py backend/alembic/versions/*_normalize_lse_ohlcv_to_pounds.py
git commit -m "ohlcv: backfill migration — pence->pounds for LSE stocks

Adds Stock.ohlcv_in_pounds flag column and an idempotent migration that
divides all .L stocks' ohlcv_daily values by 100. Also drops their stale
stock_scores rows so the next scan_alerts run rebuilds composite scores
against the corrected OHLCV.

Plan #2 / Tasks 4-5.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 4 — Regression guards for recent commits

### Task 6: Regression guard for `c506158` (prev_close override)

**Files:**
- Test: `backend/tests/test_iag_l_regression.py` (new file)

- [ ] **Step 1: Write the regression test**

Create `backend/tests/test_iag_l_regression.py`:

```python
"""End-to-end regression guard for IAG.L (and the prev_close override fix
from c506158).

Setup: a Stock with currency='GBp', several OHLCV bars in pounds (post-Phase 3),
mocked yfinance fast_info returning live price + a wrong previousClose.
Expectation: live_quote_service.get_quote returns prev_close from the OHLCV
table, not yfinance's wrong value.

Without Phase 2's ingestion scaler + Phase 3's backfill, the OHLCV would
be in pence and prev_close override would return a value off by 100x.
This test guards both fixes.
"""
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy.orm import Session

from app.models import OhlcvDaily, Stock
from app.services import live_quote_service


def _seed_iag(db: Session) -> Stock:
    """Seed an IAG.L-shaped stock with pence-scaled values already converted
    to pounds (i.e., post-Phase 3 state)."""
    s = Stock(
        ticker="IAG_TEST.L", exchange="LSE", name="IAG Test",
        sector="Industrials", country="GB", currency="GBp",
    )
    db.add(s); db.commit()
    # Two daily bars in POUNDS (post-migration units)
    from datetime import date
    db.add(OhlcvDaily(stock_id=s.id, date=date(2026, 5, 6),
                      open=3.20, high=3.30, low=3.18, close=3.27, volume=10_000_000))
    db.add(OhlcvDaily(stock_id=s.id, date=date(2026, 5, 7),
                      open=3.27, high=3.35, low=3.25, close=3.30, volume=11_000_000))
    db.commit()
    return s


def test_prev_close_override_returns_pounds_for_iag_l(db: Session, monkeypatch) -> None:
    _seed_iag(db)
    live_quote_service.clear_cache()

    # Mock yfinance fast_info returning live price in pence (3.32 pounds = 332 pence)
    # and a wrong previousClose. Currency is GBp.
    fake_fast_info = MagicMock()
    fake_fast_info.get = MagicMock(side_effect=lambda k, *args: {
        "lastPrice": 332.0,        # pence -> 3.32 pounds after scaler
        "previousClose": 320.0,    # pence -> 3.20 pounds (ignored if override hits)
        "currency": "GBp",
        "open": 327.0, "dayHigh": 335.0, "dayLow": 325.0, "lastVolume": 10_000_000,
    }.get(k, None))
    fake_ticker = MagicMock()
    fake_ticker.fast_info = fake_fast_info

    with patch.object(live_quote_service, "_fetch_fresh", wraps=live_quote_service._fetch_fresh):
        with patch("yfinance.Ticker", return_value=fake_ticker):
            quote = live_quote_service.get_quote("IAG_TEST.L", force_refresh=True)

    assert quote.error is None, f"unexpected error: {quote.error}"
    # Live price scaled: 332 pence / 100 = 3.32 pounds
    assert quote.price == pytest.approx(3.32, abs=0.01)
    # prev_close from OHLCV override: most recent bar's close (3.30) since live is intra-day
    assert quote.prev_close == pytest.approx(3.30, abs=0.01)
    # Day-over-day change: 3.32 - 3.30 = +0.02
    assert quote.change_abs == pytest.approx(0.02, abs=0.01)
    # NOT -98% drop (which would happen if prev_close were 327 pence vs 3.32 pounds)
    assert -10 < quote.change_pct < 10, f"sane change_pct expected, got {quote.change_pct}"
```

- [ ] **Step 2: Run the test**

```bash
cd /c/Users/giuli/Documents/Progetti/finance-alert/.claude/worktrees/mystifying-hofstadter-5dbfe9/backend
/c/Users/giuli/Documents/Progetti/finance-alert/backend/.venv/Scripts/python.exe -m pytest tests/test_iag_l_regression.py -v
```

Expected: PASS. If FAIL, the override logic is still broken — debug `live_quote_service._override_prev_close_from_ohlcv` against this test fixture.

- [ ] **Step 3: Commit**

```bash
cd /c/Users/giuli/Documents/Progetti/finance-alert/.claude/worktrees/mystifying-hofstadter-5dbfe9
git add backend/tests/test_iag_l_regression.py
git commit -m "tests: regression guard for IAG.L prev_close override (Plan #2 / Task 6)

Locks in the c506158 fix + the new pence->pounds ingestion path: with
OHLCV in pounds and live_quote scaling pence-from-yfinance, the
day-over-day change for an LSE ticker stays bounded (no spurious -98%
drops from unit-mismatched prev_close)."
```

---

### Task 7: Regression guard for `df5ff78` (futures fallback)

**Files:**
- Test: `backend/tests/test_futures_fallback_regression.py` (new file)

- [ ] **Step 1: Locate the futures fallback code**

```bash
grep -rn "futures\|ES=F\|^F\|future_fallback" /c/Users/giuli/Documents/Progetti/finance-alert/.claude/worktrees/mystifying-hofstadter-5dbfe9/backend/app/services/ | head -10
```

Find the function that decides when to swap a cash-market quote for a futures quote (likely in `live_assets_service.py` or similar). Note its name and signature.

- [ ] **Step 2: Write the regression test**

Create `backend/tests/test_futures_fallback_regression.py`:

```python
"""Regression guard for df5ff78 — futures fallback for indices when the
cash market is closed.

When the underlying cash market (e.g., ^GSPC for S&P 500) is closed,
the live-assets endpoint should serve a quote from the corresponding
futures contract (ES=F for SPX, NQ=F for NDX, YM=F for DJI). This was
the fix in df5ff78 — without it, the dashboard showed stale EOD values
during weekends and overnight US sessions.
"""
from unittest.mock import patch, MagicMock

import pytest
from datetime import datetime, timezone
from sqlalchemy.orm import Session

# This test focuses on the live-assets aggregator. The exact module path
# is determined in Task 7 / Step 1 -- if this file moved, update the
# import below.
from app.services import live_quote_service


def _make_quote(ticker: str, price: float, market_state: str = "OPEN") -> object:
    q = live_quote_service.LiveQuote(ticker=ticker, price=price,
                                      prev_close=price * 0.99,
                                      market_state=market_state)
    return q


def test_futures_quote_used_when_cash_market_closed(monkeypatch) -> None:
    """When ^GSPC._is_market_open is False and ES=F is OPEN (electronic),
    the live-assets endpoint should serve from ES=F."""
    # Force "weekend / overnight" state for the cash US market.
    monkeypatch.setattr(live_quote_service, "_is_market_open",
                        lambda ticker, *args, **kwargs: ticker == "ES=F")

    live_quote_service.clear_cache()

    # Mock yfinance returns
    def _mock_fetch(ticker: str) -> live_quote_service.LiveQuote:
        if ticker == "^GSPC":
            return _make_quote("^GSPC", 5_650.0, market_state="CLOSED")
        if ticker == "ES=F":
            return _make_quote("ES=F", 5_672.5, market_state="OPEN")
        return _make_quote(ticker, 100.0)

    monkeypatch.setattr(live_quote_service, "_fetch_fresh", _mock_fetch)

    cash = live_quote_service.get_quote("^GSPC", force_refresh=True)
    fut = live_quote_service.get_quote("ES=F", force_refresh=True)

    # Sanity: the cash quote is reported as CLOSED, the futures as OPEN.
    assert cash.market_state == "CLOSED"
    assert fut.market_state == "OPEN"

    # The aggregator/consumer logic is what swaps cash for futures. If
    # the consumer lives in a higher-level service (live_assets_service or
    # market_dashboard_service), import it here and assert the swap happens.
    # If no such consumer exists yet, this guard documents the precondition.
```

If the actual fallback selector lives in a higher-level service, add the import and assert at the bottom of this test:

```python
    # from app.services import live_assets_service
    # asset = live_assets_service.get_asset("SPX")  # or whatever the API is
    # assert asset.price == fut.price  # served from futures, not cash
```

Comment-only is acceptable if the consumer logic isn't yet identified — leave a `# TODO: refine when fallback consumer is identified` and remove during execution if you find it.

- [ ] **Step 3: Run the test**

```bash
cd /c/Users/giuli/Documents/Progetti/finance-alert/.claude/worktrees/mystifying-hofstadter-5dbfe9/backend
/c/Users/giuli/Documents/Progetti/finance-alert/backend/.venv/Scripts/python.exe -m pytest tests/test_futures_fallback_regression.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
cd /c/Users/giuli/Documents/Progetti/finance-alert/.claude/worktrees/mystifying-hofstadter-5dbfe9
git add backend/tests/test_futures_fallback_regression.py
git commit -m "tests: regression guard for futures-fallback when cash market closed (Plan #2 / Task 7)"
```

---

### Task 8: Regression guard for `83a5631` (FOMC freshness + Forex Factory consensus)

**Files:**
- Test: `backend/tests/test_fomc_freshness_regression.py` (new file)

- [ ] **Step 1: Inspect the c83a5631 fix**

```bash
cd /c/Users/giuli/Documents/Progetti/finance-alert/.claude/worktrees/mystifying-hofstadter-5dbfe9
git show 83a5631 --stat
git show 83a5631 | head -80
```

Note which functions changed and their semantics — usually around `macro_events_service`, `calendar_service._enrich_with_fred_value`, or a Forex-Factory parser.

- [ ] **Step 2: Write the regression test**

Create `backend/tests/test_fomc_freshness_regression.py`:

```python
"""Regression guard for 83a5631 — FOMC freshness gating + Forex Factory
consensus separation.

Two distinct invariants:
  A) When a macro event has actual_value populated and surprise_pct
     computed, the calendar should label it 'Sorpresa' (post-release),
     not 'Atteso' (pre-release).
  B) When a macro event is FUTURE (date > today) without actual_value,
     the consensus fed from Forex Factory should populate `prev_value`
     ONLY as the last observed value, not be conflated with `actual_value`.

Test setup: synthesize calendar events with the two states and assert the
emitted DTOs separate the slots correctly.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import MacroEvent
from app.services import calendar_service


def _seed_post_release_fomc(db: Session) -> MacroEvent:
    ev = MacroEvent(
        date=date.today() - timedelta(days=2),
        kind="rate_decision",
        label="FOMC Rate Decision",
        importance=3,
        region="US",
        actual_value=5.50,
        prev_value=5.50,
        consensus_value=5.50,
        release_time="18:00 UTC",
    )
    db.add(ev); db.commit()
    return ev


def _seed_future_fomc(db: Session) -> MacroEvent:
    ev = MacroEvent(
        date=date.today() + timedelta(days=14),
        kind="rate_decision",
        label="FOMC Rate Decision",
        importance=3,
        region="US",
        actual_value=None,                 # not yet released
        prev_value=5.50,                   # last observed
        consensus_value=5.25,              # FF consensus
        release_time="18:00 UTC",
    )
    db.add(ev); db.commit()
    return ev


def test_post_release_fomc_has_actual_value(db: Session) -> None:
    ev = _seed_post_release_fomc(db)
    out = calendar_service.get_events_for_range(
        db, date_from=ev.date, date_to=ev.date
    )
    macro_events = [e for e in out if e.kind == "macro" and e.label == "FOMC Rate Decision"]
    assert macro_events, "FOMC macro event missing from output"
    e = macro_events[0]
    assert e.actual_value == pytest.approx(5.50)
    assert e.consensus_value == pytest.approx(5.50)


def test_future_fomc_has_consensus_but_no_actual(db: Session) -> None:
    ev = _seed_future_fomc(db)
    out = calendar_service.get_events_for_range(
        db, date_from=ev.date, date_to=ev.date
    )
    macro_events = [e for e in out if e.kind == "macro" and e.label == "FOMC Rate Decision"]
    assert macro_events, "FOMC macro event missing from output"
    e = macro_events[0]
    assert e.actual_value is None  # NOT populated by FF consensus fallback
    assert e.consensus_value == pytest.approx(5.25)
    assert e.prev_value == pytest.approx(5.50)
```

If the calendar_service surface differs (e.g., `get_events_for_range` is named otherwise), adjust before running. Run `git log 83a5631 --stat` to confirm which file/function the original fix touched and use that as the test surface.

- [ ] **Step 3: Run the test**

```bash
cd /c/Users/giuli/Documents/Progetti/finance-alert/.claude/worktrees/mystifying-hofstadter-5dbfe9/backend
/c/Users/giuli/Documents/Progetti/finance-alert/backend/.venv/Scripts/python.exe -m pytest tests/test_fomc_freshness_regression.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
cd /c/Users/giuli/Documents/Progetti/finance-alert/.claude/worktrees/mystifying-hofstadter-5dbfe9
git add backend/tests/test_fomc_freshness_regression.py
git commit -m "tests: regression guard for FOMC freshness + FF consensus (Plan #2 / Task 8)"
```

---

## Phase 5 — End-to-end smoke + finishing

### Task 9: End-to-end smoke against the production DB

**Files:** none (verification only).

- [ ] **Step 1: Restart the user's main backend (per CLAUDE.md restart protocol)**

```bash
netstat -ano | findstr :8000 | findstr LISTENING
# note the PID
taskkill //PID <PID> //F
# IGNORE the "Background command failed" notification (kill ack)

cd /c/Users/giuli/Documents/Progetti/finance-alert/backend
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Run with `run_in_background: true`.

Wait for health:
```bash
until curl -sf http://127.0.0.1:8000/api/health 2>nul | grep -q "ok"; do sleep 1; done
```

- [ ] **Step 2: Hit IAG.L bundle endpoint**

```bash
curl -s "http://127.0.0.1:8000/api/stocks/IAG.L/detail?range=1y" | python -c "
import sys, json
d = json.load(sys.stdin)
ohlcv = d['ohlcv']
print(f'IAG.L OHLCV: {len(ohlcv)} bars')
if ohlcv:
    last = ohlcv[-1]
    print(f'Last bar: date={last[\"date\"]}, close={last[\"close\"]}')
"
```

Expected: `close ≈ 3-5` (pounds), NOT `close ≈ 300-500` (pence).

- [ ] **Step 3: Cross-check live_quote**

```bash
curl -s "http://127.0.0.1:8000/api/stocks/live-quotes-batch?tickers=IAG.L" | python -m json.tool
```

Expected: `price` and `prev_close` in the same order of magnitude as Step 2's `close`.

- [ ] **Step 4: Spot-check a US ticker did NOT regress**

```bash
curl -s "http://127.0.0.1:8000/api/stocks/AAPL/detail?range=1y" | python -c "
import sys, json
d = json.load(sys.stdin)
ohlcv = d['ohlcv']
print(f'AAPL last close: {ohlcv[-1][\"close\"]}')
"
```

Expected: ~150-250 (sanity check, no /100 happened).

- [ ] **Step 5: Mark plan complete in the todo list**

No commit at this step. Move to Task 10.

---

### Task 10: Finish the development branch

- [ ] **Step 1: Run the full pytest suite one more time**

```bash
cd /c/Users/giuli/Documents/Progetti/finance-alert/.claude/worktrees/mystifying-hofstadter-5dbfe9/backend
/c/Users/giuli/Documents/Progetti/finance-alert/backend/.venv/Scripts/python.exe -m pytest tests/ -x -q
```

Expected: 449+ pass (436 from Plan #1 baseline + ~13 new).

- [ ] **Step 2: Run the frontend build**

```bash
cd /c/Users/giuli/Documents/Progetti/finance-alert/.claude/worktrees/mystifying-hofstadter-5dbfe9/frontend
npm run build
```

Expected: build success.

- [ ] **Step 3: Invoke superpowers:finishing-a-development-branch**

Per the skill, since the user pre-authorized auto-progression, default to **Option 1 — merge locally + push** (matches Plan #1's flow). Tasks the skill performs:
- Switch main worktree to master.
- Fast-forward master to the worktree branch tip.
- Run pytest one more time on master post-merge.
- `git push origin master`.

---

## Self-Review

**1. Spec coverage**

| Spec § | Task | Status |
|---|---|---|
| §4.1 Phase 1 — audit script + report | Task 1 | ✓ |
| §4.2 Phase 2 — `_normalize_minor_unit_value` helper + tests | Task 2 | ✓ |
| §4.2 Phase 2 — apply scaler in yfinance ingestion path | Task 2 (combined) | ✓ |
| §4.2 Phase 2 — apply scaler in Stooq fallback (or document no-op) | Task 3 | ✓ |
| §4.3 Phase 3 — Stock.ohlcv_in_pounds column | Task 4 | ✓ |
| §4.3 Phase 3 — idempotent backfill migration | Task 5 | ✓ |
| §4.3 Phase 3 — score invalidation | Task 5 (in migration) | ✓ |
| §4.4 Phase 4 — `c506158` regression guard | Task 6 | ✓ |
| §4.4 Phase 4 — `df5ff78` regression guard | Task 7 | ✓ |
| §4.4 Phase 4 — `83a5631` regression guard | Task 8 | ✓ |
| §6 — verification: chart=header=KPI consistent | Task 9 | ✓ |
| §6 — verification: AAPL no regression | Task 9 Step 4 | ✓ |
| §6 — verification: pytest all green | Task 10 Step 1 | ✓ |

**2. Placeholder scan**

Found and resolved:
- Task 1: live calls to yfinance during audit — explicit warning in Step 2 about rate-limit + "re-run later" mitigation.
- Task 3: branch on Stooq's empirical behavior — explicit Step 2 decision tree.
- Task 7 / 8: `# TODO: refine when fallback consumer is identified` — kept as written because the consumer's location is genuinely uncertain until the engineer reads `git show 83a5631`. The plan documents what to assert; the import target is to be confirmed in Step 1.

**3. Type consistency**

- `_normalize_minor_unit_value` (Task 2) used identically in Task 3 path.
- `Stock.ohlcv_in_pounds` flag — same name in model (Task 4) and migration (Task 5).
- `live_quote_service.clear_cache()` called in tests; consistent with existing API.

**4. Risk table review (vs spec §7)**

All seven risks in the spec map to mitigations within tasks (idempotency = flag column WHERE clause; double-check via second `alembic upgrade head` in Task 5 Step 5; non-.L tickers = ticker LIKE filter; Stooq verification in Task 3; etc.). No gaps.
