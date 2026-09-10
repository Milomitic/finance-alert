"""Tests for /api/calendar.

Covers auth, query-param defaulting, validation (from > to, range cap,
unknown kinds/importance), and end-to-end aggregation by stubbing the
fundamentals cache the same way `test_calendar_service.py` does.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Stock, StockScore, User
from app.services import stock_fundamentals_service
from app.services.stock_fundamentals_service import EarningsPoint, Fundamentals


@pytest.fixture(autouse=True)
def _clear_cache():
    stock_fundamentals_service._CACHE.clear()
    yield
    stock_fundamentals_service._CACHE.clear()


def _put(ticker: str, *, next_date: str | None = None, next_eps: float | None = None,
         next_rev: float | None = None,
         earnings: list[EarningsPoint] | None = None) -> None:
    stock_fundamentals_service._CACHE[ticker] = Fundamentals(
        ticker=ticker,
        next_earnings_date=next_date,
        next_eps_estimate=next_eps,
        next_revenue_estimate=next_rev,
        earnings=earnings or [],
        fetched_at=datetime.now(UTC).timestamp(),
    )


def _seed(db: Session, *, ticker: str, name: str = "Acme",
          sector: str | None = None, market_cap: int | None = None) -> Stock:
    s = Stock(ticker=ticker, exchange="NMS", name=name, sector=sector, market_cap=market_cap)
    db.add(s)
    db.flush()
    db.add(StockScore(
        stock_id=s.id, composite=70.0,
        quality=50.0, growth=50.0, value=50.0, momentum=50.0, sentiment=50.0,
        risk_tier="moderate",
        computed_at=datetime.now(UTC),
        breakdown=json.dumps({}),
    ))
    db.commit()
    return s


@pytest.fixture
def authed_client(db: Session) -> TestClient:
    user = User(username="tester", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def test_calendar_unauthenticated_401(db: Session):
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.get("/api/calendar")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_calendar_authenticated_200(authed_client: TestClient):
    resp = authed_client.get("/api/calendar")
    assert resp.status_code == 200
    data = resp.json()
    # Default window: today → today + 30 days. Both keys serialized via alias.
    assert "from" in data and "to" in data
    assert "events" in data and isinstance(data["events"], list)


# ---------------------------------------------------------------------------
# Validation (422)
# ---------------------------------------------------------------------------

def test_calendar_from_after_to_returns_422(authed_client: TestClient):
    resp = authed_client.get("/api/calendar?from=2026-06-01&to=2026-05-01")
    assert resp.status_code == 422
    assert "<=" in resp.json()["detail"] or "must be" in resp.json()["detail"].lower()


def test_calendar_unknown_kinds_returns_422(authed_client: TestClient):
    resp = authed_client.get("/api/calendar?kinds=foo")
    assert resp.status_code == 422


def test_calendar_unknown_importance_returns_422(authed_client: TestClient):
    resp = authed_client.get("/api/calendar?importance=critical")
    assert resp.status_code == 422


def test_calendar_range_too_wide_returns_422(authed_client: TestClient):
    resp = authed_client.get("/api/calendar?from=2024-01-01&to=2027-01-01")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Aggregation through the API
# ---------------------------------------------------------------------------

def test_calendar_returns_earnings_for_scored_stock(authed_client: TestClient, db: Session):
    _seed(db, ticker="AAPL", name="Apple Inc.", sector="Technology",
          market_cap=3_000_000_000_000)
    _put("AAPL", next_date="2026-05-08", next_eps=1.43, next_rev=90_000_000_000.0)

    resp = authed_client.get("/api/calendar?from=2026-05-01&to=2026-05-31")
    assert resp.status_code == 200
    data = resp.json()

    earnings = [e for e in data["events"] if e["kind"] == "earnings"]
    assert len(earnings) == 1
    e = earnings[0]
    assert e["ticker"] == "AAPL"
    assert e["date"] == "2026-05-08"
    assert e["eps_estimate"] == pytest.approx(1.43)
    assert e["sector"] == "Technology"


def test_calendar_returns_macros_in_window(authed_client: TestClient):
    resp = authed_client.get("/api/calendar?from=2026-05-01&to=2026-05-31")
    assert resp.status_code == 200
    macros = [e for e in resp.json()["events"] if e["kind"] == "macro"]
    assert macros, "expected curated macros in May 2026"
    # Spot-check FOMC presence on the canonical date
    assert any(m["date"] == "2026-05-14" and "FOMC" in m["label"] for m in macros)


def test_calendar_kinds_earnings_excludes_macros(authed_client: TestClient, db: Session):
    _seed(db, ticker="AAPL", name="Apple Inc.")
    _put("AAPL", next_date="2026-05-08", next_eps=1.0)

    resp = authed_client.get("/api/calendar?from=2026-05-01&to=2026-05-31&kinds=earnings")
    assert resp.status_code == 200
    kinds = {e["kind"] for e in resp.json()["events"]}
    assert kinds <= {"earnings"}


def test_calendar_kinds_macro_excludes_earnings(authed_client: TestClient, db: Session):
    _seed(db, ticker="AAPL", name="Apple Inc.")
    _put("AAPL", next_date="2026-05-08", next_eps=1.0)

    resp = authed_client.get("/api/calendar?from=2026-05-01&to=2026-05-31&kinds=macro")
    assert resp.status_code == 200
    kinds = {e["kind"] for e in resp.json()["events"]}
    assert kinds <= {"macro"}


def test_calendar_importance_high_only(authed_client: TestClient):
    resp = authed_client.get(
        "/api/calendar?from=2026-05-01&to=2026-08-31&importance=high"
    )
    assert resp.status_code == 200
    macros = [e for e in resp.json()["events"] if e["kind"] == "macro"]
    assert macros
    assert all(m["importance"] == "high" for m in macros)


def test_calendar_events_sorted_by_date_ascending(authed_client: TestClient, db: Session):
    _seed(db, ticker="AAA", name="A")
    _seed(db, ticker="BBB", name="B")
    _put("AAA", next_date="2026-05-20", next_eps=1.0)
    _put("BBB", next_date="2026-05-05", next_eps=1.0)

    resp = authed_client.get("/api/calendar?from=2026-05-01&to=2026-05-31")
    events = resp.json()["events"]
    dates = [e["date"] for e in events]
    assert dates == sorted(dates)


def test_calendar_response_shape_uses_from_to_aliases(authed_client: TestClient):
    """The response keys are `from` and `to` (Pydantic aliases) — not
    `date_from` / `date_to`."""
    resp = authed_client.get("/api/calendar?from=2026-05-01&to=2026-05-31")
    assert resp.status_code == 200
    data = resp.json()
    assert data["from"] == "2026-05-01"
    assert data["to"] == "2026-05-31"
    assert "date_from" not in data
    assert "date_to" not in data


# ---------------------------------------------------------------------------
# /api/macro/{series_id} — detail endpoint
# ---------------------------------------------------------------------------

def test_macro_detail_unauthenticated_401(db: Session):
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.get("/api/macro/1")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_macro_detail_404_for_missing_series(authed_client: TestClient):
    resp = authed_client.get("/api/macro/999999")
    assert resp.status_code == 404


def test_macro_detail_full_payload(authed_client: TestClient, db: Session):
    """Seeds a MacroSeries + 3 observations + 1 future release date and
    verifies the response carries: metadata, derived currency, the latest
    release with previous_value pointing at the second-most-recent
    observation, full history (newest first), and the upcoming date."""
    from datetime import date as _d

    from app.models import MacroObservation, MacroReleaseDate, MacroSeries

    series = MacroSeries(
        fred_series_id="TESTSER",
        fred_release_id=999,
        label="Test Indicator",
        region="US",
        importance="high",
        unit="pct",
        description="A test series for the detail endpoint.",
        source="Test Authority",
    )
    db.add(series)
    db.flush()
    db.add_all([
        MacroObservation(series_id=series.id, date=_d(2026, 1, 15), value=1.0),
        MacroObservation(series_id=series.id, date=_d(2026, 2, 15), value=1.5),
        MacroObservation(series_id=series.id, date=_d(2026, 3, 15), value=2.1),
    ])
    db.add(MacroReleaseDate(series_id=series.id, date=_d(2030, 4, 15)))
    db.commit()

    resp = authed_client.get(f"/api/macro/{series.id}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["series_id"] == series.id
    assert data["label"] == "Test Indicator"
    assert data["currency"] == "USD"          # derived from region="US"
    assert data["source"] == "Test Authority"
    assert data["importance"] == "high"

    # latest = newest observation; previous_value = the one before. An
    # observation date is a reference period, never a fabricated publication.
    assert data["latest"]["actual_value"] == 2.1
    assert data["latest"]["previous_value"] == 1.5
    assert data["latest"]["period_label"] == "Mar"
    assert data["latest"]["expected_value"] is None  # no historical consensus
    assert data["latest"]["observation_period"] == "2026-03-15"
    assert data["latest"]["publication_date"] is None
    assert "release_date" not in data["latest"]

    # history newest → oldest, full set
    assert [r["actual_value"] for r in data["history"]] == [2.1, 1.5, 1.0]
    assert [r["observation_period"] for r in data["history"]] == [
        "2026-03-15",
        "2026-02-15",
        "2026-01-15",
    ]
    # First row's previous = second row's actual
    assert data["history"][0]["previous_value"] == 1.5
    # Oldest row has no previous
    assert data["history"][-1]["previous_value"] is None

    # Future date surfaced under upcoming
    assert "2030-04-15" in data["upcoming"]


# ---------------------------------------------------------------------------
# /api/scan-runs/recent — scan log endpoint (added 2026-05-14)
# ---------------------------------------------------------------------------

def test_scan_log_unauthenticated_401(db: Session):
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.get("/api/scan-runs/recent")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_scan_log_phase_history_recorded_on_phase_set(authed_client: TestClient, db: Session):
    """Set ScanRun.phase a few times via the SQLAlchemy event listener and
    verify phase_history closes prior entries + appends new ones."""
    import json as _json
    from datetime import UTC, datetime

    from app.models import ScanRun

    run = ScanRun(
        kind="alerts_scan",
        trigger="manual",
        status="running",
        started_at=datetime.now(UTC),
    )
    db.add(run)
    db.commit()
    # Initial phase set
    run.phase = "fetching:loading_catalog"
    db.commit()
    run.phase = "fetching:incremental"
    db.commit()
    run.phase = None  # finalize
    run.status = "success"
    run.completed_at = datetime.now(UTC)
    db.commit()

    history = _json.loads(run.phase_history)
    assert len(history) == 2  # None at end doesn't get appended
    assert history[0]["phase"] == "fetching:loading_catalog"
    assert history[0]["ended_at"] is not None  # closed when 2nd phase started
    assert history[1]["phase"] == "fetching:incremental"
    assert history[1]["ended_at"] is not None  # closed when None was set


def test_scan_log_endpoint_returns_runs_with_durations(authed_client: TestClient, db: Session):
    from datetime import UTC, datetime, timedelta

    from app.models import ScanRun

    t0 = datetime.now(UTC)
    run = ScanRun(
        kind="alerts_scan",
        trigger="manual",
        status="success",
        started_at=t0,
        completed_at=t0 + timedelta(seconds=42),
        progress_done=100,
        progress_total=100,
        stocks_scanned=100,
        alerts_fired=7,
    )
    db.add(run)
    db.commit()
    run.phase = "fetching:incremental"
    db.commit()
    run.phase = "evaluating:scoring"
    db.commit()
    run.phase = None
    db.commit()

    resp = authed_client.get("/api/scan-runs/recent?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert "runs" in data
    assert any(r["id"] == run.id for r in data["runs"])
    target = next(r for r in data["runs"] if r["id"] == run.id)
    assert target["status"] == "success"
    assert target["alerts_fired"] == 7
    assert target["total_duration_sec"] == 42.0
    assert len(target["phases"]) == 2
    assert target["phases"][0]["phase"] == "fetching:incremental"
    assert target["phases"][0]["duration_sec"] is not None
    assert target["phases"][0]["duration_sec"] >= 0


def test_scan_log_filter_by_kind(authed_client: TestClient, db: Session):
    from datetime import UTC, datetime

    from app.models import ScanRun

    db.add_all([
        ScanRun(kind="alerts_scan",     trigger="manual", status="success", started_at=datetime.now(UTC)),
        ScanRun(kind="score_recompute", trigger="manual", status="success", started_at=datetime.now(UTC)),
    ])
    db.commit()

    resp = authed_client.get("/api/scan-runs/recent?kind=score_recompute")
    assert resp.status_code == 200
    kinds = {r["kind"] for r in resp.json()["runs"]}
    assert kinds == {"score_recompute"}


def test_macro_detail_carries_the_scale_and_keeps_the_three_dates_apart(
    authed_client: TestClient, db: Session
):
    """La scala deve ARRIVARE al frontend, o la correzione e decorativa.

    Il difetto: la scheda dell'indicatore rende `Total Non-Farm Payrolls
    (thousands)` e il formatter stampava `159.1K` sul valore memorizzato
    159100, cioe sbagliava di mille volte. **L'unita era nel payload e il
    formatter la ignorava** — ma poteva ignorarla solo perche l'API non la
    esponeva affatto: `unit` diceva "level" per una serie in migliaia e per
    una in miliardi allo stesso modo.

    E le tre date restano tre: il periodo osservato, la pubblicazione e il
    momento in cui l'abbiamo scaricata. Prima erano un campo solo, costruito
    dal periodo, quindi il dato di agosto risultava pubblicato il 1 agosto:
    una lettura datata prima che il periodo che misura fosse finito.
    """
    from datetime import date as _d

    from app.models.macro import MacroObservation, MacroSeries

    series = MacroSeries(
        fred_series_id="PAYEMSTEST",
        fred_release_id=50,
        label="Occupati non agricoli",
        region="US",
        importance="high",
        unit="level",
        source_scale="thousands",
        description="Total Non-Farm Payrolls (thousands)",
        source="BLS",
        last_refreshed_at=datetime(2026, 9, 10, 6, 0, tzinfo=UTC),
    )
    db.add(series)
    db.flush()
    db.add_all([
        MacroObservation(series_id=series.id, date=_d(2026, 7, 1), value=158_900.0),
        MacroObservation(series_id=series.id, date=_d(2026, 8, 1), value=159_100.0),
    ])
    db.commit()

    data = authed_client.get(f"/api/macro/{series.id}").json()

    # La scala viaggia, distinta dal tipo di valore.
    assert data["source_scale"] == "thousands"
    assert data["value_kind"] == "level"

    # I nomi vecchi non ci sono piu. Serve dirlo: un frontend che leggesse
    # ancora `unit` otterrebbe `undefined` e renderebbe di nuovo il numero
    # grezzo, cioe il difetto tornerebbe in silenzio.
    assert "unit" not in data
    assert "last_refreshed_at" not in data

    # Tre date, tre campi.
    latest = data["latest"]
    assert latest["observation_period"] == "2026-08-01"
    # ⚠️ FRED non consegna la data di pubblicazione delle osservazioni. Non si
    # ricostruisce dal periodo: era esattamente quello il bug.
    assert latest["publication_date"] is None
    assert latest["acquired_at"] is not None
    assert data["data_acquired_at"] is not None


def test_a_series_without_a_declared_scale_says_so_instead_of_guessing(
    authed_client: TestClient, db: Session
):
    """Il controllo negativo.

    Senza di esso un'API che restituisse sempre "ones" supererebbe il test
    sopra, e il frontend compatterebbe di nuovo qualunque cosa. Una scala
    ignota deve arrivare come `null`, cosi il formatter puo rifiutarsi di
    applicare un suffisso invece di inventarne uno.
    """
    from datetime import date as _d

    from app.models.macro import MacroObservation, MacroSeries

    series = MacroSeries(
        fred_series_id="SENZASCALA",
        fred_release_id=1,
        label="Serie senza scala",
        region="US",
        importance="low",
        unit="level",
        source="Test",
    )
    db.add(series)
    db.flush()
    db.add(MacroObservation(series_id=series.id, date=_d(2026, 8, 1), value=42.0))
    db.commit()

    data = authed_client.get(f"/api/macro/{series.id}").json()

    assert data["source_scale"] is None
    assert data["value_kind"] == "level"


def test_the_curated_map_declares_the_scale_where_fred_has_one():
    """La scala e DICHIARATA nella mappa curata, non dedotta a valle.

    Solo quella mappa sa che PAYEMS spedisce migliaia e GDPC1 miliardi. Un
    formatter che lo indovina e il bug ×1000; una serie di livello a cui
    nessuno ha assegnato la scala deve restare senza, non prendere un
    valore plausibile.
    """
    from app.scripts.refresh_fred import CURATED_SERIES

    by_id = {c.fred_series_id: c for c in CURATED_SERIES}

    assert by_id["PAYEMS"].source_scale == "thousands"
    assert by_id["GDPC1"].source_scale == "billions"
    assert by_id["RSAFS"].source_scale == "millions"
    # Una percentuale non ha scala da dichiarare: il campo resta vuoto invece
    # di prendere "ones" per riempirlo.
    assert by_id["UNRATE"].source_scale is None
