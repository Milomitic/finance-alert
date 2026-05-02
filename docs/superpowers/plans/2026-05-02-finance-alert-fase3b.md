# Fase 3B Stock Detail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nuova pagina `/stocks/:ticker` con candlestick chart, indicatori, drawing tools, price-target alerts, news, alert history e regole effettive read-only. Sostituire il SpotlightPlaceholder in HomePage con cards reali (top gainer + most-alerted + vol spike).

**Architecture:** Nuovo modello `PriceAlert` (tabella separata per alert price-target per-stock per-istanza, distinto dalle regole signal-based). Nuovi service `stock_detail_service`, `price_alert_service`, `stock_news_service`, `spotlight_service`. Estensione `scan_runner` con step "evaluate price alerts" non-fatal. Frontend: lightweight-charts (TradingView, ~45kB) per candlestick + SMA + volume + RSI panel. Drawings persistiti in localStorage.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, pytest, yfinance (per news), React 19, TypeScript 6, TanStack Query 5, **lightweight-charts 4.x** (NEW dep), shadcn/ui, Recharts (per sparkline mini in spotlight).

**Spec di riferimento:** `docs/superpowers/specs/2026-05-02-finance-alert-fase3b-stock-detail-design.md`

---

## File Structure

### Backend new files
```
backend/app/models/price_alert.py
backend/alembic/versions/<auto>_add_price_alerts.py
backend/app/services/stock_detail_service.py
backend/app/services/price_alert_service.py
backend/app/services/stock_news_service.py
backend/app/services/spotlight_service.py
backend/app/schemas/stock_detail.py
backend/app/schemas/price_alert.py
backend/app/schemas/spotlight.py
backend/app/api/price_alerts.py
backend/app/api/spotlight.py
backend/tests/test_models_price_alert.py
backend/tests/test_price_alert_service.py
backend/tests/test_stock_detail_service.py
backend/tests/test_stock_news_service.py
backend/tests/test_spotlight_service.py
backend/tests/test_api_stock_detail.py
backend/tests/test_api_stock_news.py
backend/tests/test_api_price_alerts.py
backend/tests/test_api_spotlight.py
```

### Backend modified
```
backend/app/models/__init__.py             aggiungere import PriceAlert
backend/app/models/alert.py                rule_id nullable
backend/app/api/stocks.py                  estendere con detail + news endpoints
backend/app/services/scan_runner.py        wire price_alert evaluator
backend/app/services/stats_service.py      add get_top_alerted_stock_7d helper
backend/app/main.py                        register price_alerts + spotlight routers
```

### Frontend new files
```
frontend/src/lib/stockMeta.ts                                country code -> flag mapping for stocks
frontend/src/api/priceAlerts.ts
frontend/src/api/spotlight.ts
frontend/src/hooks/useStockDetail.ts
frontend/src/hooks/useStockPriceAlerts.ts
frontend/src/hooks/useStockNews.ts
frontend/src/hooks/useSpotlight.ts
frontend/src/hooks/useStockDrawings.ts
frontend/src/pages/StockDetailPage.tsx
frontend/src/components/stock/StockHeader.tsx
frontend/src/components/stock/PriceChart.tsx
frontend/src/components/stock/RsiPanel.tsx
frontend/src/components/stock/RangeSelector.tsx
frontend/src/components/stock/IndicatorToggles.tsx
frontend/src/components/stock/DrawingToolbar.tsx
frontend/src/components/stock/TechnicalKpiCard.tsx
frontend/src/components/stock/PriceAlertsCard.tsx
frontend/src/components/stock/PriceAlertDialog.tsx
frontend/src/components/stock/StockAlertsHistoryCard.tsx
frontend/src/components/stock/EffectiveRulesCard.tsx
frontend/src/components/stock/NewsCard.tsx
frontend/src/components/dashboard/SpotlightCards.tsx
```

### Frontend modified
```
frontend/src/api/types.ts                              + StockDetail, OhlcvBar, IndicatorSeries, StockKpis, EffectiveRule, StockNewsItem, PriceAlert*, SpotlightCard
frontend/src/api/stocks.ts                             + detail, news methods
frontend/src/App.tsx                                    + route /stocks/:ticker
frontend/src/components/Layout.tsx                     enable Stocks sidebar entry
frontend/src/pages/HomePage.tsx                        replace SpotlightPlaceholder with SpotlightCards
frontend/src/components/dashboard/MarketTreemap.tsx    onClick navigate to /stocks/:ticker
```

### Frontend deleted
```
frontend/src/components/dashboard/SpotlightPlaceholder.tsx
```

---

## Section A — Foundation (model + migration)

### Task A1: PriceAlert model + register + UPSERT smoke test

**Files:**
- Create: `backend/app/models/price_alert.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/alert.py` (rule_id nullable)
- Test: `backend/tests/test_models_price_alert.py`

- [ ] **Step 1: Create `backend/app/models/price_alert.py`**

```python
"""Price-target alert: per-stock, per-instance alert that fires when the stock
price crosses a target threshold. Distinct from signal-based Rules (RSI etc.)."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy import Index as SAIndex
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class PriceAlert(Base):
    __tablename__ = "price_alerts"
    __table_args__ = (
        SAIndex("ix_price_alerts_stock_id", "stock_id"),
        SAIndex("ix_price_alerts_enabled", "enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
    )
    target_price: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)  # "above" | "below"
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 2: Register in `backend/app/models/__init__.py`**

Read the file. Add `from app.models.price_alert import PriceAlert` (alphabetical placement) and add `"PriceAlert"` to `__all__`.

- [ ] **Step 3: Make `Alert.rule_id` nullable in `backend/app/models/alert.py`**

Find:
```python
    rule_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("rules.id", ondelete="CASCADE"), nullable=False
    )
```
Replace with:
```python
    rule_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("rules.id", ondelete="CASCADE"), nullable=True
    )
```

- [ ] **Step 4: Write smoke test**

`backend/tests/test_models_price_alert.py`:
```python
"""Test PriceAlert model — basic CRUD and FK behavior."""
from datetime import UTC, datetime

from app.models import PriceAlert, Stock


def test_create_price_alert(db):
    stock = Stock(ticker="TEST", exchange="NMS", name="Test Co")
    db.add(stock)
    db.commit()

    pa = PriceAlert(
        stock_id=stock.id,
        target_price=100.0,
        direction="above",
        enabled=True,
        note="resistance",
    )
    db.add(pa)
    db.commit()
    db.refresh(pa)

    assert pa.id is not None
    assert pa.triggered_at is None
    assert pa.created_at is not None


def test_price_alert_cascade_on_stock_delete(db):
    stock = Stock(ticker="DEL", exchange="NMS", name="Delete Me")
    db.add(stock)
    db.commit()

    db.add(PriceAlert(stock_id=stock.id, target_price=50.0, direction="below"))
    db.commit()

    assert db.query(PriceAlert).count() == 1
    db.delete(stock)
    db.commit()
    assert db.query(PriceAlert).count() == 0
```

- [ ] **Step 5: Run test**

```bash
cd backend && uv run pytest tests/test_models_price_alert.py -v
```
Expected: 2 passed (the test fixture `db` calls `Base.metadata.create_all()` so the table exists in the in-memory test DB).

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/price_alert.py backend/app/models/__init__.py backend/app/models/alert.py backend/tests/test_models_price_alert.py
git commit -m "$(cat <<'EOF'
feat(backend): add PriceAlert model + make Alert.rule_id nullable

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task A2: Alembic migration

**Files:**
- Create: `backend/alembic/versions/<auto>_add_price_alerts.py` (filename auto-generated)

- [ ] **Step 1: Generate migration skeleton**

```bash
cd backend && uv run alembic revision -m "add price alerts"
```

This creates `backend/alembic/versions/<hash>_add_price_alerts.py`. Verify `down_revision` points at the current head (most recent existing migration).

- [ ] **Step 2: Replace upgrade/downgrade**

Replace `upgrade()` body:
```python
def upgrade() -> None:
    """Upgrade schema."""
    # 1. Create price_alerts table
    op.create_table(
        "price_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("target_price", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_price_alerts_stock_id", "price_alerts", ["stock_id"])
    op.create_index("ix_price_alerts_enabled", "price_alerts", ["enabled"])

    # 2. Make alerts.rule_id nullable (SQLite needs batch_alter_table)
    with op.batch_alter_table("alerts", schema=None) as batch_op:
        batch_op.alter_column("rule_id", existing_type=sa.Integer(), nullable=True)
```

Replace `downgrade()` body:
```python
def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("alerts", schema=None) as batch_op:
        batch_op.alter_column("rule_id", existing_type=sa.Integer(), nullable=False)

    op.drop_index("ix_price_alerts_enabled", table_name="price_alerts")
    op.drop_index("ix_price_alerts_stock_id", table_name="price_alerts")
    op.drop_table("price_alerts")
```

Make sure `from alembic import op` and `import sqlalchemy as sa` are present at top.

- [ ] **Step 3: Apply migration**

```bash
cd backend && uv run alembic upgrade head
```
Expected: log line `Running upgrade ... -> <new_hash>, add price alerts`. No errors.

- [ ] **Step 4: Verify table + nullable**

```bash
cd backend && uv run python -c "
from app.core.db import engine
from sqlalchemy import inspect
ins = inspect(engine)
print('price_alerts:', 'price_alerts' in ins.get_table_names())
cols = {c['name']: c for c in ins.get_columns('alerts')}
print('alerts.rule_id nullable:', cols['rule_id']['nullable'])
"
```
Expected: `price_alerts: True`, `alerts.rule_id nullable: True`.

- [ ] **Step 5: Re-run A1 test**

```bash
cd backend && uv run pytest tests/test_models_price_alert.py -v
```
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/
git commit -m "$(cat <<'EOF'
feat(backend): alembic migration creating price_alerts + alerts.rule_id nullable

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Section B — Service layer

### Task B1: PriceAlertService (CRUD + edge-trigger evaluator)

**Files:**
- Create: `backend/app/services/price_alert_service.py`
- Test: `backend/tests/test_price_alert_service.py`

- [ ] **Step 1: Create the service**

`backend/app/services/price_alert_service.py`:
```python
"""CRUD + edge-trigger evaluator for price-target alerts."""
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, OhlcvDaily, PriceAlert


def list_for_stock(db: Session, stock_id: int) -> list[PriceAlert]:
    return list(
        db.execute(
            select(PriceAlert)
            .where(PriceAlert.stock_id == stock_id)
            .order_by(PriceAlert.created_at.desc())
        ).scalars()
    )


def create(
    db: Session,
    stock_id: int,
    target_price: float,
    direction: str,
    note: str | None = None,
) -> PriceAlert:
    if direction not in ("above", "below"):
        raise ValueError(f"direction must be 'above' or 'below', got {direction!r}")
    if target_price <= 0:
        raise ValueError(f"target_price must be positive, got {target_price}")
    pa = PriceAlert(
        stock_id=stock_id,
        target_price=target_price,
        direction=direction,
        note=note,
        enabled=True,
    )
    db.add(pa)
    db.commit()
    db.refresh(pa)
    return pa


def update(
    db: Session,
    alert_id: int,
    *,
    enabled: bool | None = None,
    target_price: float | None = None,
    direction: str | None = None,
    note: str | None = None,
) -> PriceAlert:
    pa = db.get(PriceAlert, alert_id)
    if pa is None:
        raise LookupError(f"price alert {alert_id} not found")
    reset_trigger = False
    if enabled is not None:
        pa.enabled = enabled
    if target_price is not None:
        if target_price <= 0:
            raise ValueError("target_price must be positive")
        pa.target_price = target_price
        reset_trigger = True
    if direction is not None:
        if direction not in ("above", "below"):
            raise ValueError(f"direction invalid: {direction!r}")
        pa.direction = direction
        reset_trigger = True
    if note is not None:
        pa.note = note
    if reset_trigger:
        pa.triggered_at = None
    db.commit()
    db.refresh(pa)
    return pa


def delete(db: Session, alert_id: int) -> None:
    pa = db.get(PriceAlert, alert_id)
    if pa is None:
        raise LookupError(f"price alert {alert_id} not found")
    db.delete(pa)
    db.commit()


def evaluate_all(db: Session) -> int:
    """Evaluate all enabled, not-yet-triggered price alerts. Fire Alert rows
    for those that crossed their target between prev_close and last_close.

    Returns: number of alerts fired.
    """
    pending = list(
        db.execute(
            select(PriceAlert)
            .where(PriceAlert.enabled.is_(True))
            .where(PriceAlert.triggered_at.is_(None))
        ).scalars()
    )
    fired = 0
    now = datetime.now(UTC)
    for pa in pending:
        bars = list(
            db.execute(
                select(OhlcvDaily)
                .where(OhlcvDaily.stock_id == pa.stock_id)
                .order_by(OhlcvDaily.date.desc())
                .limit(2)
            ).scalars()
        )
        if len(bars) < 2:
            continue
        last_close = float(bars[0].close)
        prev_close = float(bars[1].close)
        target = float(pa.target_price)

        crossed = False
        if pa.direction == "above" and prev_close <= target < last_close:
            crossed = True
        elif pa.direction == "below" and prev_close >= target > last_close:
            crossed = True

        if not crossed:
            continue

        snapshot = {
            "price_alert_id": pa.id,
            "target": target,
            "direction": pa.direction,
            "prev_close": prev_close,
            "last_close": last_close,
        }
        db.add(
            Alert(
                rule_id=None,
                stock_id=pa.stock_id,
                trigger_price=last_close,
                snapshot=json.dumps(snapshot),
            )
        )
        pa.triggered_at = now
        fired += 1

    if fired:
        db.commit()
    return fired
```

- [ ] **Step 2: Write tests**

`backend/tests/test_price_alert_service.py`:
```python
"""Tests for app.services.price_alert_service."""
import json
from datetime import date, timedelta

import pytest

from app.models import Alert, OhlcvDaily, PriceAlert, Stock
from app.services import price_alert_service


def _seed_stock_with_two_bars(db, ticker: str, prev_close: float, last_close: float) -> Stock:
    s = Stock(ticker=ticker, exchange="NMS", name=ticker)
    db.add(s)
    db.commit()
    today = date(2026, 5, 2)
    db.add(OhlcvDaily(
        stock_id=s.id, date=today - timedelta(days=1),
        open=prev_close, high=prev_close, low=prev_close, close=prev_close, volume=1_000_000,
    ))
    db.add(OhlcvDaily(
        stock_id=s.id, date=today,
        open=last_close, high=last_close, low=last_close, close=last_close, volume=1_000_000,
    ))
    db.commit()
    return s


def test_create_validates_direction(db):
    s = Stock(ticker="X", exchange="NMS", name="X")
    db.add(s); db.commit()
    with pytest.raises(ValueError):
        price_alert_service.create(db, s.id, 100.0, "sideways")


def test_create_validates_positive_price(db):
    s = Stock(ticker="X", exchange="NMS", name="X")
    db.add(s); db.commit()
    with pytest.raises(ValueError):
        price_alert_service.create(db, s.id, -10.0, "above")


def test_evaluate_above_fires_when_crossed(db):
    s = _seed_stock_with_two_bars(db, "T", prev_close=99.0, last_close=101.0)
    price_alert_service.create(db, s.id, 100.0, "above")
    fired = price_alert_service.evaluate_all(db)
    assert fired == 1
    alerts = db.query(Alert).all()
    assert len(alerts) == 1
    assert alerts[0].rule_id is None
    snap = json.loads(alerts[0].snapshot)
    assert snap["direction"] == "above"
    assert snap["target"] == 100.0
    pa = db.query(PriceAlert).first()
    assert pa.triggered_at is not None


def test_evaluate_below_fires_when_crossed(db):
    s = _seed_stock_with_two_bars(db, "T", prev_close=101.0, last_close=99.0)
    price_alert_service.create(db, s.id, 100.0, "below")
    fired = price_alert_service.evaluate_all(db)
    assert fired == 1


def test_evaluate_does_not_refire_already_triggered(db):
    s = _seed_stock_with_two_bars(db, "T", prev_close=99.0, last_close=101.0)
    pa = price_alert_service.create(db, s.id, 100.0, "above")
    price_alert_service.evaluate_all(db)
    fired_again = price_alert_service.evaluate_all(db)
    assert fired_again == 0
    assert db.query(Alert).count() == 1


def test_evaluate_skips_disabled(db):
    s = _seed_stock_with_two_bars(db, "T", prev_close=99.0, last_close=101.0)
    pa = price_alert_service.create(db, s.id, 100.0, "above")
    price_alert_service.update(db, pa.id, enabled=False)
    fired = price_alert_service.evaluate_all(db)
    assert fired == 0


def test_update_resets_triggered_when_target_changes(db):
    s = _seed_stock_with_two_bars(db, "T", prev_close=99.0, last_close=101.0)
    pa = price_alert_service.create(db, s.id, 100.0, "above")
    price_alert_service.evaluate_all(db)
    assert pa.triggered_at is not None
    updated = price_alert_service.update(db, pa.id, target_price=110.0)
    assert updated.triggered_at is None
```

- [ ] **Step 3: Run tests**

```bash
cd backend && uv run pytest tests/test_price_alert_service.py -v
```
Expected: 7 passed.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/price_alert_service.py backend/tests/test_price_alert_service.py
git commit -m "$(cat <<'EOF'
feat(backend): PriceAlertService with CRUD and edge-trigger evaluator (TDD)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task B2: StockDetailService (loader + indicators + effective_rules resolver)

**Files:**
- Create: `backend/app/services/stock_detail_service.py`
- Test: `backend/tests/test_stock_detail_service.py`

- [ ] **Step 1: Create the service**

`backend/app/services/stock_detail_service.py`:
```python
"""Aggregate stock detail: anagrafica + OHLCV (range-filtered) + indicators
+ KPIs + effective rules (resolved from Tier 1/Tier 2) + alerts history."""
import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.indicators.rsi import rsi as rsi_indicator
from app.indicators.sma import sma as sma_indicator
from app.models import Alert, OhlcvDaily, Rule, Stock, Watchlist, WatchlistItem


RANGE_DAYS: dict[str, int | None] = {
    "1m": 30, "3m": 90, "6m": 180, "1y": 365, "all": None,
}


@dataclass
class IndicatorPoint:
    date: date
    value: float | None


@dataclass
class EffectiveRule:
    kind: str
    enabled: bool
    params: dict[str, Any]
    source: str   # "tier1" | "tier2"
    watchlist_name: str | None


@dataclass
class StockKpis:
    last_close: float | None
    prev_close: float | None
    change_pct: float | None
    high_52w: float | None
    low_52w: float | None
    vol_avg_20: float | None
    vol_today: int | None
    vol_ratio: float | None


@dataclass
class StockDetail:
    stock: Stock
    ohlcv: list[OhlcvDaily]
    sma50: list[IndicatorPoint]
    sma200: list[IndicatorPoint]
    rsi14: list[IndicatorPoint]
    kpis: StockKpis
    effective_rules: list[EffectiveRule]
    alerts_history: list[Alert]


def _compute_indicator_series(
    bars: list[OhlcvDaily],
) -> tuple[list[IndicatorPoint], list[IndicatorPoint], list[IndicatorPoint]]:
    if len(bars) < 2:
        return [], [], []
    close = pd.Series([float(b.close) for b in bars])
    sma50_s = sma_indicator(close, 50)
    sma200_s = sma_indicator(close, 200)
    rsi_s = rsi_indicator(close, 14)

    def to_points(series: pd.Series) -> list[IndicatorPoint]:
        return [
            IndicatorPoint(
                date=bars[i].date,
                value=float(v) if not pd.isna(v) else None,
            )
            for i, v in enumerate(series)
        ]

    return to_points(sma50_s), to_points(sma200_s), to_points(rsi_s)


def _compute_kpis(bars: list[OhlcvDaily]) -> StockKpis:
    if not bars:
        return StockKpis(None, None, None, None, None, None, None, None)
    last = bars[-1]
    prev = bars[-2] if len(bars) >= 2 else None
    last_close = float(last.close)
    prev_close = float(prev.close) if prev else None
    change_pct = (
        ((last_close - prev_close) / prev_close * 100.0)
        if prev_close else None
    )
    window_252 = bars[-252:]
    high_52w = max(float(b.close) for b in window_252) if window_252 else None
    low_52w = min(float(b.close) for b in window_252) if window_252 else None
    last20 = bars[-20:]
    vol_avg_20 = (sum(int(b.volume) for b in last20) / len(last20)) if last20 else None
    vol_today = int(last.volume)
    vol_ratio = (vol_today / vol_avg_20) if vol_avg_20 and vol_avg_20 > 0 else None
    return StockKpis(
        last_close=last_close, prev_close=prev_close, change_pct=change_pct,
        high_52w=high_52w, low_52w=low_52w, vol_avg_20=vol_avg_20,
        vol_today=vol_today, vol_ratio=vol_ratio,
    )


def resolve_effective_rules(db: Session, stock_id: int) -> list[EffectiveRule]:
    """For each rule kind: find global Tier 1 rule, then check if any watchlist
    containing this stock has a Tier 2 override for that kind. Tier 2 wins.
    If multiple Tier 2 conflict (rare), most-restrictive wins (disabled > enabled)."""
    global_rules = list(
        db.execute(select(Rule).where(Rule.watchlist_id.is_(None))).scalars()
    )
    # Find all Tier 2 rules where the rule's watchlist contains this stock
    tier2 = list(
        db.execute(
            select(Rule, Watchlist.name)
            .join(WatchlistItem, WatchlistItem.watchlist_id == Rule.watchlist_id)
            .join(Watchlist, Watchlist.id == Rule.watchlist_id)
            .where(WatchlistItem.stock_id == stock_id)
            .where(Rule.watchlist_id.isnot(None))
        ).all()
    )
    # Build per-kind override (most restrictive wins)
    overrides: dict[str, tuple[Rule, str]] = {}
    for rule, wl_name in tier2:
        existing = overrides.get(rule.kind)
        if existing is None:
            overrides[rule.kind] = (rule, wl_name)
        else:
            existing_rule = existing[0]
            if not rule.enabled and existing_rule.enabled:
                overrides[rule.kind] = (rule, wl_name)

    out: list[EffectiveRule] = []
    for g in global_rules:
        ov = overrides.get(g.kind)
        if ov is not None:
            r, wl_name = ov
            out.append(EffectiveRule(
                kind=r.kind, enabled=r.enabled,
                params=json.loads(r.params or "{}"),
                source="tier2", watchlist_name=wl_name,
            ))
        else:
            out.append(EffectiveRule(
                kind=g.kind, enabled=g.enabled,
                params=json.loads(g.params or "{}"),
                source="tier1", watchlist_name=None,
            ))
    return out


def get_detail(db: Session, ticker: str, range_key: str = "1y") -> StockDetail | None:
    stock = db.execute(select(Stock).where(Stock.ticker == ticker)).scalar_one_or_none()
    if stock is None:
        return None

    days = RANGE_DAYS.get(range_key, 365)
    bars_q = (
        select(OhlcvDaily)
        .where(OhlcvDaily.stock_id == stock.id)
        .order_by(OhlcvDaily.date.asc())
    )
    bars = list(db.execute(bars_q).scalars())
    # Indicator computation needs full history; filter only the OHLCV view
    if days is not None:
        cutoff = bars[-1].date - timedelta(days=days) if bars else None
        ohlcv_view = [b for b in bars if cutoff is None or b.date >= cutoff]
    else:
        ohlcv_view = bars

    sma50, sma200, rsi14 = _compute_indicator_series(bars)
    # Slice indicators to match ohlcv_view
    if days is not None and bars:
        cutoff_idx = len(bars) - len(ohlcv_view)
        sma50 = sma50[cutoff_idx:]
        sma200 = sma200[cutoff_idx:]
        rsi14 = rsi14[cutoff_idx:]

    kpis = _compute_kpis(bars)
    effective_rules = resolve_effective_rules(db, stock.id)
    alerts_history = list(
        db.execute(
            select(Alert)
            .where(Alert.stock_id == stock.id)
            .order_by(Alert.triggered_at.desc())
            .limit(50)
        ).scalars()
    )
    return StockDetail(
        stock=stock,
        ohlcv=ohlcv_view,
        sma50=sma50, sma200=sma200, rsi14=rsi14,
        kpis=kpis,
        effective_rules=effective_rules,
        alerts_history=alerts_history,
    )
```

- [ ] **Step 2: Write tests**

`backend/tests/test_stock_detail_service.py`:
```python
"""Tests for stock_detail_service."""
import json
from datetime import date, timedelta

from app.models import OhlcvDaily, Rule, Stock, Watchlist, WatchlistItem
from app.services import stock_detail_service


def _seed_stock_full(db, ticker: str = "AAPL", n_bars: int = 250) -> Stock:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=f"{ticker} Inc",
              sector="Technology", country="US", currency="USD")
    db.add(s); db.commit()
    today = date(2026, 5, 2)
    for i in range(n_bars):
        d = today - timedelta(days=n_bars - 1 - i)
        c = 100.0 + 0.1 * i
        db.add(OhlcvDaily(
            stock_id=s.id, date=d,
            open=c - 0.5, high=c + 0.5, low=c - 1.0, close=c, volume=1_000_000,
        ))
    db.commit()
    return s


def test_get_detail_returns_none_for_missing_ticker(db):
    assert stock_detail_service.get_detail(db, "MISSING") is None


def test_get_detail_full_payload(db):
    s = _seed_stock_full(db, n_bars=250)
    d = stock_detail_service.get_detail(db, s.ticker, range_key="1y")
    assert d is not None
    assert d.stock.ticker == "AAPL"
    assert len(d.ohlcv) > 0
    assert d.kpis.last_close is not None
    assert d.kpis.high_52w is not None
    # Indicators computed
    assert any(p.value is not None for p in d.sma50)
    assert any(p.value is not None for p in d.rsi14)


def test_get_detail_range_filter_1m(db):
    s = _seed_stock_full(db, n_bars=250)
    d = stock_detail_service.get_detail(db, s.ticker, range_key="1m")
    assert d is not None
    # 1m = ~30 days, give some leeway for weekends
    assert 28 <= len(d.ohlcv) <= 32


def test_resolve_effective_rules_tier1_only(db):
    s = _seed_stock_full(db, n_bars=10)
    db.add(Rule(watchlist_id=None, kind="rsi_oversold", params='{"threshold":30}', enabled=True))
    db.add(Rule(watchlist_id=None, kind="death_cross", params='{}', enabled=True))
    db.commit()

    rules = stock_detail_service.resolve_effective_rules(db, s.id)
    assert len(rules) == 2
    kinds = {r.kind: r for r in rules}
    assert kinds["rsi_oversold"].source == "tier1"
    assert kinds["rsi_oversold"].enabled is True


def test_resolve_effective_rules_tier2_override(db):
    s = _seed_stock_full(db, n_bars=10)
    # Create user + watchlist + add stock
    from app.models import User
    u = User(username="admin", password_hash="x")
    db.add(u); db.commit()
    wl = Watchlist(name="Tech", user_id=u.id)
    db.add(wl); db.commit()
    db.add(WatchlistItem(watchlist_id=wl.id, stock_id=s.id))
    # Tier 1 enabled
    db.add(Rule(watchlist_id=None, kind="rsi_oversold", params='{}', enabled=True))
    # Tier 2 disabled override for the watchlist that contains the stock
    db.add(Rule(watchlist_id=wl.id, kind="rsi_oversold", params='{}', enabled=False))
    db.commit()

    rules = stock_detail_service.resolve_effective_rules(db, s.id)
    rsi = next(r for r in rules if r.kind == "rsi_oversold")
    assert rsi.source == "tier2"
    assert rsi.enabled is False
    assert rsi.watchlist_name == "Tech"
```

- [ ] **Step 3: Run tests**

```bash
cd backend && uv run pytest tests/test_stock_detail_service.py -v
```
Expected: 5 passed.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/stock_detail_service.py backend/tests/test_stock_detail_service.py
git commit -m "$(cat <<'EOF'
feat(backend): StockDetailService loader + effective_rules resolver (TDD)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task B3: StockNewsService (yfinance wrapper + cache)

**Files:**
- Create: `backend/app/services/stock_news_service.py`
- Test: `backend/tests/test_stock_news_service.py`

- [ ] **Step 1: Create the service**

`backend/app/services/stock_news_service.py`:
```python
"""yfinance news wrapper with in-memory TTL cache."""
from datetime import UTC, datetime, timedelta
from typing import Any

from loguru import logger

NEWS_TTL = timedelta(hours=1)
_CACHE: dict[str, tuple[datetime, list[dict[str, Any]]]] = {}


def _normalize_yf_item(raw: dict) -> dict[str, Any] | None:
    """yfinance.Ticker.news returns dicts of varying shape across versions.
    Normalize to {title, link, publisher, published_at: ISO8601 str | None}."""
    title = raw.get("title")
    link = raw.get("link") or raw.get("url")
    publisher = raw.get("publisher") or raw.get("source")
    ts = raw.get("providerPublishTime") or raw.get("publish_time")
    if not title or not link:
        return None
    published_at = (
        datetime.fromtimestamp(ts, tz=UTC).isoformat() if isinstance(ts, (int, float)) else None
    )
    return {
        "title": str(title),
        "link": str(link),
        "publisher": str(publisher) if publisher else "Unknown",
        "published_at": published_at,
    }


def get_news(ticker: str, limit: int = 5) -> list[dict[str, Any]]:
    """Fetch news for a ticker. Cached for 1h. Returns [] on any error."""
    now = datetime.now(UTC)
    cached = _CACHE.get(ticker)
    if cached and (now - cached[0]) < NEWS_TTL:
        return cached[1][:limit]
    try:
        import yfinance as yf
        raw_items = yf.Ticker(ticker).news or []
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[news] yfinance fetch failed for {ticker}: {exc}")
        # Cache empty result to avoid hammering on failure
        _CACHE[ticker] = (now, [])
        return []
    normalized = [n for raw in raw_items if (n := _normalize_yf_item(raw))]
    _CACHE[ticker] = (now, normalized)
    return normalized[:limit]


def clear_cache() -> None:
    """For tests."""
    _CACHE.clear()
```

- [ ] **Step 2: Write tests**

`backend/tests/test_stock_news_service.py`:
```python
"""Tests for stock_news_service."""
from datetime import UTC, datetime, timedelta

from app.services import stock_news_service


def test_normalize_handles_complete_item():
    raw = {
        "title": "Apple beats Q3",
        "link": "https://example.com/news/123",
        "publisher": "Reuters",
        "providerPublishTime": 1714694400,
    }
    n = stock_news_service._normalize_yf_item(raw)
    assert n is not None
    assert n["title"] == "Apple beats Q3"
    assert n["publisher"] == "Reuters"
    assert n["published_at"] is not None


def test_normalize_skips_missing_title_or_link():
    assert stock_news_service._normalize_yf_item({"link": "x"}) is None
    assert stock_news_service._normalize_yf_item({"title": "x"}) is None


def test_get_news_cache_hit(monkeypatch):
    stock_news_service.clear_cache()
    calls: list[str] = []

    class FakeTicker:
        def __init__(self, t): self._t = t
        @property
        def news(self):
            calls.append(self._t)
            return [{"title": "T", "link": "L", "publisher": "P", "providerPublishTime": 1}]

    fake_module = type("M", (), {"Ticker": FakeTicker})
    monkeypatch.setitem(__import__("sys").modules, "yfinance", fake_module)

    a = stock_news_service.get_news("AAPL")
    b = stock_news_service.get_news("AAPL")
    assert len(a) == 1 and len(b) == 1
    assert calls == ["AAPL"]   # cached on second call


def test_get_news_fallback_on_yfinance_error(monkeypatch):
    stock_news_service.clear_cache()

    class BoomTicker:
        def __init__(self, t): pass
        @property
        def news(self):
            raise RuntimeError("network down")

    fake_module = type("M", (), {"Ticker": BoomTicker})
    monkeypatch.setitem(__import__("sys").modules, "yfinance", fake_module)

    items = stock_news_service.get_news("AAPL")
    assert items == []
```

- [ ] **Step 3: Run tests**

```bash
cd backend && uv run pytest tests/test_stock_news_service.py -v
```
Expected: 4 passed.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/stock_news_service.py backend/tests/test_stock_news_service.py
git commit -m "$(cat <<'EOF'
feat(backend): StockNewsService with TTL cache + graceful yfinance fallback (TDD)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task B4: SpotlightService + stats_service helper

**Files:**
- Modify: `backend/app/services/stats_service.py` (add helper)
- Create: `backend/app/services/spotlight_service.py`
- Test: `backend/tests/test_spotlight_service.py`

- [ ] **Step 1: Add helper to `stats_service.py`**

Append at the end of the file:
```python
def get_top_alerted_stock_7d(db: Session) -> tuple[Stock, int] | None:
    """Top 1 stock by alert count in last 7 days. Returns (stock, count) or None.
    Excludes archived alerts."""
    from datetime import UTC, datetime, timedelta
    from sqlalchemy import func, select
    from app.models import Alert, Stock as StockModel

    cutoff = datetime.now(UTC) - timedelta(days=7)
    row = db.execute(
        select(StockModel, func.count(Alert.id).label("cnt"))
        .join(Alert, Alert.stock_id == StockModel.id)
        .where(Alert.triggered_at >= cutoff)
        .where(Alert.archived_at.is_(None))
        .group_by(StockModel.id)
        .order_by(func.count(Alert.id).desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    return (row[0], int(row[1]))
```

(Note: existing `stats_service.py` already imports Session and Stock at module level — this helper uses local imports for clarity. If the linter complains about unused module imports later, those are pre-existing concerns.)

- [ ] **Step 2: Create `spotlight_service.py`**

`backend/app/services/spotlight_service.py`:
```python
"""Build the 3 spotlight cards for the HomePage dashboard:
- 1x top_gainer (from market snapshot movers.gainers[0])
- 1x most_alerted_7d (from stats_service helper)
- 1x vol_spike (from market snapshot movers.volume_spikes[0])
Each card includes a sparkline (last 30 close)."""
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OhlcvDaily, Stock
from app.services import market_stats_service, stats_service


SPARKLINE_LEN = 30


def _sparkline(db: Session, stock_id: int) -> list[float]:
    bars = list(
        db.execute(
            select(OhlcvDaily)
            .where(OhlcvDaily.stock_id == stock_id)
            .order_by(OhlcvDaily.date.desc())
            .limit(SPARKLINE_LEN)
        ).scalars()
    )
    return [float(b.close) for b in reversed(bars)]


def _stock_id_by_ticker(db: Session, ticker: str) -> int | None:
    s = db.execute(select(Stock).where(Stock.ticker == ticker)).scalar_one_or_none()
    return s.id if s else None


def build(db: Session) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    snap = market_stats_service.get_latest_snapshot(db)
    payload: dict[str, Any] = {}
    if snap is not None:
        try:
            payload = json.loads(snap.payload)
        except Exception:
            payload = {}

    # 1) Top gainer from snapshot
    movers = payload.get("movers", {}) if payload else {}
    gainers = movers.get("gainers", [])
    if gainers:
        top = gainers[0]
        sid = _stock_id_by_ticker(db, top["ticker"])
        cards.append({
            "type": "top_gainer",
            "ticker": top["ticker"],
            "change_pct": top.get("change_pct"),
            "last_close": top.get("last_close"),
            "sparkline": _sparkline(db, sid) if sid else [],
        })

    # 2) Most alerted in last 7 days
    most_alerted = stats_service.get_top_alerted_stock_7d(db)
    if most_alerted is not None:
        stock, count = most_alerted
        bars = _sparkline(db, stock.id)
        cards.append({
            "type": "most_alerted_7d",
            "ticker": stock.ticker,
            "alerts_count": count,
            "last_close": bars[-1] if bars else None,
            "sparkline": bars,
        })

    # 3) Volume spike from snapshot
    vol_spikes = movers.get("volume_spikes", [])
    if vol_spikes:
        v = vol_spikes[0]
        sid = _stock_id_by_ticker(db, v["ticker"])
        cards.append({
            "type": "vol_spike",
            "ticker": v["ticker"],
            "vol_ratio": v.get("vol_ratio"),
            "last_close": v.get("last_close"),
            "sparkline": _sparkline(db, sid) if sid else [],
        })

    return cards
```

- [ ] **Step 3: Write tests**

`backend/tests/test_spotlight_service.py`:
```python
"""Tests for spotlight_service + stats_service.get_top_alerted_stock_7d."""
import json
from datetime import UTC, date, datetime, timedelta

from app.models import Alert, MarketSnapshot, OhlcvDaily, Rule, Stock
from app.services import spotlight_service, stats_service


def _seed_stock(db, ticker: str, n_bars: int = 30) -> Stock:
    s = Stock(ticker=ticker, exchange="NMS", name=ticker)
    db.add(s); db.commit()
    today = date(2026, 5, 2)
    for i in range(n_bars):
        d = today - timedelta(days=n_bars - 1 - i)
        c = 100.0 + i
        db.add(OhlcvDaily(stock_id=s.id, date=d,
                          open=c, high=c, low=c, close=c, volume=1_000_000))
    db.commit()
    return s


def test_top_alerted_7d_empty(db):
    assert stats_service.get_top_alerted_stock_7d(db) is None


def test_top_alerted_7d_returns_winner(db):
    s1 = _seed_stock(db, "A")
    s2 = _seed_stock(db, "B")
    rule = Rule(watchlist_id=None, kind="rsi_oversold", params="{}", enabled=True)
    db.add(rule); db.commit()
    now = datetime.now(UTC)
    for _ in range(5):
        db.add(Alert(rule_id=rule.id, stock_id=s1.id, trigger_price=100.0,
                     snapshot="{}", triggered_at=now - timedelta(hours=1)))
    for _ in range(2):
        db.add(Alert(rule_id=rule.id, stock_id=s2.id, trigger_price=100.0,
                     snapshot="{}", triggered_at=now - timedelta(hours=1)))
    db.commit()
    result = stats_service.get_top_alerted_stock_7d(db)
    assert result is not None
    stock, count = result
    assert stock.ticker == "A"
    assert count == 5


def test_build_spotlight_with_snapshot_and_alerts(db):
    s1 = _seed_stock(db, "NVDA")
    s2 = _seed_stock(db, "AAPL")
    s3 = _seed_stock(db, "PLTR")
    # Snapshot with gainers + vol_spikes
    payload = {
        "movers": {
            "gainers": [{"ticker": "NVDA", "change_pct": 4.2, "last_close": 880.0}],
            "volume_spikes": [{"ticker": "PLTR", "vol_ratio": 3.2, "last_close": 28.5}],
            "losers": [], "new_52w_high": [], "new_52w_low": [],
        }
    }
    db.merge(MarketSnapshot(
        id=1, computed_at=datetime.now(UTC),
        stocks_total=3, stocks_with_data=3, payload=json.dumps(payload),
    ))
    # Alert on AAPL
    rule = Rule(watchlist_id=None, kind="rsi_oversold", params="{}", enabled=True)
    db.add(rule); db.commit()
    db.add(Alert(rule_id=rule.id, stock_id=s2.id, trigger_price=170.0,
                 snapshot="{}", triggered_at=datetime.now(UTC) - timedelta(hours=1)))
    db.commit()

    cards = spotlight_service.build(db)
    types = {c["type"] for c in cards}
    assert "top_gainer" in types
    assert "most_alerted_7d" in types
    assert "vol_spike" in types
    by_type = {c["type"]: c for c in cards}
    assert by_type["top_gainer"]["ticker"] == "NVDA"
    assert by_type["most_alerted_7d"]["ticker"] == "AAPL"
    assert by_type["vol_spike"]["ticker"] == "PLTR"
    # Sparkline populated
    assert len(by_type["top_gainer"]["sparkline"]) > 0


def test_build_spotlight_no_snapshot(db):
    cards = spotlight_service.build(db)
    assert cards == []   # no snapshot → no movers → no gainer/vol_spike, no alerts → no most_alerted
```

- [ ] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/test_spotlight_service.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/stats_service.py backend/app/services/spotlight_service.py backend/tests/test_spotlight_service.py
git commit -m "$(cat <<'EOF'
feat(backend): SpotlightService + get_top_alerted_stock_7d helper (TDD)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Section C — API endpoints + scan_runner integration

### Task C1: Pydantic schemas

**Files:**
- Create: `backend/app/schemas/stock_detail.py`
- Create: `backend/app/schemas/price_alert.py`
- Create: `backend/app/schemas/spotlight.py`

- [ ] **Step 1: Create `backend/app/schemas/stock_detail.py`**

```python
"""Pydantic schemas for /api/stocks/{ticker}/detail and /news."""
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.alert import AlertOut
from app.schemas.stock import StockOut


class OhlcvBarOut(BaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


class IndicatorPointOut(BaseModel):
    date: date
    value: float | None


class IndicatorSeriesOut(BaseModel):
    sma50: list[IndicatorPointOut]
    sma200: list[IndicatorPointOut]
    rsi14: list[IndicatorPointOut]


class StockKpisOut(BaseModel):
    last_close: float | None
    prev_close: float | None
    change_pct: float | None
    high_52w: float | None
    low_52w: float | None
    vol_avg_20: float | None
    vol_today: int | None
    vol_ratio: float | None


class EffectiveRuleOut(BaseModel):
    kind: str
    enabled: bool
    params: dict[str, Any]
    source: str
    watchlist_name: str | None


class StockDetailOut(BaseModel):
    stock: StockOut
    ohlcv: list[OhlcvBarOut]
    indicators: IndicatorSeriesOut
    kpis: StockKpisOut
    effective_rules: list[EffectiveRuleOut]
    alerts_history: list[AlertOut]


class StockNewsItemOut(BaseModel):
    title: str
    link: str
    publisher: str
    published_at: str | None


class StockNewsOut(BaseModel):
    items: list[StockNewsItemOut]
```

- [ ] **Step 2: Create `backend/app/schemas/price_alert.py`**

```python
"""Pydantic schemas for /api/.../price-alerts."""
from datetime import datetime

from pydantic import BaseModel, Field


class PriceAlertOut(BaseModel):
    id: int
    stock_id: int
    target_price: float
    direction: str
    enabled: bool
    note: str | None
    triggered_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PriceAlertCreate(BaseModel):
    target_price: float = Field(gt=0)
    direction: str = Field(pattern=r"^(above|below)$")
    note: str | None = Field(default=None, max_length=255)


class PriceAlertUpdate(BaseModel):
    enabled: bool | None = None
    target_price: float | None = Field(default=None, gt=0)
    direction: str | None = Field(default=None, pattern=r"^(above|below)$")
    note: str | None = Field(default=None, max_length=255)
```

- [ ] **Step 3: Create `backend/app/schemas/spotlight.py`**

```python
"""Pydantic schemas for /api/dashboard/spotlight."""
from typing import Literal

from pydantic import BaseModel


class SpotlightCardOut(BaseModel):
    type: Literal["top_gainer", "most_alerted_7d", "vol_spike"]
    ticker: str
    last_close: float | None = None
    sparkline: list[float] = []
    # Type-specific optional fields:
    change_pct: float | None = None
    vol_ratio: float | None = None
    alerts_count: int | None = None


class SpotlightOut(BaseModel):
    cards: list[SpotlightCardOut]
```

- [ ] **Step 4: Verify import**

```bash
cd backend && uv run python -c "
from app.schemas.stock_detail import StockDetailOut, StockNewsOut, OhlcvBarOut
from app.schemas.price_alert import PriceAlertOut, PriceAlertCreate, PriceAlertUpdate
from app.schemas.spotlight import SpotlightOut, SpotlightCardOut
print('OK')
"
```
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/stock_detail.py backend/app/schemas/price_alert.py backend/app/schemas/spotlight.py
git commit -m "$(cat <<'EOF'
feat(backend): Pydantic schemas for stock detail + price alerts + spotlight

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task C2: Stock detail + news endpoints

**Files:**
- Modify: `backend/app/api/stocks.py`
- Test: `backend/tests/test_api_stock_detail.py`
- Test: `backend/tests/test_api_stock_news.py`

- [ ] **Step 1: Extend `backend/app/api/stocks.py`**

Read the current file. Add imports:
```python
from app.api.deps import get_current_user, get_db
from app.schemas.stock_detail import (
    EffectiveRuleOut, IndicatorPointOut, IndicatorSeriesOut, OhlcvBarOut,
    StockDetailOut, StockKpisOut, StockNewsItemOut, StockNewsOut,
)
from app.services import stock_detail_service, stock_news_service
from app.schemas.alert import AlertOut
```

Append to the end of the file:
```python
@router.get("/{ticker}/detail", response_model=StockDetailOut)
def get_stock_detail(
    ticker: str,
    range: str = "1y",
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> StockDetailOut:
    if range not in ("1m", "3m", "6m", "1y", "all"):
        raise HTTPException(status_code=422, detail="invalid range")
    detail = stock_detail_service.get_detail(db, ticker, range_key=range)
    if detail is None:
        raise HTTPException(status_code=404, detail="Ticker not found")
    return StockDetailOut(
        stock=StockOut.model_validate(detail.stock),
        ohlcv=[
            OhlcvBarOut(
                date=b.date, open=float(b.open), high=float(b.high),
                low=float(b.low), close=float(b.close), volume=int(b.volume),
            )
            for b in detail.ohlcv
        ],
        indicators=IndicatorSeriesOut(
            sma50=[IndicatorPointOut(date=p.date, value=p.value) for p in detail.sma50],
            sma200=[IndicatorPointOut(date=p.date, value=p.value) for p in detail.sma200],
            rsi14=[IndicatorPointOut(date=p.date, value=p.value) for p in detail.rsi14],
        ),
        kpis=StockKpisOut(
            last_close=detail.kpis.last_close, prev_close=detail.kpis.prev_close,
            change_pct=detail.kpis.change_pct,
            high_52w=detail.kpis.high_52w, low_52w=detail.kpis.low_52w,
            vol_avg_20=detail.kpis.vol_avg_20, vol_today=detail.kpis.vol_today,
            vol_ratio=detail.kpis.vol_ratio,
        ),
        effective_rules=[
            EffectiveRuleOut(
                kind=r.kind, enabled=r.enabled, params=r.params,
                source=r.source, watchlist_name=r.watchlist_name,
            )
            for r in detail.effective_rules
        ],
        alerts_history=[
            AlertOut(
                id=a.id, rule_id=a.rule_id, rule_kind=None,
                stock_id=a.stock_id, ticker=detail.stock.ticker,
                triggered_at=a.triggered_at, trigger_price=float(a.trigger_price),
                snapshot=__import__("json").loads(a.snapshot or "{}"),
                read_at=a.read_at, archived_at=a.archived_at,
            )
            for a in detail.alerts_history
        ],
    )


@router.get("/{ticker}/news", response_model=StockNewsOut)
def get_stock_news(
    ticker: str,
    limit: int = 5,
    _user: User = Depends(get_current_user),
) -> StockNewsOut:
    if limit < 1 or limit > 20:
        raise HTTPException(status_code=422, detail="limit must be 1..20")
    items = stock_news_service.get_news(ticker, limit=limit)
    return StockNewsOut(items=[StockNewsItemOut(**n) for n in items])
```

- [ ] **Step 2: Write detail tests**

`backend/tests/test_api_stock_detail.py`:
```python
"""Smoke tests for /api/stocks/{ticker}/detail."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import OhlcvDaily, Stock, User


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user); db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed(db, ticker="AAPL", n_bars=250):
    s = Stock(ticker=ticker, exchange="NASDAQ", name=f"{ticker} Inc",
              sector="Technology", country="US")
    db.add(s); db.commit()
    today = date(2026, 5, 2)
    for i in range(n_bars):
        d = today - timedelta(days=n_bars - 1 - i)
        c = 100.0 + 0.1 * i
        db.add(OhlcvDaily(stock_id=s.id, date=d,
                          open=c, high=c+0.5, low=c-0.5, close=c, volume=1_000_000))
    db.commit()
    return s


def test_detail_requires_auth(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as c:
            r = c.get("/api/stocks/AAPL/detail")
            assert r.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_detail_404_unknown_ticker(client):
    r = client.get("/api/stocks/MISSING/detail")
    assert r.status_code == 404


def test_detail_payload_shape(client, db):
    _seed(db)
    r = client.get("/api/stocks/AAPL/detail")
    assert r.status_code == 200
    body = r.json()
    for k in ("stock", "ohlcv", "indicators", "kpis", "effective_rules", "alerts_history"):
        assert k in body
    assert body["stock"]["ticker"] == "AAPL"
    assert len(body["ohlcv"]) > 0
    assert "sma50" in body["indicators"]


def test_detail_invalid_range_422(client, db):
    _seed(db)
    r = client.get("/api/stocks/AAPL/detail?range=2y")
    assert r.status_code == 422
```

- [ ] **Step 3: Write news tests**

`backend/tests/test_api_stock_news.py`:
```python
"""Smoke tests for /api/stocks/{ticker}/news."""
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import User
from app.services import stock_news_service


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user); db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_news_requires_auth(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as c:
            r = c.get("/api/stocks/AAPL/news")
            assert r.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_news_returns_normalized(client, monkeypatch):
    stock_news_service.clear_cache()

    class FakeTicker:
        def __init__(self, t): pass
        @property
        def news(self):
            return [
                {"title": "T1", "link": "L1", "publisher": "P1", "providerPublishTime": 1714694400},
                {"title": "T2", "link": "L2", "publisher": "P2", "providerPublishTime": 1714780800},
            ]

    fake_module = type("M", (), {"Ticker": FakeTicker})
    monkeypatch.setitem(sys.modules, "yfinance", fake_module)

    r = client.get("/api/stocks/AAPL/news?limit=2")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 2
    assert body["items"][0]["title"] == "T1"
```

- [ ] **Step 4: Run both test files**

```bash
cd backend && uv run pytest tests/test_api_stock_detail.py tests/test_api_stock_news.py -v
```
Expected: 6 passed (4 detail + 2 news).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/stocks.py backend/tests/test_api_stock_detail.py backend/tests/test_api_stock_news.py
git commit -m "$(cat <<'EOF'
feat(backend): /api/stocks/{ticker}/detail + /news endpoints (TDD)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task C3: Price alerts CRUD endpoints

**Files:**
- Create: `backend/app/api/price_alerts.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_api_price_alerts.py`

- [ ] **Step 1: Create `backend/app/api/price_alerts.py`**

```python
"""Price-target alerts CRUD."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import PriceAlert, Stock, User
from app.schemas.price_alert import PriceAlertCreate, PriceAlertOut, PriceAlertUpdate
from app.services import price_alert_service

router = APIRouter(tags=["price-alerts"])


def _stock_id_or_404(db: Session, ticker: str) -> int:
    s = db.execute(select(Stock).where(Stock.ticker == ticker)).scalar_one_or_none()
    if s is None:
        raise HTTPException(status_code=404, detail="Ticker not found")
    return s.id


@router.get("/api/stocks/{ticker}/price-alerts", response_model=list[PriceAlertOut])
def list_price_alerts(
    ticker: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[PriceAlertOut]:
    stock_id = _stock_id_or_404(db, ticker)
    rows = price_alert_service.list_for_stock(db, stock_id)
    return [PriceAlertOut.model_validate(r, from_attributes=True) for r in rows]


@router.post(
    "/api/stocks/{ticker}/price-alerts",
    response_model=PriceAlertOut,
    status_code=201,
)
def create_price_alert(
    ticker: str,
    body: PriceAlertCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> PriceAlertOut:
    stock_id = _stock_id_or_404(db, ticker)
    try:
        pa = price_alert_service.create(
            db, stock_id, target_price=body.target_price,
            direction=body.direction, note=body.note,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return PriceAlertOut.model_validate(pa, from_attributes=True)


@router.patch("/api/price-alerts/{alert_id}", response_model=PriceAlertOut)
def update_price_alert(
    alert_id: int,
    body: PriceAlertUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> PriceAlertOut:
    try:
        pa = price_alert_service.update(
            db, alert_id,
            enabled=body.enabled, target_price=body.target_price,
            direction=body.direction, note=body.note,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Price alert not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return PriceAlertOut.model_validate(pa, from_attributes=True)


@router.delete("/api/price-alerts/{alert_id}", status_code=204)
def delete_price_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> None:
    try:
        price_alert_service.delete(db, alert_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Price alert not found")
```

- [ ] **Step 2: Register router in `backend/app/main.py`**

Read the file. Add import (alphabetical):
```python
from app.api import price_alerts as price_alerts_router
```
Add registration line after existing routers:
```python
app.include_router(price_alerts_router.router)
```

- [ ] **Step 3: Write tests**

`backend/tests/test_api_price_alerts.py`:
```python
"""Smoke tests for price-alerts CRUD endpoints."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Stock, User


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    s = Stock(ticker="AAPL", exchange="NASDAQ", name="Apple")
    db.add_all([user, s]); db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_create_list_update_delete_flow(client):
    # Create
    r = client.post("/api/stocks/AAPL/price-alerts",
                    json={"target_price": 200.0, "direction": "above", "note": "resistance"})
    assert r.status_code == 201, r.text
    pa = r.json()
    pa_id = pa["id"]
    assert pa["direction"] == "above"

    # List
    r = client.get("/api/stocks/AAPL/price-alerts")
    assert r.status_code == 200
    assert len(r.json()) == 1

    # Update
    r = client.patch(f"/api/price-alerts/{pa_id}", json={"enabled": False})
    assert r.status_code == 200
    assert r.json()["enabled"] is False

    # Delete
    r = client.delete(f"/api/price-alerts/{pa_id}")
    assert r.status_code == 204
    r = client.get("/api/stocks/AAPL/price-alerts")
    assert r.json() == []


def test_create_validates_direction(client):
    r = client.post("/api/stocks/AAPL/price-alerts",
                    json={"target_price": 200.0, "direction": "sideways"})
    assert r.status_code == 422


def test_create_validates_positive_price(client):
    r = client.post("/api/stocks/AAPL/price-alerts",
                    json={"target_price": -10.0, "direction": "above"})
    assert r.status_code == 422


def test_404_unknown_ticker(client):
    r = client.post("/api/stocks/MISSING/price-alerts",
                    json={"target_price": 100.0, "direction": "above"})
    assert r.status_code == 404


def test_update_404(client):
    r = client.patch("/api/price-alerts/9999", json={"enabled": True})
    assert r.status_code == 404
```

- [ ] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/test_api_price_alerts.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/price_alerts.py backend/app/main.py backend/tests/test_api_price_alerts.py
git commit -m "$(cat <<'EOF'
feat(backend): /api/.../price-alerts CRUD endpoints (TDD)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task C4: Spotlight endpoint

**Files:**
- Create: `backend/app/api/spotlight.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_api_spotlight.py`

- [ ] **Step 1: Create the router**

`backend/app/api/spotlight.py`:
```python
"""GET /api/dashboard/spotlight — 3 cards for HomePage."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import User
from app.schemas.spotlight import SpotlightCardOut, SpotlightOut
from app.services import spotlight_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/spotlight", response_model=SpotlightOut)
def get_spotlight(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> SpotlightOut:
    cards_raw = spotlight_service.build(db)
    cards = [SpotlightCardOut(**c) for c in cards_raw]
    return SpotlightOut(cards=cards)
```

- [ ] **Step 2: Register router in `backend/app/main.py`**

Add import: `from app.api import spotlight as spotlight_router` and registration `app.include_router(spotlight_router.router)`.

- [ ] **Step 3: Write tests**

`backend/tests/test_api_spotlight.py`:
```python
"""Smoke tests for /api/dashboard/spotlight."""
import json
from datetime import UTC, datetime, timedelta
from datetime import date as date_cls

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Alert, MarketSnapshot, OhlcvDaily, Rule, Stock, User


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user); db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_requires_auth(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as c:
            r = c.get("/api/dashboard/spotlight")
            assert r.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_spotlight_empty(client):
    r = client.get("/api/dashboard/spotlight")
    assert r.status_code == 200
    assert r.json() == {"cards": []}


def test_spotlight_with_data(client, db):
    s = Stock(ticker="NVDA", exchange="NASDAQ", name="Nvidia")
    db.add(s); db.commit()
    today = date_cls(2026, 5, 2)
    for i in range(30):
        c = 800.0 + i
        db.add(OhlcvDaily(stock_id=s.id, date=today - timedelta(days=29 - i),
                          open=c, high=c, low=c, close=c, volume=1_000_000))
    db.add(MarketSnapshot(
        id=1, computed_at=datetime.now(UTC), stocks_total=1, stocks_with_data=1,
        payload=json.dumps({"movers": {
            "gainers": [{"ticker": "NVDA", "change_pct": 4.2, "last_close": 829.0}],
            "volume_spikes": [], "losers": [], "new_52w_high": [], "new_52w_low": [],
        }}),
    ))
    db.commit()

    r = client.get("/api/dashboard/spotlight")
    assert r.status_code == 200
    cards = r.json()["cards"]
    assert any(c["type"] == "top_gainer" and c["ticker"] == "NVDA" for c in cards)
```

- [ ] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/test_api_spotlight.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/spotlight.py backend/app/main.py backend/tests/test_api_spotlight.py
git commit -m "$(cat <<'EOF'
feat(backend): /api/dashboard/spotlight endpoint (TDD)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task C5: Wire price_alert evaluator into scan_runner (non-fatal)

**Files:**
- Modify: `backend/app/services/scan_runner.py`
- Test: append to `backend/tests/test_price_alert_service.py`

- [ ] **Step 1: Modify `scan_runner.py`**

Find the existing block in `run_tracked_scan` that calls `market_stats_service.recompute_snapshot` (added in Fase 3A-bis). It looks like:
```python
        # Recompute market dashboard snapshot — non-fatal, alert pipeline succeeded already.
        try:
            from app.services import market_stats_service

            market_stats_service.recompute_snapshot(db, scan_run_id=run.id)
            logger.info(f"[scan_runner] market snapshot refreshed for ScanRun {run.id}")
        except Exception as snap_exc:  # noqa: BLE001
            logger.warning(f"[scan_runner] snapshot recompute failed (non-fatal): {snap_exc}")
```

Insert AFTER that try/except block (still before `run.completed_at = datetime.now(UTC)`):
```python
        # Evaluate price-target alerts — non-fatal, scan succeeded already.
        try:
            from app.services import price_alert_service

            fired = price_alert_service.evaluate_all(db)
            if fired:
                logger.info(f"[scan_runner] {fired} price alert(s) fired for ScanRun {run.id}")
        except Exception as pa_exc:  # noqa: BLE001
            logger.warning(f"[scan_runner] price alert evaluation failed (non-fatal): {pa_exc}")
```

- [ ] **Step 2: Add integration test**

Append to `backend/tests/test_price_alert_service.py`:
```python


from app.services import scan_runner


def test_scan_runner_fires_price_alerts(db, monkeypatch):
    """run_tracked_scan invokes evaluate_all at the end."""
    s = _seed_stock_with_two_bars(db, "FIRE", prev_close=99.0, last_close=101.0)
    price_alert_service.create(db, s.id, 100.0, "above")

    # Stub scan_universe so we don't run the full alert engine
    from app.services import scan_service
    monkeypatch.setattr(
        scan_service, "scan_universe",
        lambda db, on_progress=None, progress_every=10: scan_service.ScanResult(
            stocks_scanned=1, stocks_skipped=0, alerts_fired=0, states_updated=0,
        ),
    )

    run = scan_runner.run_tracked_scan(db, trigger="manual")
    assert run.status == "success"
    pa = db.query(PriceAlert).first()
    assert pa.triggered_at is not None


def test_scan_runner_price_alert_failure_is_non_fatal(db, monkeypatch):
    s = _seed_stock_with_two_bars(db, "X", prev_close=100.0, last_close=100.0)
    from app.services import scan_service
    monkeypatch.setattr(
        scan_service, "scan_universe",
        lambda db, on_progress=None, progress_every=10: scan_service.ScanResult(
            stocks_scanned=1, stocks_skipped=0, alerts_fired=0, states_updated=0,
        ),
    )
    monkeypatch.setattr(price_alert_service, "evaluate_all",
                        lambda db: (_ for _ in ()).throw(RuntimeError("boom")))

    run = scan_runner.run_tracked_scan(db, trigger="manual")
    assert run.status == "success"   # price alert failure must not mark scan failed
```

- [ ] **Step 3: Run tests**

```bash
cd backend && uv run pytest tests/test_price_alert_service.py -v
```
Expected: 9 passed (7 from B1 + 2 new).

- [ ] **Step 4: Run full backend suite**

```bash
cd backend && uv run pytest -q
```
Expected: ~165 passed (142 from before + ~23 new across A1+B1-B4+C2-C5). Pre-existing date-rollover flakes in `test_stats_service.py` may still fail near midnight — leave them alone.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/scan_runner.py backend/tests/test_price_alert_service.py
git commit -m "$(cat <<'EOF'
feat(backend): wire price_alert evaluator into scan_runner (non-fatal)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Section D — Frontend types + API clients + hooks

### Task D1: TS types extension

**Files:**
- Modify: `frontend/src/api/types.ts`

- [ ] **Step 1: Append to `frontend/src/api/types.ts`**

```typescript

// === Fase 3B: Stock Detail ===

export interface OhlcvBar {
  date: string;     // YYYY-MM-DD
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface IndicatorPoint {
  date: string;
  value: number | null;
}

export interface IndicatorSeries {
  sma50: IndicatorPoint[];
  sma200: IndicatorPoint[];
  rsi14: IndicatorPoint[];
}

export interface StockKpis {
  last_close: number | null;
  prev_close: number | null;
  change_pct: number | null;
  high_52w: number | null;
  low_52w: number | null;
  vol_avg_20: number | null;
  vol_today: number | null;
  vol_ratio: number | null;
}

export interface EffectiveRule {
  kind: string;
  enabled: boolean;
  params: Record<string, unknown>;
  source: "tier1" | "tier2";
  watchlist_name: string | null;
}

export interface StockDetail {
  stock: Stock;
  ohlcv: OhlcvBar[];
  indicators: IndicatorSeries;
  kpis: StockKpis;
  effective_rules: EffectiveRule[];
  alerts_history: Alert[];
}

export interface StockNewsItem {
  title: string;
  link: string;
  publisher: string;
  published_at: string | null;
}

export interface StockNews {
  items: StockNewsItem[];
}

export interface PriceAlert {
  id: number;
  stock_id: number;
  target_price: number;
  direction: "above" | "below";
  enabled: boolean;
  note: string | null;
  triggered_at: string | null;
  created_at: string;
}

export interface PriceAlertCreate {
  target_price: number;
  direction: "above" | "below";
  note?: string | null;
}

export interface PriceAlertUpdate {
  enabled?: boolean;
  target_price?: number;
  direction?: "above" | "below";
  note?: string | null;
}

export type SpotlightCardType = "top_gainer" | "most_alerted_7d" | "vol_spike";

export interface SpotlightCard {
  type: SpotlightCardType;
  ticker: string;
  last_close: number | null;
  sparkline: number[];
  change_pct?: number | null;
  vol_ratio?: number | null;
  alerts_count?: number | null;
}

export interface SpotlightSummary {
  cards: SpotlightCard[];
}
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build
```
Expected: success.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/types.ts
git commit -m "$(cat <<'EOF'
feat(frontend): add Stock Detail + PriceAlert + Spotlight TS types

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task D2: API clients

**Files:**
- Modify: `frontend/src/api/stocks.ts`
- Create: `frontend/src/api/priceAlerts.ts`
- Create: `frontend/src/api/spotlight.ts`

- [ ] **Step 1: Read and extend `frontend/src/api/stocks.ts`**

Read the existing file, then add the two methods. Append (or merge into the existing exported `stocks` object):

If the file currently has something like `export const stocks = { search: ..., filters: ... }`, extend it to:
```typescript
import { api } from "./client";
import type {
  FilterOptions, Stock, StockSearch, StockDetail, StockNews,
} from "./types";

export const stocks = {
  search: (params: URLSearchParams) =>
    api<StockSearch>(`/api/stocks/search?${params.toString()}`),
  filters: () => api<FilterOptions>("/api/stocks/filters"),
  get: (ticker: string) => api<Stock>(`/api/stocks/${ticker}`),
  detail: (ticker: string, range = "1y") =>
    api<StockDetail>(`/api/stocks/${ticker}/detail?range=${range}`),
  news: (ticker: string, limit = 5) =>
    api<StockNews>(`/api/stocks/${ticker}/news?limit=${limit}`),
};
```
(If existing methods differ, preserve them and add `detail` + `news` + `get` if missing.)

- [ ] **Step 2: Create `frontend/src/api/priceAlerts.ts`**

```typescript
import { api } from "./client";
import type { PriceAlert, PriceAlertCreate, PriceAlertUpdate } from "./types";

export const priceAlerts = {
  list: (ticker: string) =>
    api<PriceAlert[]>(`/api/stocks/${ticker}/price-alerts`),
  create: (ticker: string, body: PriceAlertCreate) =>
    api<PriceAlert>(`/api/stocks/${ticker}/price-alerts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  update: (id: number, body: PriceAlertUpdate) =>
    api<PriceAlert>(`/api/price-alerts/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  remove: (id: number) =>
    api<void>(`/api/price-alerts/${id}`, { method: "DELETE" }),
};
```

- [ ] **Step 3: Create `frontend/src/api/spotlight.ts`**

```typescript
import { api } from "./client";
import type { SpotlightSummary } from "./types";

export const spotlight = {
  summary: () => api<SpotlightSummary>("/api/dashboard/spotlight"),
};
```

- [ ] **Step 4: Verify build**

```bash
cd frontend && npm run build
```
Expected: success. (If `api` helper requires `Content-Type` to be set differently or has a different signature, adjust to match the existing pattern in `client.ts`.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/stocks.ts frontend/src/api/priceAlerts.ts frontend/src/api/spotlight.ts
git commit -m "$(cat <<'EOF'
feat(frontend): add stocks.detail/news, priceAlerts, spotlight API clients

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task D3: TanStack Query hooks

**Files:**
- Create: `frontend/src/hooks/useStockDetail.ts`
- Create: `frontend/src/hooks/useStockPriceAlerts.ts`
- Create: `frontend/src/hooks/useStockNews.ts`
- Create: `frontend/src/hooks/useSpotlight.ts`
- Create: `frontend/src/hooks/useStockDrawings.ts`

- [ ] **Step 1: useStockDetail**

```typescript
import { useQuery } from "@tanstack/react-query";

import { stocks } from "@/api/stocks";

export function useStockDetail(ticker: string, range: string = "1y") {
  return useQuery({
    queryKey: ["stock-detail", ticker, range],
    queryFn: () => stocks.detail(ticker, range),
    placeholderData: (prev) => prev,
    staleTime: 30_000,
  });
}
```

- [ ] **Step 2: useStockPriceAlerts**

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { priceAlerts } from "@/api/priceAlerts";
import type { PriceAlertCreate, PriceAlertUpdate } from "@/api/types";

export function useStockPriceAlerts(ticker: string) {
  return useQuery({
    queryKey: ["price-alerts", ticker],
    queryFn: () => priceAlerts.list(ticker),
    staleTime: 10_000,
  });
}

export function useCreatePriceAlert(ticker: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PriceAlertCreate) => priceAlerts.create(ticker, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["price-alerts", ticker] }),
  });
}

export function useUpdatePriceAlert(ticker: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: PriceAlertUpdate }) =>
      priceAlerts.update(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["price-alerts", ticker] }),
  });
}

export function useDeletePriceAlert(ticker: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => priceAlerts.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["price-alerts", ticker] }),
  });
}
```

- [ ] **Step 3: useStockNews**

```typescript
import { useQuery } from "@tanstack/react-query";

import { stocks } from "@/api/stocks";

export function useStockNews(ticker: string, limit: number = 5) {
  return useQuery({
    queryKey: ["stock-news", ticker, limit],
    queryFn: () => stocks.news(ticker, limit),
    staleTime: 60 * 60 * 1000,    // 1h, matches backend cache
    retry: 1,
  });
}
```

- [ ] **Step 4: useSpotlight**

```typescript
import { useQuery } from "@tanstack/react-query";

import { spotlight } from "@/api/spotlight";

export function useSpotlight() {
  return useQuery({
    queryKey: ["dashboard", "spotlight"],
    queryFn: () => spotlight.summary(),
    refetchInterval: 60_000,
    refetchIntervalInBackground: true,
    staleTime: 30_000,
  });
}
```

- [ ] **Step 5: useStockDrawings (localStorage)**

```typescript
import { useCallback, useEffect, useState } from "react";

export interface HorizontalDrawing {
  id: string;
  price: number;
}

export interface TrendDrawing {
  id: string;
  x1: number;   // unix seconds
  y1: number;
  x2: number;
  y2: number;
}

export interface StockDrawings {
  horizontal: HorizontalDrawing[];
  trend: TrendDrawing[];
}

const EMPTY: StockDrawings = { horizontal: [], trend: [] };

function storageKey(ticker: string): string {
  return `stock-drawings:${ticker}`;
}

function loadFromStorage(ticker: string): StockDrawings {
  try {
    const raw = localStorage.getItem(storageKey(ticker));
    if (!raw) return { horizontal: [], trend: [] };
    const parsed = JSON.parse(raw);
    return {
      horizontal: Array.isArray(parsed.horizontal) ? parsed.horizontal : [],
      trend: Array.isArray(parsed.trend) ? parsed.trend : [],
    };
  } catch {
    return { horizontal: [], trend: [] };
  }
}

export function useStockDrawings(ticker: string) {
  const [drawings, setDrawings] = useState<StockDrawings>(EMPTY);

  useEffect(() => {
    setDrawings(loadFromStorage(ticker));
  }, [ticker]);

  const persist = useCallback((next: StockDrawings) => {
    setDrawings(next);
    try {
      localStorage.setItem(storageKey(ticker), JSON.stringify(next));
    } catch {
      // localStorage full or unavailable; in-memory state still works
    }
  }, [ticker]);

  const addHorizontal = useCallback((price: number) => {
    persist({
      ...drawings,
      horizontal: [...drawings.horizontal, { id: crypto.randomUUID(), price }],
    });
  }, [drawings, persist]);

  const removeHorizontal = useCallback((id: string) => {
    persist({ ...drawings, horizontal: drawings.horizontal.filter((h) => h.id !== id) });
  }, [drawings, persist]);

  const addTrend = useCallback((x1: number, y1: number, x2: number, y2: number) => {
    persist({
      ...drawings,
      trend: [...drawings.trend, { id: crypto.randomUUID(), x1, y1, x2, y2 }],
    });
  }, [drawings, persist]);

  const removeTrend = useCallback((id: string) => {
    persist({ ...drawings, trend: drawings.trend.filter((t) => t.id !== id) });
  }, [drawings, persist]);

  const clearAll = useCallback(() => {
    persist({ horizontal: [], trend: [] });
  }, [persist]);

  return { drawings, addHorizontal, removeHorizontal, addTrend, removeTrend, clearAll };
}
```

- [ ] **Step 6: Verify build**

```bash
cd frontend && npm run build
```
Expected: success.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/hooks/
git commit -m "$(cat <<'EOF'
feat(frontend): add 5 hooks (stock-detail, price-alerts CRUD, news, spotlight, drawings)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Section E — Lightweight-charts integration

### Task E1: Install lightweight-charts

**Files:**
- Modify: `frontend/package.json`, `frontend/package-lock.json`

- [ ] **Step 1: Install**

```bash
cd frontend && npm install lightweight-charts@^4.2.0
```

- [ ] **Step 2: Verify build still passes**

```bash
cd frontend && npm run build
```
Expected: build succeeds, bundle slightly larger (~+45 kB gz).

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "$(cat <<'EOF'
chore(frontend): add lightweight-charts ^4.2.0 for Stock Detail candlestick

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task E2: PriceChart component (candlestick + SMA + volume + price-alert lines)

**Files:**
- Create: `frontend/src/components/stock/PriceChart.tsx`

- [ ] **Step 1: Create the component**

```tsx
import { useEffect, useRef } from "react";
import {
  CandlestickSeries, ColorType, HistogramSeries, LineSeries, createChart,
  type IChartApi, type ISeriesApi, type Time, type UTCTimestamp,
} from "lightweight-charts";

import type { OhlcvBar, IndicatorSeries, PriceAlert } from "@/api/types";

interface Props {
  ohlcv: OhlcvBar[];
  indicators: IndicatorSeries;
  showSma50: boolean;
  showSma200: boolean;
  priceAlerts: PriceAlert[];
  onChartClick?: (price: number) => void;
}

function dateToTime(d: string): UTCTimestamp {
  // YYYY-MM-DD -> UTC midnight unix seconds
  return (Date.parse(d) / 1000) as UTCTimestamp;
}

export function PriceChart({
  ohlcv, indicators, showSma50, showSma200, priceAlerts, onChartClick,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const sma50Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const sma200Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#374151" },
      grid: { vertLines: { color: "rgba(0,0,0,0.05)" }, horzLines: { color: "rgba(0,0,0,0.05)" } },
      rightPriceScale: { borderColor: "rgba(0,0,0,0.1)" },
      timeScale: { borderColor: "rgba(0,0,0,0.1)", timeVisible: false },
      crosshair: { mode: 1 },
      autoSize: true,
    });
    chartRef.current = chart;
    candleRef.current = chart.addCandlestickSeries({
      upColor: "#16a34a", downColor: "#dc2626",
      borderUpColor: "#16a34a", borderDownColor: "#dc2626",
      wickUpColor: "#16a34a", wickDownColor: "#dc2626",
    });
    sma50Ref.current = chart.addLineSeries({
      color: "#3b82f6", lineWidth: 2, priceLineVisible: false, lastValueVisible: false,
    });
    sma200Ref.current = chart.addLineSeries({
      color: "#f59e0b", lineWidth: 2, priceLineVisible: false, lastValueVisible: false,
    });
    volumeRef.current = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
      color: "rgba(100,100,100,0.4)",
    });
    chart.priceScale("vol").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    const clickHandler = (param: { point?: { x: number; y: number } }) => {
      if (!onChartClick || !param.point || !candleRef.current) return;
      const price = candleRef.current.coordinateToPrice(param.point.y);
      if (price !== null && typeof price === "number") {
        onChartClick(price);
      }
    };
    chart.subscribeClick(clickHandler);

    return () => {
      chart.unsubscribeClick(clickHandler);
      chart.remove();
      chartRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Update click handler reference without recreating chart
  useEffect(() => {
    // The click handler closes over onChartClick; recreate it on change
    if (!chartRef.current) return;
    const chart = chartRef.current;
    const clickHandler = (param: { point?: { x: number; y: number } }) => {
      if (!onChartClick || !param.point || !candleRef.current) return;
      const price = candleRef.current.coordinateToPrice(param.point.y);
      if (price !== null && typeof price === "number") {
        onChartClick(price);
      }
    };
    chart.subscribeClick(clickHandler);
    return () => chart.unsubscribeClick(clickHandler);
  }, [onChartClick]);

  // Set OHLCV data
  useEffect(() => {
    if (!candleRef.current || !volumeRef.current) return;
    candleRef.current.setData(
      ohlcv.map((b) => ({
        time: dateToTime(b.date),
        open: b.open, high: b.high, low: b.low, close: b.close,
      })),
    );
    volumeRef.current.setData(
      ohlcv.map((b) => ({
        time: dateToTime(b.date),
        value: b.volume,
        color: b.close >= b.open ? "rgba(22,163,74,0.4)" : "rgba(220,38,38,0.4)",
      })),
    );
    chartRef.current?.timeScale().fitContent();
  }, [ohlcv]);

  // SMA50
  useEffect(() => {
    if (!sma50Ref.current) return;
    sma50Ref.current.applyOptions({ visible: showSma50 });
    sma50Ref.current.setData(
      indicators.sma50
        .filter((p) => p.value !== null)
        .map((p) => ({ time: dateToTime(p.date), value: p.value as number })),
    );
  }, [indicators.sma50, showSma50]);

  // SMA200
  useEffect(() => {
    if (!sma200Ref.current) return;
    sma200Ref.current.applyOptions({ visible: showSma200 });
    sma200Ref.current.setData(
      indicators.sma200
        .filter((p) => p.value !== null)
        .map((p) => ({ time: dateToTime(p.date), value: p.value as number })),
    );
  }, [indicators.sma200, showSma200]);

  // Price alert horizontal lines
  useEffect(() => {
    if (!candleRef.current) return;
    const series = candleRef.current;
    const created = priceAlerts
      .filter((pa) => pa.enabled && pa.triggered_at === null)
      .map((pa) =>
        series.createPriceLine({
          price: pa.target_price,
          color: pa.direction === "above" ? "#16a34a" : "#dc2626",
          lineWidth: 1,
          lineStyle: 2,   // dashed
          axisLabelVisible: true,
          title: `${pa.direction === "above" ? "↑" : "↓"} $${pa.target_price.toFixed(2)}`,
        }),
      );
    return () => {
      created.forEach((line) => series.removePriceLine(line));
    };
  }, [priceAlerts]);

  return <div ref={containerRef} className="w-full h-[420px]" />;
}
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build
```
Expected: success. If TypeScript complains about lightweight-charts types, double-check `Time`/`UTCTimestamp` import names match your installed version.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/stock/PriceChart.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): add PriceChart (candlestick + SMA overlays + volume + price-alert lines)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task E3: RsiPanel component (separate chart, sync time-axis)

**Files:**
- Create: `frontend/src/components/stock/RsiPanel.tsx`

- [ ] **Step 1: Create**

```tsx
import { useEffect, useRef } from "react";
import {
  ColorType, LineSeries, createChart,
  type IChartApi, type ISeriesApi, type UTCTimestamp,
} from "lightweight-charts";

import type { IndicatorPoint } from "@/api/types";

interface Props {
  rsi14: IndicatorPoint[];
}

function dateToTime(d: string): UTCTimestamp {
  return (Date.parse(d) / 1000) as UTCTimestamp;
}

export function RsiPanel({ rsi14 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const lineRef = useRef<ISeriesApi<"Line"> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#374151" },
      grid: { vertLines: { color: "rgba(0,0,0,0.05)" }, horzLines: { color: "rgba(0,0,0,0.05)" } },
      rightPriceScale: { borderColor: "rgba(0,0,0,0.1)" },
      timeScale: { borderColor: "rgba(0,0,0,0.1)", timeVisible: false },
      crosshair: { mode: 1 },
      autoSize: true,
    });
    chartRef.current = chart;
    lineRef.current = chart.addLineSeries({
      color: "#7c3aed", lineWidth: 2, priceLineVisible: false,
    });
    // Add 30 / 70 reference lines
    lineRef.current.createPriceLine({
      price: 30, color: "#fb923c", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "30",
    });
    lineRef.current.createPriceLine({
      price: 70, color: "#dc2626", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "70",
    });
    return () => { chart.remove(); chartRef.current = null; };
  }, []);

  useEffect(() => {
    if (!lineRef.current) return;
    lineRef.current.setData(
      rsi14
        .filter((p) => p.value !== null)
        .map((p) => ({ time: dateToTime(p.date), value: p.value as number })),
    );
    chartRef.current?.timeScale().fitContent();
  }, [rsi14]);

  return <div ref={containerRef} className="w-full h-[120px]" />;
}
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build
```
Expected: success.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/stock/RsiPanel.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): add RsiPanel (separate lightweight-charts panel for RSI14)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Section F — Stock detail page components

### Task F1: StockHeader + TechnicalKpiCard + RangeSelector + IndicatorToggles

**Files:**
- Create: `frontend/src/lib/stockMeta.ts`
- Create: `frontend/src/components/stock/StockHeader.tsx`
- Create: `frontend/src/components/stock/TechnicalKpiCard.tsx`
- Create: `frontend/src/components/stock/RangeSelector.tsx`
- Create: `frontend/src/components/stock/IndicatorToggles.tsx`

- [ ] **Step 1: Create `frontend/src/lib/stockMeta.ts`**

```typescript
/**
 * Map ISO country codes (Stock.country) to flag asset codes for /flags/{code}.svg.
 * Falls back to "" (no flag rendered) for unknown countries.
 */
const COUNTRY_TO_FLAG: Record<string, string> = {
  US: "us",
  IT: "it",
  CN: "cn",
  HK: "hk",
  // EU member states aliased to "eu" since we have eu.svg
  DE: "eu", FR: "eu", ES: "eu", NL: "eu", BE: "eu", IE: "eu",
};

export function getStockFlagCode(country: string | null | undefined): string {
  if (!country) return "";
  return COUNTRY_TO_FLAG[country.toUpperCase()] ?? "";
}
```

- [ ] **Step 2: Create `frontend/src/components/stock/StockHeader.tsx`**

```tsx
import type { Stock, StockKpis } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { ACRONYM_HELP } from "@/lib/acronymHelp";
import { getStockFlagCode } from "@/lib/stockMeta";
import { cn } from "@/lib/utils";

interface Props {
  stock: Stock;
  kpis: StockKpis;
}

function fmtMc(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toLocaleString()}`;
}

export function StockHeader({ stock, kpis }: Props) {
  const flag = getStockFlagCode(stock.country);
  const change = kpis.change_pct;
  const changeColor = change == null
    ? "text-muted-foreground"
    : change > 0
      ? "text-green-600 dark:text-green-400"
      : change < 0
        ? "text-red-600 dark:text-red-400"
        : "";
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-3 flex-wrap">
          {flag && (
            <img
              src={`/flags/${flag}.svg`}
              alt={stock.country ?? ""}
              width={32} height={22}
              style={{ width: "32px", height: "22px", objectFit: "cover" }}
              className="rounded shadow-sm shrink-0"
            />
          )}
          <div className="min-w-0">
            <div className="flex items-baseline gap-2 flex-wrap">
              <span className="text-2xl font-bold">{stock.ticker}</span>
              <span className="text-sm text-muted-foreground truncate">{stock.name}</span>
            </div>
            <div className="text-xs text-muted-foreground">
              {stock.exchange}
              {stock.sector && <> · {stock.sector}</>}
              {stock.industry && <> · {stock.industry}</>}
            </div>
          </div>
          <div className="ml-auto flex items-center gap-6 text-sm tabular-nums">
            {kpis.last_close != null && (
              <div>
                <div className="text-xs text-muted-foreground">Last close</div>
                <div className="text-2xl font-bold">${kpis.last_close.toFixed(2)}</div>
              </div>
            )}
            {change != null && (
              <div>
                <div className="text-xs text-muted-foreground">Change</div>
                <div className={cn("text-xl font-semibold", changeColor)}>
                  {change >= 0 ? "+" : ""}{change.toFixed(2)}%
                </div>
              </div>
            )}
            {kpis.high_52w != null && kpis.low_52w != null && (
              <div title="52 weeks range">
                <div className="text-xs text-muted-foreground">52w range</div>
                <div className="text-sm">${kpis.low_52w.toFixed(2)} – ${kpis.high_52w.toFixed(2)}</div>
              </div>
            )}
            <div title={ACRONYM_HELP.UNIVERSE}>
              <div className="text-xs text-muted-foreground">Mkt cap</div>
              <div className="text-sm">{fmtMc(stock.market_cap)}</div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 3: Create `frontend/src/components/stock/TechnicalKpiCard.tsx`**

```tsx
import type { StockKpis, IndicatorSeries } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { ACRONYM_HELP } from "@/lib/acronymHelp";

interface Props {
  kpis: StockKpis;
  indicators: IndicatorSeries;
}

function lastValue(series: { value: number | null }[]): number | null {
  for (let i = series.length - 1; i >= 0; i--) {
    if (series[i].value !== null) return series[i].value;
  }
  return null;
}

function fmtNum(v: number | null, digits = 2): string {
  return v == null ? "—" : v.toFixed(digits);
}

export function TechnicalKpiCard({ kpis, indicators }: Props) {
  const sma50 = lastValue(indicators.sma50);
  const sma200 = lastValue(indicators.sma200);
  const rsi = lastValue(indicators.rsi14);

  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
          KPI tecnici
        </div>
        <table className="w-full text-sm tabular-nums">
          <tbody>
            <tr><td className="py-1 text-muted-foreground">SMA 50</td><td className="py-1 text-right font-semibold">${fmtNum(sma50)}</td></tr>
            <tr><td className="py-1 text-muted-foreground">SMA 200</td><td className="py-1 text-right font-semibold">${fmtNum(sma200)}</td></tr>
            <tr><td className="py-1 text-muted-foreground" title={ACRONYM_HELP.RSI_OVERSOLD}>RSI(14)</td><td className="py-1 text-right font-semibold">{fmtNum(rsi, 1)}</td></tr>
            <tr><td className="py-1 text-muted-foreground">52w high</td><td className="py-1 text-right">${fmtNum(kpis.high_52w)}</td></tr>
            <tr><td className="py-1 text-muted-foreground">52w low</td><td className="py-1 text-right">${fmtNum(kpis.low_52w)}</td></tr>
            <tr><td className="py-1 text-muted-foreground">Vol oggi</td><td className="py-1 text-right">{kpis.vol_today?.toLocaleString() ?? "—"}</td></tr>
            <tr><td className="py-1 text-muted-foreground" title={ACRONYM_HELP.VOL_SPIKE}>Vol×avg20</td><td className="py-1 text-right font-semibold">{fmtNum(kpis.vol_ratio, 2)}×</td></tr>
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 4: Create `frontend/src/components/stock/RangeSelector.tsx`**

```tsx
import { cn } from "@/lib/utils";

interface Props {
  value: string;
  onChange: (range: string) => void;
}

const OPTIONS = [
  { key: "1m", label: "1M" },
  { key: "3m", label: "3M" },
  { key: "6m", label: "6M" },
  { key: "1y", label: "1Y" },
  { key: "all", label: "All" },
];

export function RangeSelector({ value, onChange }: Props) {
  return (
    <div className="inline-flex rounded-md border bg-muted/30 p-0.5">
      {OPTIONS.map((opt) => (
        <button
          key={opt.key}
          type="button"
          onClick={() => onChange(opt.key)}
          className={cn(
            "px-3 py-1 text-xs font-medium rounded transition-colors",
            value === opt.key
              ? "bg-background shadow-sm text-foreground"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 5: Create `frontend/src/components/stock/IndicatorToggles.tsx`**

```tsx
interface Props {
  showSma50: boolean;
  showSma200: boolean;
  onToggle: (key: "sma50" | "sma200", value: boolean) => void;
}

export function IndicatorToggles({ showSma50, showSma200, onToggle }: Props) {
  return (
    <div className="inline-flex items-center gap-3 text-xs">
      <label className="inline-flex items-center gap-1 cursor-pointer">
        <input
          type="checkbox"
          checked={showSma50}
          onChange={(e) => onToggle("sma50", e.target.checked)}
          className="cursor-pointer"
        />
        <span style={{ color: "#3b82f6" }}>SMA 50</span>
      </label>
      <label className="inline-flex items-center gap-1 cursor-pointer">
        <input
          type="checkbox"
          checked={showSma200}
          onChange={(e) => onToggle("sma200", e.target.checked)}
          className="cursor-pointer"
        />
        <span style={{ color: "#f59e0b" }}>SMA 200</span>
      </label>
    </div>
  );
}
```

- [ ] **Step 6: Verify build**

```bash
cd frontend && npm run build
```
Expected: success.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/stockMeta.ts frontend/src/components/stock/
git commit -m "$(cat <<'EOF'
feat(frontend): add StockHeader + TechnicalKpiCard + RangeSelector + IndicatorToggles + stockMeta

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task F2: PriceAlertDialog + PriceAlertsCard

**Files:**
- Create: `frontend/src/components/stock/PriceAlertDialog.tsx`
- Create: `frontend/src/components/stock/PriceAlertsCard.tsx`

- [ ] **Step 1: Create `PriceAlertDialog.tsx`**

```tsx
import { useEffect, useState } from "react";

import type { PriceAlert } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

interface Props {
  open: boolean;
  initialPrice?: number;
  initialDirection?: "above" | "below";
  editing?: PriceAlert | null;
  onClose: () => void;
  onSubmit: (body: { target_price: number; direction: "above" | "below"; note: string | null }) => void;
}

export function PriceAlertDialog({
  open, initialPrice, initialDirection, editing, onClose, onSubmit,
}: Props) {
  const [price, setPrice] = useState<string>("");
  const [direction, setDirection] = useState<"above" | "below">("above");
  const [note, setNote] = useState<string>("");
  const [error, setError] = useState<string>("");

  useEffect(() => {
    if (!open) return;
    if (editing) {
      setPrice(String(editing.target_price));
      setDirection(editing.direction);
      setNote(editing.note ?? "");
    } else {
      setPrice(initialPrice != null ? initialPrice.toFixed(2) : "");
      setDirection(initialDirection ?? "above");
      setNote("");
    }
    setError("");
  }, [open, editing, initialPrice, initialDirection]);

  const submit = () => {
    const num = parseFloat(price);
    if (Number.isNaN(num) || num <= 0) {
      setError("Inserisci un prezzo positivo");
      return;
    }
    onSubmit({ target_price: num, direction, note: note.trim() || null });
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{editing ? "Modifica price alert" : "Nuovo price alert"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label htmlFor="price">Target price ($)</Label>
            <Input
              id="price"
              type="number"
              step="0.01"
              min="0"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              autoFocus
            />
          </div>
          <div>
            <Label>Direzione</Label>
            <Select value={direction} onValueChange={(v) => setDirection(v as "above" | "below")}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="above">Above (sopra il target)</SelectItem>
                <SelectItem value="below">Below (sotto il target)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label htmlFor="note">Nota (opzionale)</Label>
            <Input
              id="note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="es. resistance level"
              maxLength={255}
            />
          </div>
          {error && <div className="text-sm text-destructive">{error}</div>}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Annulla</Button>
          <Button onClick={submit}>{editing ? "Salva" : "Crea"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Create `PriceAlertsCard.tsx`**

```tsx
import { ArrowDown, ArrowUp, Pencil, Power, Trash2 } from "lucide-react";
import { useState } from "react";

import type { PriceAlert } from "@/api/types";
import {
  useCreatePriceAlert, useDeletePriceAlert, useStockPriceAlerts, useUpdatePriceAlert,
} from "@/hooks/useStockPriceAlerts";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PriceAlertDialog } from "@/components/stock/PriceAlertDialog";
import { cn } from "@/lib/utils";

interface Props {
  ticker: string;
}

export function PriceAlertsCard({ ticker }: Props) {
  const q = useStockPriceAlerts(ticker);
  const create = useCreatePriceAlert(ticker);
  const update = useUpdatePriceAlert(ticker);
  const remove = useDeletePriceAlert(ticker);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<PriceAlert | null>(null);

  const items = q.data ?? [];

  return (
    <>
      <Card>
        <CardContent className="p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Price alerts
            </span>
            <Button
              size="sm"
              variant="outline"
              onClick={() => { setEditing(null); setDialogOpen(true); }}
            >
              + Aggiungi
            </Button>
          </div>
          {items.length === 0 ? (
            <div className="text-xs text-muted-foreground text-center py-4">
              Nessuna price alert. Click su "+ Aggiungi" o sul chart per crearne una.
            </div>
          ) : (
            <ul className="space-y-1.5">
              {items.map((pa) => {
                const isTriggered = pa.triggered_at != null;
                return (
                  <li
                    key={pa.id}
                    className={cn(
                      "flex items-center gap-2 px-2 py-1.5 rounded text-xs border",
                      !pa.enabled && "opacity-50",
                      isTriggered && "bg-amber-50 dark:bg-amber-900/10",
                    )}
                  >
                    {pa.direction === "above"
                      ? <ArrowUp className="h-3.5 w-3.5 text-green-600" />
                      : <ArrowDown className="h-3.5 w-3.5 text-red-600" />}
                    <span className="font-semibold tabular-nums">${pa.target_price.toFixed(2)}</span>
                    {pa.note && <span className="text-muted-foreground truncate">{pa.note}</span>}
                    {isTriggered && <span className="text-amber-700 dark:text-amber-400 text-[10px]">scattato</span>}
                    <span className="ml-auto flex items-center gap-1">
                      <button
                        onClick={() => update.mutate({ id: pa.id, body: { enabled: !pa.enabled } })}
                        title={pa.enabled ? "Disabilita" : "Abilita"}
                        className="p-1 hover:bg-muted rounded"
                      >
                        <Power className="h-3 w-3" />
                      </button>
                      <button
                        onClick={() => { setEditing(pa); setDialogOpen(true); }}
                        title="Modifica"
                        className="p-1 hover:bg-muted rounded"
                      >
                        <Pencil className="h-3 w-3" />
                      </button>
                      <button
                        onClick={() => { if (confirm("Eliminare?")) remove.mutate(pa.id); }}
                        title="Elimina"
                        className="p-1 hover:bg-destructive/10 hover:text-destructive rounded"
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>
      <PriceAlertDialog
        open={dialogOpen}
        editing={editing}
        onClose={() => setDialogOpen(false)}
        onSubmit={(body) => {
          if (editing) {
            update.mutate({ id: editing.id, body });
          } else {
            create.mutate(body);
          }
          setDialogOpen(false);
        }}
      />
    </>
  );
}
```

- [ ] **Step 3: Verify build**

```bash
cd frontend && npm run build
```
Expected: success. (If shadcn `Dialog`, `Input`, `Label`, `Select` components are missing, install via shadcn CLI: `npx shadcn@2 add dialog input label select`. They may already exist — verify with `ls frontend/src/components/ui/`.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/stock/PriceAlertDialog.tsx frontend/src/components/stock/PriceAlertsCard.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): add PriceAlertDialog + PriceAlertsCard (CRUD UI)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task F3: StockAlertsHistoryCard + EffectiveRulesCard + NewsCard

**Files:**
- Create: `frontend/src/components/stock/StockAlertsHistoryCard.tsx`
- Create: `frontend/src/components/stock/EffectiveRulesCard.tsx`
- Create: `frontend/src/components/stock/NewsCard.tsx`

- [ ] **Step 1: Create `StockAlertsHistoryCard.tsx`**

```tsx
import { useState } from "react";

import type { Alert } from "@/api/types";
import { AlertDetailDialog } from "@/components/AlertDetailDialog";
import { Card, CardContent } from "@/components/ui/card";

interface Props {
  alerts: Alert[];
}

const KIND_LABEL: Record<string, string> = {
  rsi_oversold: "RSI Oversold",
  rsi_overbought: "RSI Overbought",
  golden_cross: "Golden Cross",
  death_cross: "Death Cross",
};

export function StockAlertsHistoryCard({ alerts }: Props) {
  const [open, setOpen] = useState<Alert | null>(null);

  return (
    <>
      <Card>
        <CardContent className="p-4">
          <div className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            Alert storici ({alerts.length})
          </div>
          {alerts.length === 0 ? (
            <div className="text-xs text-muted-foreground text-center py-4">
              Nessun alert per questo ticker.
            </div>
          ) : (
            <ul className="divide-y">
              {alerts.slice(0, 10).map((a) => (
                <li
                  key={a.id}
                  className="py-1.5 cursor-pointer hover:bg-accent transition-colors text-xs flex items-center gap-2"
                  onClick={() => setOpen(a)}
                >
                  <span className="font-medium">
                    {a.rule_kind ? KIND_LABEL[a.rule_kind] ?? a.rule_kind : "Price alert"}
                  </span>
                  <span className="ml-auto text-muted-foreground tabular-nums">
                    {new Date(a.triggered_at).toLocaleString("it-IT", {
                      day: "2-digit", month: "2-digit", year: "2-digit",
                    })}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {alerts.length > 10 && (
            <div className="text-xs text-muted-foreground mt-2 text-center">
              +{alerts.length - 10} non mostrati
            </div>
          )}
        </CardContent>
      </Card>
      <AlertDetailDialog alert={open} onClose={() => setOpen(null)} />
    </>
  );
}
```

- [ ] **Step 2: Create `EffectiveRulesCard.tsx`**

```tsx
import { Check, X } from "lucide-react";

import type { EffectiveRule } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface Props {
  rules: EffectiveRule[];
}

const KIND_LABEL: Record<string, string> = {
  rsi_oversold: "RSI Oversold",
  rsi_overbought: "RSI Overbought",
  golden_cross: "Golden Cross",
  death_cross: "Death Cross",
};

export function EffectiveRulesCard({ rules }: Props) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
          Regole effettive
        </div>
        {rules.length === 0 ? (
          <div className="text-xs text-muted-foreground text-center py-4">
            Nessuna regola configurata.
          </div>
        ) : (
          <ul className="space-y-1.5">
            {rules.map((r) => (
              <li key={r.kind} className="flex items-center gap-2 text-xs">
                {r.enabled
                  ? <Check className="h-3.5 w-3.5 text-green-600" />
                  : <X className="h-3.5 w-3.5 text-muted-foreground" />}
                <span className={cn("font-medium", !r.enabled && "line-through text-muted-foreground")}>
                  {KIND_LABEL[r.kind] ?? r.kind}
                </span>
                <Badge
                  variant={r.source === "tier2" ? "secondary" : "outline"}
                  className="ml-auto text-[10px] h-5"
                  title={r.source === "tier2" ? `Override da watchlist "${r.watchlist_name}"` : "Regola globale"}
                >
                  {r.source === "tier2" ? `WL: ${r.watchlist_name}` : "Globale"}
                </Badge>
              </li>
            ))}
          </ul>
        )}
        <div className="text-[10px] text-muted-foreground mt-3 italic">
          Override per-stock disponibili in fasi future.
        </div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 3: Create `NewsCard.tsx`**

```tsx
import { ExternalLink, Newspaper } from "lucide-react";

import { useStockNews } from "@/hooks/useStockNews";
import { Card, CardContent } from "@/components/ui/card";

interface Props {
  ticker: string;
}

function formatRelative(iso: string | null): string {
  if (!iso) return "";
  try {
    const ts = new Date(iso).getTime();
    const diffH = (Date.now() - ts) / (1000 * 60 * 60);
    if (diffH < 1) return `${Math.round(diffH * 60)}m fa`;
    if (diffH < 24) return `${Math.round(diffH)}h fa`;
    return `${Math.round(diffH / 24)}g fa`;
  } catch { return ""; }
}

export function NewsCard({ ticker }: Props) {
  const q = useStockNews(ticker, 5);
  const items = q.data?.items ?? [];

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-2 mb-2">
          <Newspaper className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            News
          </span>
        </div>
        {q.isLoading ? (
          <div className="space-y-2">
            {[0,1,2].map((i) => <div key={i} className="h-4 bg-muted/40 animate-pulse rounded" />)}
          </div>
        ) : items.length === 0 ? (
          <div className="text-xs text-muted-foreground text-center py-4">
            News non disponibili per questo ticker.
          </div>
        ) : (
          <ul className="space-y-2">
            {items.map((n) => (
              <li key={n.link} className="text-xs">
                <a
                  href={n.link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:underline flex items-start gap-1"
                >
                  <span className="line-clamp-2">{n.title}</span>
                  <ExternalLink className="h-3 w-3 shrink-0 text-muted-foreground mt-0.5" />
                </a>
                <div className="text-[10px] text-muted-foreground mt-0.5">
                  {n.publisher}
                  {n.published_at && <> · {formatRelative(n.published_at)}</>}
                </div>
              </li>
            ))}
          </ul>
        )}
        <div className="text-[10px] text-muted-foreground mt-3 italic">
          Powered by yfinance
        </div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 4: Verify build**

```bash
cd frontend && npm run build
```
Expected: success.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/stock/StockAlertsHistoryCard.tsx frontend/src/components/stock/EffectiveRulesCard.tsx frontend/src/components/stock/NewsCard.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): add StockAlertsHistoryCard + EffectiveRulesCard + NewsCard

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task F4: DrawingToolbar + StockDetailPage orchestrator

**Files:**
- Create: `frontend/src/components/stock/DrawingToolbar.tsx`
- Create: `frontend/src/pages/StockDetailPage.tsx`

- [ ] **Step 1: Create `DrawingToolbar.tsx`**

This is a minimal toolbar that toggles a "set-alert" mode. Full H-line/trend-line drawing with persistence is exposed but kept simple (single `localStorage` toggle for "active mode"). The PriceChart receives a click handler from the page; the toolbar tells the page which mode is active.

```tsx
import { Bell, Eraser, Minus, TrendingUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type DrawingMode = "none" | "hline" | "trend" | "alert";

interface Props {
  mode: DrawingMode;
  onSetMode: (mode: DrawingMode) => void;
  onClearAll: () => void;
}

export function DrawingToolbar({ mode, onSetMode, onClearAll }: Props) {
  const Tool = ({
    target, label, icon: Icon, title,
  }: { target: DrawingMode; label: string; icon: typeof Bell; title: string }) => (
    <Button
      type="button"
      size="sm"
      variant={mode === target ? "default" : "outline"}
      onClick={() => onSetMode(mode === target ? "none" : target)}
      title={title}
      className={cn("text-xs h-8")}
    >
      <Icon className="h-3.5 w-3.5 mr-1" />
      {label}
    </Button>
  );

  return (
    <div className="inline-flex items-center gap-2">
      <Tool target="hline" label="H-line" icon={Minus} title="Disegna una linea orizzontale al prezzo cliccato" />
      <Tool target="trend" label="Trend" icon={TrendingUp} title="Disegna una trendline (2 click)" />
      <Tool target="alert" label="Set alert" icon={Bell} title="Crea un price alert al prezzo cliccato" />
      <Button
        type="button" size="sm" variant="ghost" onClick={onClearAll}
        title="Rimuovi tutti i drawing per questo stock"
        className="text-xs h-8"
      >
        <Eraser className="h-3.5 w-3.5 mr-1" /> Clear
      </Button>
    </div>
  );
}
```

- [ ] **Step 2: Extend PriceChart to render localStorage drawings**

Edit `frontend/src/components/stock/PriceChart.tsx` to also render the user-drawn horizontal lines. Add a new prop `drawings` and effect:

Add to `Props`:
```typescript
import type { HorizontalDrawing } from "@/hooks/useStockDrawings";
```
```typescript
interface Props {
  ohlcv: OhlcvBar[];
  indicators: IndicatorSeries;
  showSma50: boolean;
  showSma200: boolean;
  priceAlerts: PriceAlert[];
  horizontalDrawings: HorizontalDrawing[];   // NEW
  onChartClick?: (price: number) => void;
}
```
And destructure `horizontalDrawings` in the function signature.

Add a new effect AFTER the price-alert lines effect:
```typescript
  useEffect(() => {
    if (!candleRef.current) return;
    const series = candleRef.current;
    const created = horizontalDrawings.map((h) =>
      series.createPriceLine({
        price: h.price,
        color: "#6b7280",
        lineWidth: 1,
        lineStyle: 0,   // solid
        axisLabelVisible: true,
        title: `H $${h.price.toFixed(2)}`,
      }),
    );
    return () => {
      created.forEach((line) => series.removePriceLine(line));
    };
  }, [horizontalDrawings]);
```

(Trend lines are deferred — implementing them requires `addLineSeries` per trend and managing time-coordinate clicks. For 3B we ship horizontal lines + price alerts; trend is a placeholder via the toolbar button that for now no-ops or shows a toast "trend lines coming soon".)

To keep scope focused: when DrawingMode is "trend", the page does nothing on click (or shows a toast). Mark this in code with a comment.

- [ ] **Step 3: Create `StockDetailPage.tsx`**

```tsx
import { AlertCircle } from "lucide-react";
import { useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import type { PriceAlert } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { useCreatePriceAlert, useStockPriceAlerts } from "@/hooks/useStockPriceAlerts";
import { useStockDetail } from "@/hooks/useStockDetail";
import { useStockDrawings } from "@/hooks/useStockDrawings";
import { DrawingToolbar, type DrawingMode } from "@/components/stock/DrawingToolbar";
import { EffectiveRulesCard } from "@/components/stock/EffectiveRulesCard";
import { IndicatorToggles } from "@/components/stock/IndicatorToggles";
import { NewsCard } from "@/components/stock/NewsCard";
import { PriceAlertDialog } from "@/components/stock/PriceAlertDialog";
import { PriceAlertsCard } from "@/components/stock/PriceAlertsCard";
import { PriceChart } from "@/components/stock/PriceChart";
import { RangeSelector } from "@/components/stock/RangeSelector";
import { RsiPanel } from "@/components/stock/RsiPanel";
import { StockAlertsHistoryCard } from "@/components/stock/StockAlertsHistoryCard";
import { StockHeader } from "@/components/stock/StockHeader";
import { TechnicalKpiCard } from "@/components/stock/TechnicalKpiCard";

export default function StockDetailPage() {
  const { ticker = "" } = useParams<{ ticker: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const range = searchParams.get("range") ?? "1y";

  const detail = useStockDetail(ticker, range);
  const priceAlertsQuery = useStockPriceAlerts(ticker);
  const createPa = useCreatePriceAlert(ticker);
  const drawings = useStockDrawings(ticker);

  const [showSma50, setShowSma50] = useState(true);
  const [showSma200, setShowSma200] = useState(true);
  const [mode, setMode] = useState<DrawingMode>("none");
  const [pendingPrice, setPendingPrice] = useState<number | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const handleChartClick = (price: number) => {
    if (mode === "alert") {
      setPendingPrice(price);
      setDialogOpen(true);
      setMode("none");
    } else if (mode === "hline") {
      drawings.addHorizontal(Math.round(price * 100) / 100);
      setMode("none");
    }
    // mode === "trend" is deferred — no-op for now
  };

  if (detail.isLoading) {
    return (
      <div className="space-y-3">
        <Card><CardContent className="p-4 h-[80px] animate-pulse bg-muted/40" /></Card>
        <div className="grid lg:grid-cols-[1fr_320px] gap-3">
          <Card><CardContent className="p-4 h-[540px] animate-pulse bg-muted/40" /></Card>
          <div className="space-y-3">
            {[0,1,2,3,4].map((i) =>
              <Card key={i}><CardContent className="p-4 h-[100px] animate-pulse bg-muted/40" /></Card>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (detail.isError || !detail.data) {
    return (
      <Card>
        <CardContent className="p-6 flex items-center gap-3 text-sm">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <span>Errore nel caricamento del ticker <strong>{ticker}</strong>. Verifica che esista in catalogo.</span>
        </CardContent>
      </Card>
    );
  }

  const d = detail.data;
  const priceAlerts: PriceAlert[] = priceAlertsQuery.data ?? [];
  const lastClose = d.kpis.last_close ?? 0;

  return (
    <div className="space-y-3">
      <StockHeader stock={d.stock} kpis={d.kpis} />

      <div className="grid lg:grid-cols-[1fr_320px] gap-3">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
              <RangeSelector
                value={range}
                onChange={(r) => setSearchParams({ range: r })}
              />
              <div className="flex items-center gap-3">
                <IndicatorToggles
                  showSma50={showSma50}
                  showSma200={showSma200}
                  onToggle={(k, v) => k === "sma50" ? setShowSma50(v) : setShowSma200(v)}
                />
                <DrawingToolbar
                  mode={mode}
                  onSetMode={setMode}
                  onClearAll={drawings.clearAll}
                />
              </div>
            </div>
            {d.ohlcv.length < 2 ? (
              <div className="h-[420px] flex items-center justify-center text-sm text-muted-foreground">
                Dati insufficienti per il chart
              </div>
            ) : (
              <PriceChart
                ohlcv={d.ohlcv}
                indicators={d.indicators}
                showSma50={showSma50}
                showSma200={showSma200}
                priceAlerts={priceAlerts}
                horizontalDrawings={drawings.drawings.horizontal}
                onChartClick={handleChartClick}
              />
            )}
            {d.indicators.rsi14.length > 0 && (
              <div className="mt-2">
                <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">
                  RSI(14)
                </div>
                <RsiPanel rsi14={d.indicators.rsi14} />
              </div>
            )}
          </CardContent>
        </Card>

        <div className="space-y-3">
          <TechnicalKpiCard kpis={d.kpis} indicators={d.indicators} />
          <PriceAlertsCard ticker={ticker} />
          <StockAlertsHistoryCard alerts={d.alerts_history} />
          <EffectiveRulesCard rules={d.effective_rules} />
          <NewsCard ticker={ticker} />
        </div>
      </div>

      <PriceAlertDialog
        open={dialogOpen}
        initialPrice={pendingPrice ?? undefined}
        initialDirection={pendingPrice != null && pendingPrice > lastClose ? "above" : "below"}
        onClose={() => setDialogOpen(false)}
        onSubmit={(body) => {
          createPa.mutate(body);
          setDialogOpen(false);
        }}
      />
    </div>
  );
}
```

- [ ] **Step 4: Verify build**

```bash
cd frontend && npm run build
```
Expected: success.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/stock/DrawingToolbar.tsx frontend/src/components/stock/PriceChart.tsx frontend/src/pages/StockDetailPage.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): add DrawingToolbar + StockDetailPage orchestrator

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Section G — Routing + dashboard wire-up

### Task G1: Add /stocks/:ticker route + Stocks sidebar entry

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Layout.tsx`

- [ ] **Step 1: Modify App.tsx**

Add the route. Find:
```tsx
import HomePage from "@/pages/HomePage";
import LoginPage from "@/pages/LoginPage";
import WatchlistDetailPage from "@/pages/WatchlistDetailPage";
import WatchlistListPage from "@/pages/WatchlistListPage";
```
Add an import:
```tsx
import StockDetailPage from "@/pages/StockDetailPage";
```

Find:
```tsx
<Route path="/alerts" element={<AlertsPage />} />
```
Add right after:
```tsx
<Route path="/stocks/:ticker" element={<StockDetailPage />} />
```

- [ ] **Step 2: Modify Layout.tsx**

Read the file. Find the NAV array entry for `/stocks` (currently `enabled: false`). Update to:
```tsx
{ to: "/stocks/AAPL", label: "Stocks", icon: Search, enabled: true },
```
(The default ticker AAPL is a placeholder — user can navigate elsewhere from the page or via dashboard.)

- [ ] **Step 3: Verify build**

```bash
cd frontend && npm run build
```
Expected: success.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/Layout.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): mount /stocks/:ticker route + enable Stocks sidebar entry

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task G2: SpotlightCards component (replaces SpotlightPlaceholder)

**Files:**
- Create: `frontend/src/components/dashboard/SpotlightCards.tsx`

- [ ] **Step 1: Create the component**

```tsx
import { Bell, Sparkles, TrendingUp, Zap } from "lucide-react";
import { Link } from "react-router-dom";
import { Line, LineChart, ResponsiveContainer } from "recharts";

import type { SpotlightCard } from "@/api/types";
import { useSpotlight } from "@/hooks/useSpotlight";
import { Card, CardContent } from "@/components/ui/card";
import { StockLogo } from "@/components/dashboard/StockLogo";

const TYPE_META: Record<SpotlightCard["type"], { label: string; icon: typeof Bell; accent: string }> = {
  top_gainer: {
    label: "Top gainer",
    icon: TrendingUp,
    accent: "text-green-600 dark:text-green-400",
  },
  most_alerted_7d: {
    label: "Most alerted 7d",
    icon: Bell,
    accent: "text-amber-600 dark:text-amber-400",
  },
  vol_spike: {
    label: "Volume spike",
    icon: Zap,
    accent: "text-blue-600 dark:text-blue-400",
  },
};

function CardItem({ card }: { card: SpotlightCard }) {
  const meta = TYPE_META[card.type];
  const Icon = meta.icon;
  const sparkData = card.sparkline.map((v, i) => ({ idx: i, v }));
  const trendUp = sparkData.length >= 2 && sparkData[sparkData.length - 1].v >= sparkData[0].v;
  const subtitle =
    card.type === "top_gainer" ? `${card.change_pct! >= 0 ? "+" : ""}${card.change_pct?.toFixed(2)}%` :
    card.type === "vol_spike"  ? `${card.vol_ratio?.toFixed(1)}× volume` :
                                  `${card.alerts_count} alert ult. 7gg`;

  return (
    <Link to={`/stocks/${card.ticker}`} className="block">
      <Card className="hover:bg-accent/30 transition-colors cursor-pointer h-full">
        <CardContent className="p-3">
          <div className="flex items-center gap-2 mb-2">
            <Icon className={`h-3.5 w-3.5 ${meta.accent}`} />
            <span className="text-[10px] uppercase tracking-wide text-muted-foreground font-semibold">
              {meta.label}
            </span>
          </div>
          <div className="flex items-center gap-2 mb-1">
            <StockLogo ticker={card.ticker} size="sm" />
            <div className="min-w-0 flex-1">
              <div className="font-bold text-sm">{card.ticker}</div>
              <div className={`text-xs ${meta.accent}`}>{subtitle}</div>
            </div>
            {card.last_close != null && (
              <div className="text-xs tabular-nums text-muted-foreground">
                ${card.last_close.toFixed(2)}
              </div>
            )}
          </div>
          {sparkData.length > 0 && (
            <div className="h-8 mt-1">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={sparkData}>
                  <Line
                    type="monotone"
                    dataKey="v"
                    stroke={trendUp ? "#16a34a" : "#dc2626"}
                    strokeWidth={1.5}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>
    </Link>
  );
}

export function SpotlightCards() {
  const q = useSpotlight();
  const cards = q.data?.cards ?? [];

  if (q.isLoading) {
    return (
      <Card>
        <CardContent className="p-4 min-h-[120px] animate-pulse bg-muted/40" />
      </Card>
    );
  }

  if (cards.length === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="p-6 flex flex-col items-center justify-center text-center min-h-[120px]">
          <Sparkles className="h-5 w-5 text-muted-foreground mb-2" />
          <div className="text-sm text-muted-foreground">
            Nessun stock in spotlight (esegui uno scan o attendi alert).
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
      {cards.map((c) => <CardItem key={c.type} card={c} />)}
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build
```
Expected: success.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/dashboard/SpotlightCards.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): add SpotlightCards (3 mini cards with sparkline + link to /stocks)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task G3: HomePage replace placeholder + Treemap navigate

**Files:**
- Modify: `frontend/src/pages/HomePage.tsx`
- Modify: `frontend/src/components/dashboard/MarketTreemap.tsx`
- Delete: `frontend/src/components/dashboard/SpotlightPlaceholder.tsx`

- [ ] **Step 1: Replace SpotlightPlaceholder with SpotlightCards in HomePage.tsx**

Find:
```tsx
import { SpotlightPlaceholder } from "@/components/dashboard/SpotlightPlaceholder";
```
Replace with:
```tsx
import { SpotlightCards } from "@/components/dashboard/SpotlightCards";
```

Find:
```tsx
<SpotlightPlaceholder />
```
Replace with:
```tsx
<SpotlightCards />
```

- [ ] **Step 2: Add navigation on Treemap tile click**

Read `frontend/src/components/dashboard/MarketTreemap.tsx`. Add `useNavigate` from react-router-dom and wire onClick on the chart container or on `CustomCell`.

The simplest approach: wrap the Recharts container with a click handler that derives the clicked ticker from event target — but Recharts Treemap event handling is awkward. Use the `onClick` prop on the `<Treemap>` component which fires with the data point.

Find the `<Treemap data={filtered} dataKey="size" content={<CustomCell />} />` line and replace with:
```tsx
<Treemap
  data={filtered}
  dataKey="size"
  content={<CustomCell />}
  onClick={(payload) => {
    const ticker = (payload as { ticker?: string } | undefined)?.ticker;
    if (ticker) navigate(`/stocks/${ticker}`);
  }}
/>
```

Add the import at top:
```tsx
import { useNavigate } from "react-router-dom";
```

Add `const navigate = useNavigate();` at the top of the `MarketTreemap` function body, near the existing `useState`/`useMemo`.

Also update the title attribute on the chart wrapper. Find:
```tsx
<div className="h-[260px] flex-1" title="Drill-down su singolo stock disponibile in Fase 3B">
```
Replace with:
```tsx
<div className="h-[260px] flex-1" title="Click su un tile per andare alla pagina dello stock">
```

- [ ] **Step 3: Delete SpotlightPlaceholder.tsx**

```bash
rm frontend/src/components/dashboard/SpotlightPlaceholder.tsx
```

- [ ] **Step 4: Verify build**

```bash
cd frontend && npm run build
```
Expected: success. If a leftover import to SpotlightPlaceholder fails, find it via grep and remove.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/HomePage.tsx frontend/src/components/dashboard/MarketTreemap.tsx frontend/src/components/dashboard/SpotlightPlaceholder.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): wire SpotlightCards into HomePage + Treemap click -> /stocks/:ticker

Old SpotlightPlaceholder.tsx removed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Section H — Ship

### Task H1: ARCHITECTURE.md + final smoke test + push

- [ ] **Step 1: Run full backend test suite**

```bash
cd backend && uv run pytest -q
```
Expected: ~165 passing (142 from before + ~23 new). 2 pre-existing date-rollover flakes may still fail near midnight — leave them alone.

- [ ] **Step 2: Run frontend build**

```bash
cd frontend && npm run build
```
Expected: clean. Bundle should be < 1.1 MB.

- [ ] **Step 3: Live smoke test**

Stop and restart backend (the `--reload` watcher may have missed new files):
- In one shell: `cd backend && uv run uvicorn app.main:app --port 8000`
- In another shell:
```bash
curl -sf http://localhost:8000/api/health
curl -s http://localhost:8000/openapi.json | python -c "import sys,json; d=json.load(sys.stdin); paths=[p for p in d['paths'] if 'stocks' in p or 'price-alert' in p or 'spotlight' in p]; print(sorted(paths))"
```
Expected paths include: `/api/dashboard/spotlight`, `/api/price-alerts/{alert_id}`, `/api/stocks/{ticker}/detail`, `/api/stocks/{ticker}/news`, `/api/stocks/{ticker}/price-alerts`.

Open `http://localhost:8000/` in browser, login, navigate to `/stocks/AAPL` directly OR click a Treemap tile.

- [ ] **Step 4: Update `docs/ARCHITECTURE.md`**

Read the file. Make these edits:

1. Header line — bump `**Stato applicazione**`:
   ```
   **Stato applicazione**: Fase 1 in production. Fase 2 (alert engine) implemented. Fase 3A (Dashboard Home) implemented. Fase 3A-bis (Market Dashboard redesign) implemented. Fase 3B (Stock Detail) implemented.
   ```

2. §1 Panoramica — add new bullet after the 3A-bis line:
   ```markdown
   - **(Fase 3B — implementato)** Pagina Stock Detail su `/stocks/:ticker` con candlestick chart (lightweight-charts), indicatori SMA/RSI, drawing tools (H-lines persistite in localStorage), price-target alerts (nuovo dominio `PriceAlert` + edge-trigger evaluator integrato in scan_runner), news headlines via yfinance, vista read-only delle regole effettive. SpotlightCards reali in Dashboard.
   ```

3. §9 Roadmap — promote Fase 3B from Futura to **Implementata** with detail:
   ```markdown
   | **Fase 3B** — Stock Detail | **Implementata** | Pagina `/stocks/:ticker` con candlestick (lightweight-charts) + SMA + volume + RSI panel + drawing tools (H-line) + price-target alerts (nuovo modello `PriceAlert` + endpoint CRUD + evaluator non-fatal in scan_runner) + news yfinance (cache 1h) + alert history per-stock + effective_rules read-only Tier1/Tier2. SpotlightCards in HomePage al posto del placeholder. |
   ```

4. §11 Changelog — append:
   ```markdown
   | 2026-05-02 | <commit-sha> | Fase 3B Stock Detail: nuova pagina `/stocks/:ticker` (layout grid 2-col), nuovo dominio PriceAlert (tabella + CRUD + edge-trigger evaluator non-fatal in scan_runner), endpoint `/api/stocks/{ticker}/detail`, `/news`, `/price-alerts`, `/api/dashboard/spotlight`. Frontend: lightweight-charts (candlestick + SMA + volume + RSI panel + price-line drawings), useStockDrawings (localStorage), SpotlightCards reali con sparkline + link a /stocks. ~23 nuovi test backend (totale ~165 passing). |
   ```
   Replace `<commit-sha>` with the short SHA from `git rev-parse --short HEAD`.

- [ ] **Step 5: Commit + push**

```bash
git add docs/ARCHITECTURE.md
git commit -m "$(cat <<'EOF'
docs: mark Fase 3B Stock Detail complete in ARCHITECTURE.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push origin master
```

Expected: push succeeds. Phase 3B shipped.

---

## Self-review checklist

**Spec coverage** — comparing plan to spec:
- §5 Modello dati `price_alerts` table → A1 + A2 ✓
- §5 `Alert.rule_id` nullable → A1 + A2 ✓
- §6 endpoint `/api/stocks/{ticker}/detail` → C2 ✓
- §6 endpoint `/api/stocks/{ticker}/news` → C2 ✓
- §6 endpoint `/api/.../price-alerts` CRUD → C3 ✓
- §6 endpoint `/api/dashboard/spotlight` → C4 ✓
- §7 `PriceAlertService` (CRUD + evaluator) → B1 ✓
- §7 `StockDetailService` (loader + indicators + effective_rules) → B2 ✓
- §7 `StockNewsService` (yfinance + cache) → B3 ✓
- §7 `SpotlightService` + `get_top_alerted_stock_7d` → B4 ✓
- §7 `evaluate_price_alerts` integrato in `scan_runner` non-fatal → C5 ✓
- §8 Pagina `StockDetailPage` + 12 sub-components → F1 + F2 + F3 + F4 ✓
- §8 Hooks (useStockDetail, useStockPriceAlerts, useStockNews, useSpotlight, useStockDrawings) → D3 ✓
- §8 API client → D2 ✓
- §8 Routing `/stocks/:ticker` + sidebar Stocks enabled → G1 ✓
- §8 SpotlightCards reali in HomePage → G2 + G3 ✓
- §8 Treemap click → /stocks → G3 ✓
- §9 UX: drawing tools localStorage → D3 (useStockDrawings) + F4 (DrawingToolbar) + E2 (PriceChart horizontal lines) ✓
- §9 UX: set alert from chart → F4 (page wires onChartClick → dialog) ✓
- §9 UX: range selector URL state → F1 (RangeSelector) + F4 (page) ✓
- §10 Error handling: 404 ticker, OHLCV insufficiente, news fallback, validation → covered in C2/C3 + F4 ✓
- §11 DoD checklist — all items have a task ✓
- §13 Roadmap follow-up — referenced in spec, no tasks here (correct) ✓

**Placeholder scan**: nessun TBD/TODO; ogni step ha codice eseguibile o comando preciso.

**Type consistency**:
- `PriceAlert` interface (TS) ↔ `PriceAlert` model (Python) ↔ `PriceAlertOut` (Pydantic) — field names match (id, stock_id, target_price, direction, enabled, note, triggered_at, created_at)
- `OhlcvBar` (TS) ↔ `OhlcvBarOut` (Pydantic) ↔ `OhlcvDaily` (model) — field names match
- `EffectiveRule` (TS) ↔ `EffectiveRuleOut` (Pydantic) ↔ `EffectiveRule` dataclass (Python service) — match
- `StockDetail` (TS) ↔ `StockDetailOut` (Pydantic) ↔ `StockDetail` dataclass — match
- Hook query keys consistent: `["stock-detail", ticker, range]`, `["price-alerts", ticker]`, `["stock-news", ticker]`, `["dashboard", "spotlight"]`
- Drawing types: `HorizontalDrawing` defined once in `useStockDrawings.ts`, imported by `PriceChart.tsx`

**Method signatures consistent**:
- `price_alert_service.create(db, stock_id, target_price, direction, note=None)` — matches all callers
- `price_alert_service.update(db, alert_id, *, enabled=None, target_price=None, direction=None, note=None)` — matches Pydantic `PriceAlertUpdate` fields
- `stock_detail_service.get_detail(db, ticker, range_key="1y")` — matches API call
- `spotlight_service.build(db)` — matches API call

---

## Execution Handoff (skipped — user authorized auto-progression)

Per istruzione utente: skip prompt approvazione, passare direttamente a `superpowers:subagent-driven-development`.
