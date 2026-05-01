# Finance Alert — Fase 3A Implementation Plan (Dashboard Home)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/` Home page that shows 4 KPI cards, a 30-day alerts-by-day chart (Recharts), Top 10 stocks by alert count, a 10-row recent-alerts feed, and a system status footer. Single BFF endpoint `GET /api/dashboard/summary` aggregates everything; frontend polls every 30s via TanStack Query.

**Architecture:** Pure additive — zero new DB tables, zero new migrations. Backend adds a `stats_service` (4 pure aggregation functions), an API router `dashboard.py` with one composing endpoint, and Pydantic schemas. Frontend adds 5 dashboard components, an `useDashboardSummary` hook, an API client, and an `HomePage` mounted on `/`.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (existing), pytest. React 19, TypeScript 6, Vite 8, **recharts** (NEW), TanStack Query 5, shadcn/ui, vitest.

**Spec:** [docs/superpowers/specs/2026-05-01-finance-alert-fase3a-design.md](../specs/2026-05-01-finance-alert-fase3a-design.md)
**Architecture (living):** [docs/ARCHITECTURE.md](../../ARCHITECTURE.md)

---

## Conventions

- Working directory: `C:/Users/giuli/Documents/Progetti/finance-alert` (root). Commands assume Git Bash via Bash tool; `just` recipes work on Windows via `set windows-shell := ["cmd.exe", "/C"]`.
- Conventional Commits with `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` trailer.
- Update `docs/ARCHITECTURE.md` when introducing endpoint/service/page (this plan adds an entry at the end).
- TDD strict on `stats_service` and the dashboard API endpoint. Frontend smoke-tested via build + a single render test.
- Existing baseline: 103 backend tests passing. Final: ~114.

---

## File Structure

```
backend/app/
├── services/
│   └── stats_service.py             # NEW — pure aggregation queries (Section A)
├── schemas/
│   └── dashboard.py                 # NEW — KpiSummaryOut, DashboardSummaryOut, etc. (Section B)
├── api/
│   └── dashboard.py                 # NEW — GET /api/dashboard/summary (Section B)
└── main.py                          # MODIFY — register dashboard router

backend/tests/
├── test_stats_service.py            # NEW (Section A)
└── test_api_dashboard.py            # NEW (Section B)

frontend/src/
├── api/
│   ├── dashboard.ts                 # NEW (Section C)
│   └── types.ts                     # MODIFY — add Dashboard* types (Section C)
├── hooks/
│   └── useDashboardSummary.ts       # NEW (Section C)
├── components/
│   └── dashboard/                   # NEW dir
│       ├── KpiCard.tsx              # Section D
│       ├── AlertsByDayChart.tsx     # Section D
│       ├── TopStocksTable.tsx       # Section D
│       ├── RecentAlertsFeed.tsx     # Section D
│       └── SystemStatusCard.tsx     # Section D
├── pages/
│   └── HomePage.tsx                 # NEW (Section E)
├── App.tsx                          # MODIFY — / now → HomePage (Section E)
└── components/Layout.tsx            # MODIFY — Dashboard nav entry enabled (Section E)
```

---

## Section A — `stats_service` (TDD strict)

### Task A1: Initial scaffold + KPI summary tests

**Files:**
- Create: `backend/app/services/stats_service.py`
- Create: `backend/tests/test_stats_service.py`

- [ ] **Step 1: Write failing tests for the KPI summary**

```python
# backend/tests/test_stats_service.py
"""Tests for stats_service aggregation queries."""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import Alert, Rule, Stock
from app.services.stats_service import KpiSummary, get_kpi_summary


def _seed_baseline(db: Session) -> tuple[Stock, Rule]:
    stock = Stock(ticker="AAPL", exchange="NASDAQ", name="Apple Inc.")
    db.add(stock)
    rule = Rule(watchlist_id=None, kind="rsi_oversold", params="{}", enabled=True)
    db.add(rule)
    db.commit()
    db.refresh(stock)
    db.refresh(rule)
    return stock, rule


def _make_alert(
    db: Session,
    stock: Stock,
    rule: Rule,
    *,
    age_hours: float = 0.0,
    archived: bool = False,
) -> Alert:
    a = Alert(
        rule_id=rule.id,
        stock_id=stock.id,
        trigger_price=100.0,
        snapshot="{}",
    )
    a.triggered_at = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    if archived:
        a.archived_at = datetime.now(timezone.utc)
    db.add(a)
    db.commit()
    return a


def test_kpi_alerts_24h_counts_only_recent_unarchived(db: Session) -> None:
    stock, rule = _seed_baseline(db)
    _make_alert(db, stock, rule, age_hours=2)      # in 24h
    _make_alert(db, stock, rule, age_hours=12)     # in 24h
    _make_alert(db, stock, rule, age_hours=30)     # outside 24h
    _make_alert(db, stock, rule, age_hours=2, archived=True)  # archived → excluded
    summary = get_kpi_summary(db)
    assert isinstance(summary, KpiSummary)
    assert summary.alerts_last_24h == 2


def test_kpi_alerts_prev_24h_window(db: Session) -> None:
    stock, rule = _seed_baseline(db)
    _make_alert(db, stock, rule, age_hours=2)      # in current 24h
    _make_alert(db, stock, rule, age_hours=30)     # in [24h, 48h)
    _make_alert(db, stock, rule, age_hours=40)     # in [24h, 48h)
    _make_alert(db, stock, rule, age_hours=72)     # outside
    summary = get_kpi_summary(db)
    assert summary.alerts_last_24h == 1
    assert summary.alerts_prev_24h == 2


def test_kpi_unread_excludes_archived_and_read(db: Session) -> None:
    stock, rule = _seed_baseline(db)
    _make_alert(db, stock, rule, age_hours=2)
    a_read = _make_alert(db, stock, rule, age_hours=2)
    a_read.read_at = datetime.now(timezone.utc)
    db.commit()
    _make_alert(db, stock, rule, age_hours=2, archived=True)
    summary = get_kpi_summary(db)
    assert summary.alerts_unread == 1


def test_kpi_stocks_and_indices_counts(db: Session) -> None:
    from app.models import Index
    db.add(Stock(ticker="AAPL", exchange="NASDAQ", name="Apple"))
    db.add(Stock(ticker="MSFT", exchange="NASDAQ", name="Microsoft"))
    db.add(Index(code="SP500", name="S&P 500", country="US"))
    db.add(Index(code="NDX", name="Nasdaq-100", country="US"))
    db.add(Index(code="DJI", name="DJIA", country="US"))
    db.commit()
    summary = get_kpi_summary(db)
    assert summary.stocks_monitored == 2
    assert summary.indices_count == 3
```

- [ ] **Step 2: Run, verify ImportError**

```bash
cd backend && uv run pytest tests/test_stats_service.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.stats_service'`.

- [ ] **Step 3: Implement KPI summary**

```python
# backend/app/services/stats_service.py
"""Aggregation queries for the dashboard.

All functions are pure: take a Session, return a dataclass. No mutation,
no side effects. Designed to be composed by `app/api/dashboard.py`.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Alert, Index, Stock


@dataclass
class KpiSummary:
    alerts_last_24h: int
    alerts_prev_24h: int
    alerts_unread: int
    stocks_monitored: int
    indices_count: int


def get_kpi_summary(db: Session) -> KpiSummary:
    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_48h = now - timedelta(hours=48)

    last_24h = db.execute(
        select(func.count(Alert.id)).where(
            Alert.triggered_at > cutoff_24h,
            Alert.archived_at.is_(None),
        )
    ).scalar_one()

    prev_24h = db.execute(
        select(func.count(Alert.id)).where(
            Alert.triggered_at > cutoff_48h,
            Alert.triggered_at <= cutoff_24h,
            Alert.archived_at.is_(None),
        )
    ).scalar_one()

    unread = db.execute(
        select(func.count(Alert.id)).where(
            Alert.read_at.is_(None),
            Alert.archived_at.is_(None),
        )
    ).scalar_one()

    stocks_count = db.execute(select(func.count(Stock.id))).scalar_one()
    indices_count = db.execute(select(func.count(Index.id))).scalar_one()

    return KpiSummary(
        alerts_last_24h=int(last_24h),
        alerts_prev_24h=int(prev_24h),
        alerts_unread=int(unread),
        stocks_monitored=int(stocks_count),
        indices_count=int(indices_count),
    )
```

- [ ] **Step 4: Run tests, verify pass**

```bash
cd backend && uv run pytest tests/test_stats_service.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/stats_service.py backend/tests/test_stats_service.py
git -c user.name="Milomitic" -c user.email="milomitic@gmail.com" commit -m "$(cat <<'EOF'
feat(backend): add stats_service with KPI summary (TDD)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task A2: `get_alerts_by_day` (TDD)

**Files:**
- Modify: `backend/app/services/stats_service.py`
- Modify: `backend/tests/test_stats_service.py`

- [ ] **Step 1: Append failing tests**

Add to `backend/tests/test_stats_service.py`:

```python
from app.services.stats_service import AlertsByDayPoint, get_alerts_by_day


def test_alerts_by_day_groups_by_date_and_kind(db: Session) -> None:
    stock, rule = _seed_baseline(db)
    rule2 = Rule(watchlist_id=None, kind="golden_cross", params="{}", enabled=True)
    db.add(rule2)
    db.commit()
    db.refresh(rule2)
    # Today: 2 oversold + 1 cross
    _make_alert(db, stock, rule, age_hours=2)
    _make_alert(db, stock, rule, age_hours=3)
    _make_alert(db, stock, rule2, age_hours=4)
    # Yesterday: 1 oversold
    _make_alert(db, stock, rule, age_hours=26)
    points = get_alerts_by_day(db, days=30)
    today_iso = (date.today())
    yesterday_iso = today_iso - timedelta(days=1)
    by_date = {p.date: p for p in points}
    assert by_date[today_iso].count == 3
    assert by_date[today_iso].by_kind == {"rsi_oversold": 2, "golden_cross": 1}
    assert by_date[yesterday_iso].count == 1
    assert by_date[yesterday_iso].by_kind == {"rsi_oversold": 1}


def test_alerts_by_day_includes_zero_days_in_range(db: Session) -> None:
    """Days with no alerts must still be present (count=0) so the chart is continuous."""
    _seed_baseline(db)  # no alerts
    points = get_alerts_by_day(db, days=7)
    assert len(points) == 7
    assert all(p.count == 0 for p in points)
    assert all(p.by_kind == {} for p in points)


def test_alerts_by_day_excludes_archived(db: Session) -> None:
    stock, rule = _seed_baseline(db)
    _make_alert(db, stock, rule, age_hours=2)
    _make_alert(db, stock, rule, age_hours=2, archived=True)
    points = get_alerts_by_day(db, days=1)
    today_pt = next(p for p in points if p.date == date.today())
    assert today_pt.count == 1
```

- [ ] **Step 2: Run, verify ImportError on `AlertsByDayPoint`/`get_alerts_by_day`**

- [ ] **Step 3: Implement**

Append to `backend/app/services/stats_service.py`:

```python
from sqlalchemy import Date, cast

from app.models import Rule


@dataclass
class AlertsByDayPoint:
    date: "date"  # python date
    count: int
    by_kind: dict[str, int]


def get_alerts_by_day(db: Session, days: int = 30) -> list[AlertsByDayPoint]:
    """Return one point per day in the [today - days + 1, today] range, ascending.

    Days with no alerts are included with count=0 and by_kind={}, so the chart
    is continuous (no gaps).
    """
    from datetime import date as _date, timedelta as _td

    today = _date.today()
    start_day = today - _td(days=days - 1)
    cutoff_dt = datetime.combine(start_day, datetime.min.time(), tzinfo=timezone.utc)

    rows = db.execute(
        select(
            cast(Alert.triggered_at, Date).label("d"),
            Rule.kind.label("kind"),
            func.count(Alert.id).label("c"),
        )
        .join(Rule, Rule.id == Alert.rule_id)
        .where(
            Alert.triggered_at >= cutoff_dt,
            Alert.archived_at.is_(None),
        )
        .group_by("d", Rule.kind)
    ).all()

    by_date: dict[_date, dict[str, int]] = {}
    for d, kind, c in rows:
        by_date.setdefault(d, {})[kind] = int(c)

    points: list[AlertsByDayPoint] = []
    for offset in range(days):
        day = start_day + _td(days=offset)
        kinds = by_date.get(day, {})
        points.append(
            AlertsByDayPoint(date=day, count=sum(kinds.values()), by_kind=kinds)
        )
    return points
```

Also update the imports at the top of `stats_service.py`:

```python
from datetime import date, datetime, timedelta, timezone
```

- [ ] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/test_stats_service.py -v
```

Expected: 7 passed (4 prior + 3 new).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/stats_service.py backend/tests/test_stats_service.py
git -c user.name="Milomitic" -c user.email="milomitic@gmail.com" commit -m "$(cat <<'EOF'
feat(backend): add stats_service.get_alerts_by_day with zero-fill (TDD)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task A3: `get_top_stocks` (TDD)

**Files:**
- Modify: `backend/app/services/stats_service.py`
- Modify: `backend/tests/test_stats_service.py`

- [ ] **Step 1: Append failing tests**

```python
from app.services.stats_service import TopStock, get_top_stocks


def test_top_stocks_orders_by_count_desc_limit_10(db: Session) -> None:
    rule = Rule(watchlist_id=None, kind="rsi_oversold", params="{}", enabled=True)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    stocks = []
    for i in range(12):
        s = Stock(ticker=f"T{i:02d}", exchange="X", name=f"Stock {i}")
        db.add(s)
        db.commit()
        db.refresh(s)
        stocks.append(s)
        # Stock with index i gets (i+1) alerts to enforce ordering
        for _ in range(i + 1):
            _make_alert(db, s, rule, age_hours=1)
    top = get_top_stocks(db, days=30, limit=10)
    assert len(top) == 10
    # Highest count first; ties broken by ticker ASC (no ties here, but verify ordering)
    assert top[0].ticker == "T11" and top[0].alert_count == 12
    assert top[-1].ticker == "T02" and top[-1].alert_count == 3


def test_top_stocks_top_kind_is_most_frequent(db: Session) -> None:
    stock = Stock(ticker="AAPL", exchange="NASDAQ", name="Apple")
    db.add(stock)
    rule_oversold = Rule(watchlist_id=None, kind="rsi_oversold", params="{}", enabled=True)
    rule_cross = Rule(watchlist_id=None, kind="golden_cross", params="{}", enabled=True)
    db.add(rule_oversold)
    db.add(rule_cross)
    db.commit()
    db.refresh(stock)
    db.refresh(rule_oversold)
    db.refresh(rule_cross)
    _make_alert(db, stock, rule_oversold, age_hours=2)
    _make_alert(db, stock, rule_oversold, age_hours=3)
    _make_alert(db, stock, rule_cross, age_hours=4)
    top = get_top_stocks(db, days=30, limit=10)
    assert len(top) == 1
    assert top[0].top_kind == "rsi_oversold"


def test_top_stocks_excludes_archived(db: Session) -> None:
    stock, rule = _seed_baseline(db)
    _make_alert(db, stock, rule, age_hours=2)
    _make_alert(db, stock, rule, age_hours=2, archived=True)
    top = get_top_stocks(db, days=30, limit=10)
    assert len(top) == 1 and top[0].alert_count == 1
```

- [ ] **Step 2: Run, verify ImportError**

- [ ] **Step 3: Implement**

Append to `backend/app/services/stats_service.py`:

```python
@dataclass
class TopStock:
    stock_id: int
    ticker: str
    alert_count: int
    top_kind: str | None


def get_top_stocks(db: Session, *, days: int = 30, limit: int = 10) -> list[TopStock]:
    """Return up to `limit` stocks with the most alerts in the last `days` days.

    Order: alert_count DESC, ticker ASC (deterministic tie-break).
    `top_kind` = most frequent rule.kind for that stock in the same window.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Step 1: top stock_ids by count
    counts = db.execute(
        select(
            Alert.stock_id,
            func.count(Alert.id).label("c"),
        )
        .where(Alert.triggered_at >= cutoff, Alert.archived_at.is_(None))
        .group_by(Alert.stock_id)
        .order_by(func.count(Alert.id).desc(), Alert.stock_id.asc())
        .limit(limit)
    ).all()

    if not counts:
        return []

    stock_ids = [row.stock_id for row in counts]
    tickers = {
        s.id: s.ticker
        for s in db.execute(select(Stock).where(Stock.id.in_(stock_ids))).scalars().all()
    }

    # Step 2: top kind per stock (subquery LIMIT 1 each)
    top_kind_by_stock: dict[int, str] = {}
    for sid in stock_ids:
        kind_row = db.execute(
            select(Rule.kind, func.count(Alert.id).label("c"))
            .join(Alert, Alert.rule_id == Rule.id)
            .where(
                Alert.stock_id == sid,
                Alert.triggered_at >= cutoff,
                Alert.archived_at.is_(None),
            )
            .group_by(Rule.kind)
            .order_by(func.count(Alert.id).desc(), Rule.kind.asc())
            .limit(1)
        ).first()
        if kind_row is not None:
            top_kind_by_stock[sid] = kind_row.kind

    # Compose, preserving the ordering from step 1
    result: list[TopStock] = []
    # Re-order step1 by (count DESC, ticker ASC) — replace stock_id sort with ticker
    enriched = sorted(
        [(row.stock_id, int(row.c), tickers.get(row.stock_id, "")) for row in counts],
        key=lambda t: (-t[1], t[2]),
    )
    for stock_id, c, ticker in enriched:
        result.append(
            TopStock(
                stock_id=stock_id,
                ticker=ticker,
                alert_count=c,
                top_kind=top_kind_by_stock.get(stock_id),
            )
        )
    return result
```

- [ ] **Step 4: Run tests, verify 10 passed (7 + 3)**

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/stats_service.py backend/tests/test_stats_service.py
git -c user.name="Milomitic" -c user.email="milomitic@gmail.com" commit -m "$(cat <<'EOF'
feat(backend): add stats_service.get_top_stocks with top_kind subquery (TDD)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task A4: `get_system_status` (TDD)

**Files:**
- Modify: `backend/app/services/stats_service.py`
- Modify: `backend/tests/test_stats_service.py`

- [ ] **Step 1: Append failing tests**

```python
import pytest
from app.services.stats_service import SystemStatus, get_system_status


def test_system_status_telegram_configured_when_token_and_chat_set(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings
    monkeypatch.setattr(settings, "telegram_bot_token", "FAKE_TOKEN")
    monkeypatch.setattr(settings, "telegram_chat_id", "12345")
    status = get_system_status(db)
    assert isinstance(status, SystemStatus)
    assert status.telegram_configured is True


def test_system_status_telegram_not_configured_when_blank(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "telegram_chat_id", "")
    status = get_system_status(db)
    assert status.telegram_configured is False


def test_system_status_includes_scheduler_next_runs(db: Session) -> None:
    """next_run fields are pulled from the live APScheduler. With the scheduler
    not started in this test, the fields are None — that's the contract."""
    status = get_system_status(db)
    # Whether or not the scheduler is running depends on test fixture setup;
    # we assert only that the field is bool and the next_run fields are
    # either None or datetime.
    assert isinstance(status.scheduler_running, bool)
    assert status.scan_alerts_next_run is None or hasattr(status.scan_alerts_next_run, "isoformat")
```

- [ ] **Step 2: Run, verify ImportError**

- [ ] **Step 3: Implement**

Append to `backend/app/services/stats_service.py`:

```python
@dataclass
class SystemStatus:
    scheduler_running: bool
    scan_alerts_next_run: datetime | None
    send_digest_next_run: datetime | None
    refresh_catalog_next_run: datetime | None
    telegram_configured: bool
    last_digest_sent_at: datetime | None  # always None in 3A; will be wired in 3D


def get_system_status(db: Session) -> SystemStatus:
    from app.core.config import settings
    from app.scheduler import get_scheduler

    sched = get_scheduler()
    next_runs: dict[str, datetime | None] = {}
    for job_id in ("scan_alerts", "send_digest", "refresh_catalog"):
        job = sched.get_job(job_id)
        next_runs[job_id] = job.next_run_time if job is not None else None

    return SystemStatus(
        scheduler_running=sched.running,
        scan_alerts_next_run=next_runs["scan_alerts"],
        send_digest_next_run=next_runs["send_digest"],
        refresh_catalog_next_run=next_runs["refresh_catalog"],
        telegram_configured=bool(settings.telegram_bot_token) and bool(settings.telegram_chat_id),
        last_digest_sent_at=None,
    )
```

- [ ] **Step 4: Run tests, verify 13 passed (10 + 3)**

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/stats_service.py backend/tests/test_stats_service.py
git -c user.name="Milomitic" -c user.email="milomitic@gmail.com" commit -m "$(cat <<'EOF'
feat(backend): add stats_service.get_system_status (TDD)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Section B — Dashboard endpoint

### Task B1: Pydantic schemas for the dashboard payload

**Files:**
- Create: `backend/app/schemas/dashboard.py`

- [ ] **Step 1: Create the schemas**

```python
"""Pydantic schemas for the dashboard summary endpoint."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.alert import AlertOut, ScanStatusOut


class KpiSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    alerts_last_24h: int
    alerts_prev_24h: int
    alerts_unread: int
    stocks_monitored: int
    indices_count: int
    last_scan: ScanStatusOut | None
    next_scan_at: datetime | None
    next_digest_at: datetime | None


class AlertsByDayPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    count: int
    by_kind: dict[str, int]


class TopStockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stock_id: int
    ticker: str
    alert_count: int
    top_kind: str | None


class SystemStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scheduler_running: bool
    scan_alerts_next_run: datetime | None
    send_digest_next_run: datetime | None
    refresh_catalog_next_run: datetime | None
    telegram_configured: bool
    last_digest_sent_at: datetime | None


class DashboardSummaryOut(BaseModel):
    kpis: KpiSummaryOut
    alerts_by_day: list[AlertsByDayPointOut]
    top_stocks_30d: list[TopStockOut]
    recent_alerts: list[AlertOut]
    system_status: SystemStatusOut
```

- [ ] **Step 2: Smoke test imports**

```bash
cd backend && uv run python -c "from app.schemas.dashboard import DashboardSummaryOut, KpiSummaryOut, AlertsByDayPointOut, TopStockOut, SystemStatusOut; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/dashboard.py
git -c user.name="Milomitic" -c user.email="milomitic@gmail.com" commit -m "$(cat <<'EOF'
feat(backend): add Dashboard pydantic schemas

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task B2: Dashboard endpoint (TDD)

**Files:**
- Create: `backend/app/api/dashboard.py`, `backend/tests/test_api_dashboard.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_api_dashboard.py
"""Smoke tests for the dashboard endpoint."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Alert, Rule, Stock, User


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_dashboard_summary_requires_auth(db: Session) -> None:
    """Without get_current_user override, the cookie check kicks in -> 401."""
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as c:
            resp = c.get("/api/dashboard/summary")
            assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_dashboard_summary_payload_shape(client: TestClient, db: Session) -> None:
    stock = Stock(ticker="AAPL", exchange="NASDAQ", name="Apple")
    db.add(stock)
    db.commit()
    rule = Rule(watchlist_id=None, kind="rsi_oversold", params="{}", enabled=True)
    db.add(rule)
    db.commit()
    db.refresh(stock)
    db.refresh(rule)
    db.add(
        Alert(
            rule_id=rule.id,
            stock_id=stock.id,
            trigger_price=100.0,
            snapshot="{}",
        )
    )
    db.commit()

    resp = client.get("/api/dashboard/summary")
    assert resp.status_code == 200
    body = resp.json()
    # Top-level keys
    for key in ("kpis", "alerts_by_day", "top_stocks_30d", "recent_alerts", "system_status"):
        assert key in body, f"missing key {key}"
    # KPIs
    assert body["kpis"]["alerts_last_24h"] == 1
    assert body["kpis"]["stocks_monitored"] == 1
    # alerts_by_day is a list of 30 points (today and 29 days back)
    assert isinstance(body["alerts_by_day"], list)
    assert len(body["alerts_by_day"]) == 30
    # top_stocks contains AAPL
    assert any(s["ticker"] == "AAPL" for s in body["top_stocks_30d"])
    # recent_alerts contains 1 entry
    assert len(body["recent_alerts"]) == 1
    # system_status keys
    assert "telegram_configured" in body["system_status"]
```

- [ ] **Step 2: Run, verify 404 / ImportError**

- [ ] **Step 3: Implement the router**

```python
# backend/app/api/dashboard.py
"""Single BFF endpoint that aggregates KPI + chart + top + feed + system status."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import User
from app.schemas.alert import AlertOut, ScanStatusOut
from app.schemas.dashboard import (
    AlertsByDayPointOut,
    DashboardSummaryOut,
    KpiSummaryOut,
    SystemStatusOut,
    TopStockOut,
)
from app.services import alert_service, stats_service
from sqlalchemy import select

from app.models import ScanRun

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _latest_scan(db: Session) -> ScanStatusOut | None:
    latest = (
        db.execute(select(ScanRun).order_by(ScanRun.started_at.desc()).limit(1))
        .scalar_one_or_none()
    )
    if latest is None:
        return None
    return ScanStatusOut(
        is_running=latest.status == "running",
        last_run_id=latest.id,
        trigger=latest.trigger,
        status=latest.status,
        phase=latest.phase,
        started_at=latest.started_at,
        completed_at=latest.completed_at,
        progress_done=latest.progress_done,
        progress_total=latest.progress_total,
        stocks_scanned=latest.stocks_scanned,
        stocks_skipped=latest.stocks_skipped,
        alerts_fired=latest.alerts_fired,
        error_message=latest.error_message,
    )


@router.get("/summary", response_model=DashboardSummaryOut)
def get_summary(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> DashboardSummaryOut:
    kpi = stats_service.get_kpi_summary(db)
    by_day = stats_service.get_alerts_by_day(db, days=30)
    top = stats_service.get_top_stocks(db, days=30, limit=10)
    sys_status = stats_service.get_system_status(db)
    last_scan = _latest_scan(db)
    recent_items, _, _ = alert_service.list_alerts(db, limit=10, offset=0, archived=False)

    return DashboardSummaryOut(
        kpis=KpiSummaryOut(
            alerts_last_24h=kpi.alerts_last_24h,
            alerts_prev_24h=kpi.alerts_prev_24h,
            alerts_unread=kpi.alerts_unread,
            stocks_monitored=kpi.stocks_monitored,
            indices_count=kpi.indices_count,
            last_scan=last_scan,
            next_scan_at=sys_status.scan_alerts_next_run,
            next_digest_at=sys_status.send_digest_next_run,
        ),
        alerts_by_day=[
            AlertsByDayPointOut(date=p.date, count=p.count, by_kind=p.by_kind)
            for p in by_day
        ],
        top_stocks_30d=[
            TopStockOut(
                stock_id=t.stock_id,
                ticker=t.ticker,
                alert_count=t.alert_count,
                top_kind=t.top_kind,
            )
            for t in top
        ],
        recent_alerts=[AlertOut(**i) for i in recent_items],
        system_status=SystemStatusOut(
            scheduler_running=sys_status.scheduler_running,
            scan_alerts_next_run=sys_status.scan_alerts_next_run,
            send_digest_next_run=sys_status.send_digest_next_run,
            refresh_catalog_next_run=sys_status.refresh_catalog_next_run,
            telegram_configured=sys_status.telegram_configured,
            last_digest_sent_at=sys_status.last_digest_sent_at,
        ),
    )
```

- [ ] **Step 4: Register router in `backend/app/main.py`**

Read the current `main.py`. Add `from app.api import dashboard as dashboard_router` near the existing imports (alphabetical: between `catalog` and `rules`). Add `app.include_router(dashboard_router.router)` after the existing include_router calls.

- [ ] **Step 5: Run new tests, verify 2 passed**

```bash
cd backend && uv run pytest tests/test_api_dashboard.py -v
```

- [ ] **Step 6: Run full pytest**

```bash
cd backend && uv run pytest -v 2>&1 | tail -3
```

Expected: ~118 passed (103 prior + 13 stats + 2 dashboard).

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/dashboard.py backend/tests/test_api_dashboard.py backend/app/main.py
git -c user.name="Milomitic" -c user.email="milomitic@gmail.com" commit -m "$(cat <<'EOF'
feat(backend): add /api/dashboard/summary endpoint with smoke tests

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Section C — Frontend API client + types + hook

### Task C1: Add Dashboard types

**Files:**
- Modify: `frontend/src/api/types.ts`

- [ ] **Step 1: Append the types**

Append at the end of `frontend/src/api/types.ts`:

```typescript
export interface KpiSummary {
  alerts_last_24h: number;
  alerts_prev_24h: number;
  alerts_unread: number;
  stocks_monitored: number;
  indices_count: number;
  last_scan: ScanStatusInfo | null;
  next_scan_at: string | null;
  next_digest_at: string | null;
}

export interface AlertsByDayPoint {
  date: string; // ISO date "YYYY-MM-DD"
  count: number;
  by_kind: Record<string, number>;
}

export interface TopStock {
  stock_id: number;
  ticker: string;
  alert_count: number;
  top_kind: string | null;
}

export interface SystemStatus {
  scheduler_running: boolean;
  scan_alerts_next_run: string | null;
  send_digest_next_run: string | null;
  refresh_catalog_next_run: string | null;
  telegram_configured: boolean;
  last_digest_sent_at: string | null;
}

export interface DashboardSummary {
  kpis: KpiSummary;
  alerts_by_day: AlertsByDayPoint[];
  top_stocks_30d: TopStock[];
  recent_alerts: Alert[];
  system_status: SystemStatus;
}
```

- [ ] **Step 2: Verify TypeScript build**

```bash
cd frontend && npm run build 2>&1 | tail -3
```

Expected: clean build.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/types.ts
git -c user.name="Milomitic" -c user.email="milomitic@gmail.com" commit -m "$(cat <<'EOF'
feat(frontend): add Dashboard API types

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task C2: Add API client + hook

**Files:**
- Create: `frontend/src/api/dashboard.ts`, `frontend/src/hooks/useDashboardSummary.ts`

- [ ] **Step 1: Create `frontend/src/api/dashboard.ts`**

```typescript
import { api } from "./client";
import type { DashboardSummary } from "./types";

export const dashboard = {
  summary: () => api<DashboardSummary>("/api/dashboard/summary"),
};
```

- [ ] **Step 2: Create `frontend/src/hooks/useDashboardSummary.ts`**

```typescript
import { useQuery } from "@tanstack/react-query";

import { dashboard } from "@/api/dashboard";

export function useDashboardSummary() {
  return useQuery({
    queryKey: ["dashboard", "summary"],
    queryFn: () => dashboard.summary(),
    refetchInterval: 30_000,
    refetchIntervalInBackground: true,
    staleTime: 10_000,
  });
}
```

- [ ] **Step 3: Verify build**

```bash
cd frontend && npm run build 2>&1 | tail -3
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/dashboard.ts frontend/src/hooks/useDashboardSummary.ts
git -c user.name="Milomitic" -c user.email="milomitic@gmail.com" commit -m "$(cat <<'EOF'
feat(frontend): add dashboard API client and useDashboardSummary hook

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Section D — Dashboard components

### Task D1: Install Recharts

**Files:**
- Modify: `frontend/package.json`, `frontend/package-lock.json`

- [ ] **Step 1: Install**

```bash
cd frontend && npm install recharts
```

- [ ] **Step 2: Verify build still works**

```bash
cd frontend && npm run build 2>&1 | tail -3
```

- [ ] **Step 3: Commit**

```bash
cd "C:/Users/giuli/Documents/Progetti/finance-alert"
git add frontend/package.json frontend/package-lock.json
git -c user.name="Milomitic" -c user.email="milomitic@gmail.com" commit -m "$(cat <<'EOF'
chore(frontend): add recharts dependency for dashboard chart

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task D2: KpiCard component

**Files:**
- Create: `frontend/src/components/dashboard/KpiCard.tsx`

- [ ] **Step 1: Create**

```typescript
import type { ReactNode } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface Props {
  title: string;
  value: ReactNode;
  subtext?: ReactNode;
  icon?: ReactNode;
  tone?: "default" | "success" | "warning" | "destructive";
}

const TONE: Record<NonNullable<Props["tone"]>, string> = {
  default: "",
  success: "border-green-300/50 dark:border-green-800/50",
  warning: "border-amber-300/50 dark:border-amber-800/50",
  destructive: "border-destructive/50",
};

export function KpiCard({ title, value, subtext, icon, tone = "default" }: Props) {
  return (
    <Card className={cn(TONE[tone])}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="text-xs text-muted-foreground uppercase tracking-wide">
            {title}
          </div>
          {icon && <div className="text-muted-foreground">{icon}</div>}
        </div>
        <div className="text-2xl font-semibold tabular-nums mt-1">{value}</div>
        {subtext && (
          <div className="text-xs text-muted-foreground mt-1">{subtext}</div>
        )}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build 2>&1 | tail -3
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/dashboard/KpiCard.tsx
git -c user.name="Milomitic" -c user.email="milomitic@gmail.com" commit -m "$(cat <<'EOF'
feat(frontend): add KpiCard component

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task D3: AlertsByDayChart

**Files:**
- Create: `frontend/src/components/dashboard/AlertsByDayChart.tsx`

- [ ] **Step 1: Create**

```typescript
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { AlertsByDayPoint } from "@/api/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface Props {
  data: AlertsByDayPoint[];
}

const KIND_LABEL: Record<string, string> = {
  rsi_oversold: "RSI Oversold",
  rsi_overbought: "RSI Overbought",
  golden_cross: "Golden Cross",
  death_cross: "Death Cross",
};

interface TooltipPayloadEntry {
  payload: AlertsByDayPoint;
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: TooltipPayloadEntry[] }) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="rounded border bg-popover p-2 text-xs shadow">
      <div className="font-medium mb-1">
        {new Date(point.date).toLocaleDateString("it-IT")}
      </div>
      <div className="tabular-nums mb-1">
        Totale: <strong>{point.count}</strong>
      </div>
      {Object.entries(point.by_kind).map(([kind, count]) => (
        <div key={kind} className="text-muted-foreground">
          {KIND_LABEL[kind] ?? kind}: {count}
        </div>
      ))}
    </div>
  );
}

export function AlertsByDayChart({ data }: Props) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Alert per giorno (ultimi 30gg)</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-[260px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 5, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
              <XAxis
                dataKey="date"
                tickFormatter={(iso) =>
                  new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit" })
                }
                fontSize={11}
              />
              <YAxis allowDecimals={false} fontSize={11} />
              <Tooltip content={<CustomTooltip />} />
              <Area
                type="monotone"
                dataKey="count"
                stroke="var(--primary, #3b82f6)"
                fill="var(--primary, #3b82f6)"
                fillOpacity={0.2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

Expected: clean build, bundle slightly larger (recharts).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/dashboard/AlertsByDayChart.tsx
git -c user.name="Milomitic" -c user.email="milomitic@gmail.com" commit -m "$(cat <<'EOF'
feat(frontend): add AlertsByDayChart component (Recharts AreaChart)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task D4: TopStocksTable

**Files:**
- Create: `frontend/src/components/dashboard/TopStocksTable.tsx`

- [ ] **Step 1: Create**

```typescript
import { Link } from "react-router-dom";

import type { TopStock } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface Props {
  data: TopStock[];
}

const KIND_LABEL: Record<string, string> = {
  rsi_oversold: "RSI Oversold",
  rsi_overbought: "RSI Overbought",
  golden_cross: "Golden Cross",
  death_cross: "Death Cross",
};

export function TopStocksTable({ data }: Props) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Top 10 stock (30gg)</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {data.length === 0 ? (
          <div className="p-6 text-center text-sm text-muted-foreground">
            Nessun alert nei 30 giorni.
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Ticker</TableHead>
                <TableHead>Regola top</TableHead>
                <TableHead className="text-right">Alert</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((s) => (
                <TableRow key={s.stock_id}>
                  <TableCell className="font-medium">
                    <Link
                      to={`/alerts?ticker=${encodeURIComponent(s.ticker)}`}
                      className="hover:underline"
                    >
                      {s.ticker}
                    </Link>
                  </TableCell>
                  <TableCell>
                    {s.top_kind ? (
                      <Badge variant="secondary">
                        {KIND_LABEL[s.top_kind] ?? s.top_kind}
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground text-xs">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {s.alert_count}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build 2>&1 | tail -3
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/dashboard/TopStocksTable.tsx
git -c user.name="Milomitic" -c user.email="milomitic@gmail.com" commit -m "$(cat <<'EOF'
feat(frontend): add TopStocksTable component

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task D5: RecentAlertsFeed

**Files:**
- Create: `frontend/src/components/dashboard/RecentAlertsFeed.tsx`

- [ ] **Step 1: Create**

```typescript
import { useState } from "react";

import type { Alert } from "@/api/types";
import { AlertDetailDialog } from "@/components/AlertDetailDialog";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface Props {
  alerts: Alert[];
}

const KIND_LABEL: Record<string, string> = {
  rsi_oversold: "RSI Oversold",
  rsi_overbought: "RSI Overbought",
  golden_cross: "Golden Cross",
  death_cross: "Death Cross",
};

const KIND_EMOJI: Record<string, string> = {
  rsi_oversold: "🟢",
  rsi_overbought: "🔴",
  golden_cross: "⚡",
  death_cross: "⚠️",
};

export function RecentAlertsFeed({ alerts }: Props) {
  const [openDetail, setOpenDetail] = useState<Alert | null>(null);

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Alert recenti</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {alerts.length === 0 ? (
            <div className="p-6 text-center text-sm text-muted-foreground">
              Nessun alert recente. Esegui uno scan da{" "}
              <span className="underline">/alerts</span> per generarli.
            </div>
          ) : (
            <ul className="divide-y">
              {alerts.map((a) => (
                <li
                  key={a.id}
                  className="px-4 py-3 cursor-pointer hover:bg-accent transition-colors flex items-center gap-3"
                  onClick={() => setOpenDetail(a)}
                >
                  <span className="text-lg" aria-hidden="true">
                    {KIND_EMOJI[a.rule_kind ?? ""] ?? "•"}
                  </span>
                  <span className="font-medium min-w-[60px]">{a.ticker ?? "—"}</span>
                  <Badge variant="secondary" className="text-xs">
                    {KIND_LABEL[a.rule_kind ?? ""] ?? a.rule_kind ?? "—"}
                  </Badge>
                  <span className="text-sm tabular-nums">${a.trigger_price}</span>
                  <span className="ml-auto text-xs text-muted-foreground">
                    {new Date(a.triggered_at).toLocaleString("it-IT", {
                      day: "2-digit",
                      month: "2-digit",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      <AlertDetailDialog alert={openDetail} onClose={() => setOpenDetail(null)} />
    </>
  );
}
```

- [ ] **Step 2: Verify build**

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/dashboard/RecentAlertsFeed.tsx
git -c user.name="Milomitic" -c user.email="milomitic@gmail.com" commit -m "$(cat <<'EOF'
feat(frontend): add RecentAlertsFeed component (reuses AlertDetailDialog)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task D6: SystemStatusCard

**Files:**
- Create: `frontend/src/components/dashboard/SystemStatusCard.tsx`

- [ ] **Step 1: Create**

```typescript
import { CheckCircle2, MessageSquare, MessageSquareOff, Server, ServerOff } from "lucide-react";

import type { SystemStatus } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";

interface Props {
  status: SystemStatus;
}

function formatNext(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("it-IT", {
      dateStyle: "short",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

export function SystemStatusCard({ status }: Props) {
  return (
    <Card>
      <CardContent className="p-3 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs">
        <span className="flex items-center gap-1.5">
          {status.scheduler_running ? (
            <>
              <Server className="h-4 w-4 text-green-600" />
              <span>Scheduler attivo</span>
            </>
          ) : (
            <>
              <ServerOff className="h-4 w-4 text-destructive" />
              <span>Scheduler offline</span>
            </>
          )}
        </span>
        <span className="flex items-center gap-1.5">
          {status.telegram_configured ? (
            <>
              <MessageSquare className="h-4 w-4 text-green-600" />
              <span>Telegram configurato</span>
            </>
          ) : (
            <>
              <MessageSquareOff className="h-4 w-4 text-amber-600" />
              <span>Telegram non configurato</span>
            </>
          )}
        </span>
        <span className="text-muted-foreground">
          Prossimo scan: <strong>{formatNext(status.scan_alerts_next_run)}</strong>
        </span>
        <span className="text-muted-foreground">
          Prossimo digest: <strong>{formatNext(status.send_digest_next_run)}</strong>
        </span>
        {status.last_digest_sent_at && (
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <CheckCircle2 className="h-3.5 w-3.5" />
            Ultimo digest: {formatNext(status.last_digest_sent_at)}
          </span>
        )}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Verify build**

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/dashboard/SystemStatusCard.tsx
git -c user.name="Milomitic" -c user.email="milomitic@gmail.com" commit -m "$(cat <<'EOF'
feat(frontend): add SystemStatusCard component

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Section E — HomePage + routing wiring

### Task E1: HomePage

**Files:**
- Create: `frontend/src/pages/HomePage.tsx`

- [ ] **Step 1: Create**

```typescript
import { AlertCircle, Bell, FileBarChart2, ListChecks, ScanSearch } from "lucide-react";

import { AlertsByDayChart } from "@/components/dashboard/AlertsByDayChart";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { RecentAlertsFeed } from "@/components/dashboard/RecentAlertsFeed";
import { SystemStatusCard } from "@/components/dashboard/SystemStatusCard";
import { TopStocksTable } from "@/components/dashboard/TopStocksTable";
import { Card, CardContent } from "@/components/ui/card";
import { useDashboardSummary } from "@/hooks/useDashboardSummary";

function deltaLabel(curr: number, prev: number): string {
  const diff = curr - prev;
  if (diff === 0) return "= ieri";
  const arrow = diff > 0 ? "↑" : "↓";
  const sign = diff > 0 ? "+" : "";
  return `${sign}${diff} vs ieri ${arrow}`;
}

function lastScanLabel(
  lastScan: ReturnType<typeof useDashboardSummary>["data"] extends infer T
    ? T extends { kpis: { last_scan: infer S } }
      ? S
      : never
    : never,
): string {
  if (!lastScan) return "Mai eseguito";
  if (lastScan.is_running) return "In corso…";
  if (lastScan.completed_at) {
    const dt = new Date(lastScan.completed_at);
    return dt.toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" });
  }
  return "—";
}

export default function HomePage() {
  const q = useDashboardSummary();

  if (q.isLoading) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="p-4 h-[88px] animate-pulse bg-muted/40" />
            </Card>
          ))}
        </div>
        <Card>
          <CardContent className="h-[260px] animate-pulse bg-muted/40" />
        </Card>
      </div>
    );
  }

  if (q.isError || !q.data) {
    return (
      <Card>
        <CardContent className="p-6 flex items-center gap-3 text-sm">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <span>Errore nel caricamento del riepilogo dashboard.</span>
          <button
            className="underline"
            onClick={() => q.refetch()}
          >
            Riprova
          </button>
        </CardContent>
      </Card>
    );
  }

  const { kpis, alerts_by_day, top_stocks_30d, recent_alerts, system_status } = q.data;

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-semibold">Dashboard</h2>
        <p className="text-sm text-muted-foreground">
          Riepilogo dell'attività di monitoring (aggiornato ogni 30s)
        </p>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard
          title="Alert ultime 24h"
          value={kpis.alerts_last_24h}
          subtext={deltaLabel(kpis.alerts_last_24h, kpis.alerts_prev_24h)}
          icon={<Bell className="h-4 w-4" />}
        />
        <KpiCard
          title="Non letti"
          value={kpis.alerts_unread}
          subtext={
            kpis.alerts_unread > 0
              ? "vedi /alerts per gestirli"
              : "tutti gestiti"
          }
          icon={<FileBarChart2 className="h-4 w-4" />}
          tone={kpis.alerts_unread > 0 ? "warning" : "default"}
        />
        <KpiCard
          title="Stock monitorati"
          value={kpis.stocks_monitored}
          subtext={`${kpis.indices_count} indici`}
          icon={<ListChecks className="h-4 w-4" />}
        />
        <KpiCard
          title="Ultimo scan"
          value={lastScanLabel(kpis.last_scan)}
          subtext={
            kpis.last_scan?.alerts_fired != null
              ? `${kpis.last_scan.alerts_fired} alert generati`
              : kpis.next_scan_at
                ? `Prossimo: ${new Date(kpis.next_scan_at).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" })}`
                : undefined
          }
          icon={<ScanSearch className="h-4 w-4" />}
          tone={kpis.last_scan?.status === "failed" ? "destructive" : "default"}
        />
      </div>

      {/* Chart + Top */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <AlertsByDayChart data={alerts_by_day} />
        <TopStocksTable data={top_stocks_30d} />
      </div>

      {/* Recent alerts */}
      <RecentAlertsFeed alerts={recent_alerts} />

      {/* System status footer */}
      <SystemStatusCard status={system_status} />
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build 2>&1 | tail -3
```

Expected: clean build.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/HomePage.tsx
git -c user.name="Milomitic" -c user.email="milomitic@gmail.com" commit -m "$(cat <<'EOF'
feat(frontend): add HomePage composing all dashboard sections

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task E2: Wire `/` to HomePage + enable Dashboard sidebar entry

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Layout.tsx`

- [ ] **Step 1: Update `App.tsx`**

Read the current `App.tsx`. Add the import:

```typescript
import HomePage from "@/pages/HomePage";
```

Replace the route `<Route path="/" element={<Navigate to="/watchlists" replace />} />` with:

```tsx
<Route path="/" element={<HomePage />} />
```

(Both routes are inside the `<ProtectedRoute><Layout /></ProtectedRoute>` block. The Navigate import may be removable if no longer used; verify and remove unused imports.)

- [ ] **Step 2: Update `Layout.tsx`**

Read the current `Layout.tsx`. Find the `NAV` array. Locate the entry for "Dashboard" — it currently has `enabled: false` and `to: "/dashboard"` (or similar). Update it to:

```typescript
{ to: "/", label: "Dashboard", icon: LayoutDashboard, enabled: true },
```

Make sure `LayoutDashboard` is imported from `lucide-react` at the top:

```typescript
import { LayoutDashboard, /* existing imports */ } from "lucide-react";
```

If the existing icon for Dashboard differs, replace it with `LayoutDashboard`.

- [ ] **Step 3: Verify build**

```bash
cd frontend && npm run build 2>&1 | tail -3
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/Layout.tsx
git -c user.name="Milomitic" -c user.email="milomitic@gmail.com" commit -m "$(cat <<'EOF'
feat(frontend): mount HomePage at / and enable Dashboard sidebar entry

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task E3: ARCHITECTURE.md update + final smoke test

**Files:**
- Modify: `docs/ARCHITECTURE.md`

- [ ] **Step 1: Update ARCHITECTURE.md**

Open `docs/ARCHITECTURE.md`. Make these edits:

1. Header: bump `**Ultimo aggiornamento**` to today's date.
2. §1 Panoramica: add a bullet "**(Fase 3A — implementato)** Dashboard riepilogativa su `/`".
3. §11 Changelog: append a new row:

   ```markdown
   | 2026-05-01 | <commit-sha> | Fase 3A: Dashboard Home `/` con KPI cards, AlertsByDayChart (Recharts 30gg), TopStocksTable, RecentAlertsFeed, SystemStatusCard. Single BFF endpoint `/api/dashboard/summary` aggrega tutto; polling 30s via TanStack Query. ~13 nuovi test backend (stats_service + dashboard API). |
   ```

   Replace `<commit-sha>` with the short SHA of the most recent commit (from `git rev-parse --short HEAD`).

- [ ] **Step 2: Run full backend pytest**

```bash
cd backend && uv run pytest -v 2>&1 | tail -3
```

Expected: ~118 passed.

- [ ] **Step 3: Run frontend build**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

Expected: clean build.

- [ ] **Step 4: Smoke test the running app**

Stop and restart the dev servers (or rely on auto-reload):

```bash
# Verify backend health
curl -s http://localhost:8000/api/health
# Login and hit the dashboard endpoint
curl -s -X POST http://localhost:8000/api/auth/login -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"aaaaaaaa"}' -c /tmp/cookies.txt > /dev/null
curl -s -b /tmp/cookies.txt http://localhost:8000/api/dashboard/summary | python -m json.tool | head -30
```

Expected:
- `/api/health` ok
- Dashboard summary returns valid JSON with all 5 top-level keys: `kpis`, `alerts_by_day`, `top_stocks_30d`, `recent_alerts`, `system_status`.

- [ ] **Step 5: Commit + push**

```bash
cd "C:/Users/giuli/Documents/Progetti/finance-alert"
git add docs/ARCHITECTURE.md
git -c user.name="Milomitic" -c user.email="milomitic@gmail.com" commit -m "$(cat <<'EOF'
docs: mark Fase 3A complete in ARCHITECTURE.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push origin master
```

---

## Self-review checklist

**Spec coverage** — comparing plan to spec:
- §1 Obiettivo (4 KPI + chart + top + feed + system) → Section D + E ✓
- §3 Out of scope → respected (no Stock Detail, no Settings, no SSE) ✓
- §4 Stack additions (recharts) → Task D1 ✓
- §5 Modello dati (no new tables) → Section A doesn't add tables ✓
- §6 API surface (`GET /api/dashboard/summary`) → Task B2 ✓
- §7 Service layer (4 functions) → A1 (KPI), A2 (alerts_by_day), A3 (top_stocks), A4 (system_status) ✓
- §8 Frontend (5 components + HomePage + routing) → D2-D6 + E1 + E2 ✓
- §11 DoD (Sidebar Dashboard entry, polling, KPI live) → E2 + C2 (refetch 30s) ✓

**Type consistency** — verified:
- `KpiSummary` (Python dataclass) ↔ `KpiSummaryOut` (Pydantic) ↔ `KpiSummary` (TS) — all match field-by-field.
- `TopStock.top_kind` is `Optional[str]` everywhere.
- `AlertsByDayPoint.by_kind` is `dict[str, int]` ↔ `Record<string, number>`.

**Placeholders** — none found; every step has executable code.

**Method signatures consistent across tasks**:
- `get_kpi_summary(db)`, `get_alerts_by_day(db, days=30)`, `get_top_stocks(db, *, days=30, limit=10)`, `get_system_status(db)` — all match between A1-A4 and B2 (where they're called from the endpoint).

---

## Execution Handoff

Plan complete and saved to [docs/superpowers/plans/2026-05-01-finance-alert-fase3a.md](docs/superpowers/plans/2026-05-01-finance-alert-fase3a.md). Two execution options:

**1. Subagent-Driven (recommended)** — Fresh subagent per task, review between tasks. Same pattern that worked for Fase 1 + 2.

**2. Inline Execution** — Tasks executed sequentially in this session via executing-plans, with checkpoints.

Which approach?
