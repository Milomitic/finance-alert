"""Tests for /api/stocks/{ticker}/score and /api/scores/top.

Auth: 401 without cookie, 200 with override.
404: unknown ticker, OR known ticker with no score yet (with friendly msg).
Top picks: risk filter narrows to that tier; category sort orders by sub-score.
"""
import json
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import OhlcvDaily, ScanRun, Stock, StockScore, User


def _make_score(
    *, stock_id: int, composite: float, risk: str = "moderate",
    quality: float = 50.0, growth: float = 50.0, value: float = 50.0,
    momentum: float = 50.0, sentiment: float = 50.0,
    breakdown: dict | None = None,
) -> StockScore:
    return StockScore(
        stock_id=stock_id,
        composite=composite,
        quality=quality, growth=growth, value=value,
        momentum=momentum, sentiment=sentiment,
        risk_tier=risk,
        computed_at=datetime.now(UTC),
        # Real scores always carry breakdown._meta_global (QW5 coverage);
        # default it to fully-covered so seeded picks pass the /scores/top
        # confidence gate. Tests can still override _meta_global to
        # exercise the gate explicitly.
        breakdown=json.dumps({
            **(breakdown or {"quality": {"roe": {"raw": 0.2, "points": 30, "max": 30}}}),
            "_meta_global": (breakdown or {}).get(
                "_meta_global", {"coverage": 1.0}
            ),
        }),
    )


@pytest.fixture
def seeded_client(db: Session) -> TestClient:
    """Three stocks across the three risk tiers + scores + a couple OHLCV bars
    so the change_pct enrichment path runs in the top-picks endpoint."""
    user = User(username="tester", password_hash="x")
    db.add(user)
    db.flush()
    stocks = [
        Stock(ticker="AAA", exchange="NMS", name="AAA Inc", sector="Utilities", market_cap=300_000_000_000),
        Stock(ticker="BBB", exchange="NMS", name="BBB Corp", sector="Healthcare", market_cap=50_000_000_000),
        Stock(ticker="CCC", exchange="NMS", name="CCC Ltd", sector="Technology", market_cap=2_000_000_000),
    ]
    db.add_all(stocks)
    db.flush()
    db.add_all([
        _make_score(stock_id=stocks[0].id, composite=85.0, risk="conservative", quality=90.0),
        _make_score(stock_id=stocks[1].id, composite=70.0, risk="moderate", quality=60.0),
        _make_score(stock_id=stocks[2].id, composite=95.0, risk="aggressive", quality=30.0),
    ])
    today = date(2026, 5, 1)
    for s in stocks:
        db.add(OhlcvDaily(stock_id=s.id, date=today - timedelta(days=1),
                          open=100, high=101, low=99, close=100, volume=1_000_000))
        db.add(OhlcvDaily(stock_id=s.id, date=today,
                          open=101, high=102, low=100, close=102, volume=1_000_000))
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def empty_client(db: Session) -> TestClient:
    """Client where stocks exist but no scores have been computed yet."""
    user = User(username="tester", password_hash="x")
    db.add(user)
    db.flush()
    db.add(Stock(ticker="ZZZ", exchange="NMS", name="Z", sector="Utilities"))
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# /api/stocks/{ticker}/score
# ---------------------------------------------------------------------------

def test_get_stock_score_returns_full_payload(seeded_client: TestClient):
    resp = seeded_client.get("/api/stocks/AAA/score")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "AAA"
    assert data["composite"] == 85.0
    assert data["risk_tier"] == "conservative"
    assert data["sub_scores"]["quality"] == 90.0
    assert "breakdown" in data and isinstance(data["breakdown"], dict)


def test_get_stock_score_computed_at_has_utc_timezone(seeded_client: TestClient):
    """Regression: SQLite returns naive datetimes for DateTime(timezone=True)
    columns. Without the field_serializer the JSON is `2026-05-11T14:34:01.836551`
    (no TZ marker), and the frontend's `new Date(iso)` reads it as LOCAL time
    — so for a user in UTC+2 a fresh "now" timestamp shifts ~2h into the past
    and the score card shows "Calcolato 2h fa" right after a recompute.

    Backend convention is "all stored datetimes are UTC", so the serializer
    attaches +00:00 explicitly."""
    resp = seeded_client.get("/api/stocks/AAA/score")
    assert resp.status_code == 200
    computed_at = resp.json()["computed_at"]
    # Either Z or +00:00 / +HH:MM offset is acceptable
    assert (
        computed_at.endswith("Z")
        or computed_at.endswith("+00:00")
        or computed_at[-6] in ("+", "-")
    ), (
        f"computed_at must carry a TZ marker so JS Date() parses it as UTC; "
        f"got {computed_at!r}"
    )


def test_get_stock_score_unknown_ticker_404(seeded_client: TestClient):
    resp = seeded_client.get("/api/stocks/NOPE/score")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_get_stock_score_no_score_yet_404_with_friendly_message(empty_client: TestClient):
    resp = empty_client.get("/api/stocks/ZZZ/score")
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert "not yet computed" in detail.lower()
    assert "scan" in detail.lower()


def test_get_stock_score_unauthenticated_returns_401(db: Session):
    """No dependency override → real auth check kicks in."""
    db.add(Stock(ticker="X", exchange="NMS", name="X"))
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.get("/api/stocks/X/score")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /api/stocks/{ticker}/score/recompute
# ---------------------------------------------------------------------------

def test_recompute_returns_fresh_score_and_persists(
    seeded_client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
):
    """Regression for the "two pillars wrong" + "refresh button doesn't
    work" pair (see CLAUDE.md / scores PR). Original symptom on MU:
    the persisted score had `profitability=None` + `value=None` because
    fundamentals were partial (yfinance info call failed) at scan time.
    The GET endpoint reads the persisted row, so refreshing the React
    Query cache returned the same broken value; only a real recompute
    can update the pillars."""
    # Stub the upstream recompute path. Returning a StockScore with all
    # six pillars populated mimics a successful recompute after the
    # fundamentals cache has been repopulated by force_refresh.
    fresh = _make_score(
        stock_id=1,  # AAA is seeded with id auto-assigned, fixed up below
        composite=92.5,
        risk="moderate",
        quality=85.0,
        growth=88.0,
        value=75.0,  # was None pre-recompute
        momentum=95.0,
        sentiment=80.0,
    )
    fresh.profitability = 90.0  # was None pre-recompute
    fresh.sustainability = 85.0

    aaa = db.query(Stock).filter_by(ticker="AAA").one()
    fresh.stock_id = aaa.id

    def stub_compute_score(_db, stock, *, sector_stats=None):
        return fresh

    def stub_force_refresh(*_args, **_kw):
        # No-op — emulates a fundamentals cache refill so compute_score
        # has up-to-date data. The endpoint MUST tolerate exceptions
        # here (it's wrapped in try/except), so this stub just succeeds.
        return None

    monkeypatch.setattr(
        "app.api.scores.score_service.compute_score", stub_compute_score
    )
    monkeypatch.setattr(
        "app.api.scores.stock_fundamentals_service.get_fundamentals",
        stub_force_refresh,
    )

    resp = seeded_client.post("/api/stocks/AAA/score/recompute")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ticker"] == "AAA"
    assert data["composite"] == 92.5
    # Both regression-target pillars must now be populated, not None.
    assert data["sub_scores"]["profitability"] == 90.0
    assert data["sub_scores"]["value"] == 75.0
    # Persistence: the row in `stock_scores` is updated (UPSERT semantics).
    persisted = db.query(StockScore).filter_by(stock_id=aaa.id).one()
    assert persisted.composite == 92.5
    assert persisted.profitability == 90.0
    assert persisted.value == 75.0


def test_recompute_forces_fundamentals_refresh(
    seeded_client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
):
    """The endpoint MUST call get_fundamentals with force_refresh=True so a
    stale partial L1 entry doesn't slip through and yield the same broken
    score the user is trying to fix."""
    refresh_calls: list[tuple[str, bool]] = []

    def stub_force_refresh(ticker: str, *, force_refresh: bool = False):
        refresh_calls.append((ticker, force_refresh))
        return None

    aaa = db.query(Stock).filter_by(ticker="AAA").one()
    fresh = _make_score(stock_id=aaa.id, composite=80.0)
    fresh.profitability = 70.0
    fresh.sustainability = 70.0

    monkeypatch.setattr(
        "app.api.scores.stock_fundamentals_service.get_fundamentals",
        stub_force_refresh,
    )
    monkeypatch.setattr(
        "app.api.scores.score_service.compute_score",
        lambda _db, _s, *, sector_stats=None: fresh,
    )

    resp = seeded_client.post("/api/stocks/AAA/score/recompute")
    assert resp.status_code == 200
    assert refresh_calls == [("AAA", True)], (
        f"Expected force_refresh=True for AAA; got {refresh_calls}"
    )


def test_recompute_unknown_ticker_returns_404(seeded_client: TestClient):
    resp = seeded_client.post("/api/stocks/NOPE/score/recompute")
    assert resp.status_code == 404


def test_recompute_unauthenticated_returns_401(db: Session):
    db.add(Stock(ticker="X", exchange="NMS", name="X"))
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.post("/api/stocks/X/score/recompute")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /api/stocks/{ticker}/technical/recompute
# ---------------------------------------------------------------------------


def _technical_client(db: Session, *, bars: int) -> tuple[TestClient, int]:
    """Seed one stock with `bars` OHLCV rows and return an authed client +
    the stock id. A gently rising series gives partial_for valid dimensions."""
    user = User(username="tester", password_hash="x")
    db.add(user)
    db.flush()
    stock = Stock(ticker="TEC", exchange="NMS", name="Tec Inc")
    db.add(stock)
    db.flush()
    base = date(2026, 1, 1)
    price = 100.0
    for i in range(bars):
        price += 0.5
        db.add(OhlcvDaily(
            stock_id=stock.id, date=base + timedelta(days=i),
            open=price, high=price + 1, low=price - 1, close=price,
            volume=1_000_000,
        ))
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app), stock.id


def test_recompute_technical_returns_fresh_and_persists(db: Session):
    from app.models import TechnicalScore
    client, stock_id = _technical_client(db, bars=60)
    try:
        resp = client.post("/api/stocks/TEC/technical/recompute")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ticker"] == "TEC"
        assert isinstance(body["composite"], (int, float))
        assert body["posture"] in ("Forte", "Neutro", "Debole")
        # Persisted exactly one row.
        rows = db.query(TechnicalScore).filter_by(stock_id=stock_id).all()
        assert len(rows) == 1
        assert rows[0].composite == body["composite"]
    finally:
        app.dependency_overrides.clear()


def test_recompute_technical_insufficient_history_422(db: Session):
    client, _ = _technical_client(db, bars=5)
    try:
        resp = client.post("/api/stocks/TEC/technical/recompute")
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_recompute_technical_unknown_ticker_404(db: Session):
    client, _ = _technical_client(db, bars=60)
    try:
        resp = client.post("/api/stocks/NOPE/technical/recompute")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_recompute_tolerates_fundamentals_refresh_failure(
    seeded_client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
):
    """Network blip on the fundamentals fetch must NOT 500 the endpoint —
    compute_score still runs with whatever the cache holds. This is the
    'circuit breaker open' scenario in production."""
    def boom(*_a, **_kw):
        raise RuntimeError("yfinance circuit breaker open")

    aaa = db.query(Stock).filter_by(ticker="AAA").one()
    fresh = _make_score(stock_id=aaa.id, composite=70.0)
    fresh.profitability = 60.0
    fresh.sustainability = 60.0

    monkeypatch.setattr(
        "app.api.scores.stock_fundamentals_service.get_fundamentals",
        boom,
    )
    monkeypatch.setattr(
        "app.api.scores.score_service.compute_score",
        lambda _db, _s, *, sector_stats=None: fresh,
    )

    resp = seeded_client.post("/api/stocks/AAA/score/recompute")
    assert resp.status_code == 200
    assert resp.json()["composite"] == 70.0


# ---------------------------------------------------------------------------
# POST /api/scores/recompute-all  +  GET /api/scores/recompute-status
# (bulk recompute flow — mirror of /api/alerts/scan UX)
# ---------------------------------------------------------------------------

from datetime import datetime as _dt

from app.models.scan_run import KIND_ALERTS_SCAN, KIND_SCORE_RECOMPUTE


def test_recompute_all_returns_202_when_idle(
    seeded_client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Endpoint MUST return 202 immediately (BackgroundTasks dispatch)."""
    # Stub the actual runner so the test doesn't hit yfinance and we keep
    # the TestClient call instant. The endpoint contract is "accepts +
    # schedules"; the runner's correctness is exercised in test_score_service.
    monkeypatch.setattr(
        "app.api.scores._run_recompute_in_background",
        lambda force=True: None,
    )
    resp = seeded_client.post("/api/scores/recompute-all")
    assert resp.status_code == 202, resp.text
    assert resp.json() == {"accepted": True}


def test_recompute_all_rejects_when_already_running(
    seeded_client: TestClient, db: Session
) -> None:
    """409 if a score_recompute ScanRun is already in 'running' state.

    Guard against piling up concurrent runs: two parallel runners would
    scribble over each other's heartbeats and corrupt the UI's progress
    bar."""
    db.add(
        ScanRun(
            kind=KIND_SCORE_RECOMPUTE,
            trigger="manual",
            status="running",
            phase="scoring",
            started_at=_dt.now(UTC),
            last_progress_at=_dt.now(UTC),
            progress_done=42,
            progress_total=100,
        )
    )
    db.commit()
    resp = seeded_client.post("/api/scores/recompute-all")
    assert resp.status_code == 409
    assert "in corso" in resp.json()["detail"]


def test_recompute_status_returns_empty_when_no_run(
    seeded_client: TestClient,
) -> None:
    resp = seeded_client.get("/api/scores/recompute-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_running"] is False
    assert data["last_run_id"] is None


def test_recompute_status_returns_latest_score_recompute_row(
    seeded_client: TestClient, db: Session
) -> None:
    """The endpoint MUST filter by kind so an alert-scan row doesn't
    leak into the score-recompute toast (regression for the
    pre-discriminator schema where the two flows would have collided)."""
    # Seed: one alert-scan run AFTER a score-recompute run. Without the
    # kind filter, the alert-scan would win the ORDER BY started_at DESC.
    older = ScanRun(
        kind=KIND_SCORE_RECOMPUTE,
        trigger="manual",
        status="success",
        started_at=_dt(2026, 5, 1, tzinfo=UTC),
        completed_at=_dt(2026, 5, 1, 0, 1, tzinfo=UTC),
        progress_done=900,
        progress_total=900,
        stocks_scanned=895,
        stocks_skipped=5,
    )
    newer = ScanRun(
        kind=KIND_ALERTS_SCAN,
        trigger="manual",
        status="success",
        started_at=_dt(2026, 5, 2, tzinfo=UTC),
        completed_at=_dt(2026, 5, 2, 0, 1, tzinfo=UTC),
        progress_done=900,
        progress_total=900,
        alerts_fired=7,
    )
    db.add_all([older, newer])
    db.commit()
    resp = seeded_client.get("/api/scores/recompute-status")
    assert resp.status_code == 200
    data = resp.json()
    # Must surface the older score_recompute row, NOT the newer alert-scan.
    assert data["last_run_id"] == older.id
    assert data["stocks_scanned"] == 895
    assert data["stocks_skipped"] == 5
    assert data["alerts_fired"] is None


def test_scan_status_filters_out_score_recompute_rows(
    seeded_client: TestClient, db: Session
) -> None:
    """Symmetric guard: a score_recompute row MUST NOT be returned by
    the alert-scan endpoint, otherwise the scan toast would render
    "Ricalcolo score" content."""
    db.add(
        ScanRun(
            kind=KIND_SCORE_RECOMPUTE,
            trigger="manual",
            status="running",
            phase="scoring",
            started_at=_dt.now(UTC),
            last_progress_at=_dt.now(UTC),
            progress_done=10,
            progress_total=100,
        )
    )
    db.commit()
    resp = seeded_client.get("/api/alerts/scan-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_running"] is False
    assert data["last_run_id"] is None


def test_recompute_stop_is_idempotent_when_nothing_running(
    seeded_client: TestClient,
) -> None:
    resp = seeded_client.post("/api/scores/recompute-stop")
    assert resp.status_code == 200
    data = resp.json()
    assert data["was_running"] is False
    assert "Nessun ricalcolo" in data["message"]


def test_recompute_stop_requests_cancel_for_running_row(
    seeded_client: TestClient, db: Session
) -> None:
    from app.services import scan_cancel

    row = ScanRun(
        kind=KIND_SCORE_RECOMPUTE,
        trigger="manual",
        status="running",
        phase="scoring",
        started_at=_dt.now(UTC),
        last_progress_at=_dt.now(UTC),
        progress_done=10,
        progress_total=100,
    )
    db.add(row)
    db.commit()
    try:
        resp = seeded_client.post("/api/scores/recompute-stop")
        assert resp.status_code == 200
        data = resp.json()
        assert data["was_running"] is True
        assert data["was_stale"] is False
        assert data["stopped_run_id"] == row.id
        # The cancel flag MUST be set so the runner bails out at the next
        # iteration boundary (raises RecomputeCancelled inside the loop).
        assert scan_cancel.is_cancel_requested(row.id)
    finally:
        scan_cancel.clear(row.id)


# ---------------------------------------------------------------------------
# /api/scores/top
# ---------------------------------------------------------------------------

def test_top_picks_default_composite_descending(seeded_client: TestClient):
    resp = seeded_client.get("/api/scores/top")
    assert resp.status_code == 200
    data = resp.json()
    assert data["category"] == "composite"
    assert data["risk"] is None
    tickers = [item["ticker"] for item in data["items"]]
    assert tickers == ["CCC", "AAA", "BBB"]
    # change_pct populated from the seeded OHLCV bars (102 vs 100 → +2%).
    assert data["items"][0]["change_pct"] == pytest.approx(2.0, abs=0.01)


def test_top_picks_filtered_by_risk(seeded_client: TestClient):
    resp = seeded_client.get("/api/scores/top?risk=conservative")
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk"] == "conservative"
    assert len(data["items"]) == 1
    assert data["items"][0]["ticker"] == "AAA"
    assert data["items"][0]["risk_tier"] == "conservative"


def test_top_picks_by_category(seeded_client: TestClient):
    """category=quality sorts by the quality sub-score, not composite."""
    resp = seeded_client.get("/api/scores/top?category=quality")
    assert resp.status_code == 200
    data = resp.json()
    assert data["category"] == "quality"
    tickers = [item["ticker"] for item in data["items"]]
    # AAA: quality=90, BBB: 60, CCC: 30 → AAA first.
    assert tickers == ["AAA", "BBB", "CCC"]


def test_top_picks_excludes_low_confidence(db: Session):
    """A high composite built on a thin factor base (QW5 coverage < 0.70)
    must NOT surface as a top pick; an adequately-covered lower score
    still does."""
    user = User(username="t2", password_hash="x")
    db.add(user)
    db.flush()
    hi = Stock(ticker="HIQ", exchange="NMS", name="Hi",
               sector="Utilities", market_cap=int(1e11))
    lo = Stock(ticker="LOQ", exchange="NMS", name="Lo",
               sector="Utilities", market_cap=int(1e11))
    db.add_all([hi, lo])
    db.flush()
    db.add(_make_score(stock_id=hi.id, composite=80.0,
                       breakdown={"_meta_global": {"coverage": 0.95}}))
    db.add(_make_score(stock_id=lo.id, composite=99.0,
                       breakdown={"_meta_global": {"coverage": 0.40}}))
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        data = TestClient(app).get("/api/scores/top").json()
        tickers = [i["ticker"] for i in data["items"]]
        assert "HIQ" in tickers          # 0.95 ≥ 0.70 → shown
        assert "LOQ" not in tickers      # 0.40 < 0.70 → excluded despite top composite
    finally:
        app.dependency_overrides.clear()


def test_top_picks_invalid_risk_422(seeded_client: TestClient):
    resp = seeded_client.get("/api/scores/top?risk=hacker")
    assert resp.status_code == 422


def test_top_picks_invalid_category_422(seeded_client: TestClient):
    resp = seeded_client.get("/api/scores/top?category=badness")
    assert resp.status_code == 422


def test_top_picks_limit_respected(seeded_client: TestClient):
    resp = seeded_client.get("/api/scores/top?limit=2")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 2


def test_top_picks_limit_above_max_returns_422(seeded_client: TestClient):
    resp = seeded_client.get("/api/scores/top?limit=999")
    assert resp.status_code == 422


def test_top_picks_unauthenticated_401(db: Session):
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.get("/api/scores/top")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /api/stocks/{ticker}/score-history
# ---------------------------------------------------------------------------

from app.models import ScoreHistory


def _seed_history(
    db: Session, stock_id: int, lens: str, days_ago_to_composite: dict[int, float]
) -> None:
    """Insert one ScoreHistory row per (days_ago → composite) entry, anchored
    to today so the endpoint's rolling `days` window math is deterministic."""
    today = date.today()
    for days_ago, composite in days_ago_to_composite.items():
        db.add(ScoreHistory(
            stock_id=stock_id,
            lens=lens,
            captured_on=today - timedelta(days=days_ago),
            composite=composite,
            pillars="{}",
        ))
    db.commit()


def test_score_history_returns_points_ascending(seeded_client: TestClient, db: Session):
    aaa = db.query(Stock).filter_by(ticker="AAA").one()
    # Deliberately seeded out of chronological order — the endpoint must sort.
    _seed_history(db, aaa.id, "qualita", {1: 81.0, 5: 79.0, 3: 80.0})
    resp = seeded_client.get("/api/stocks/AAA/score-history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "AAA"
    assert data["lens"] == "qualita"
    today = date.today()
    assert data["points"] == [
        {"date": (today - timedelta(days=5)).isoformat(), "composite": 79.0},
        {"date": (today - timedelta(days=3)).isoformat(), "composite": 80.0},
        {"date": (today - timedelta(days=1)).isoformat(), "composite": 81.0},
    ]


def test_score_history_filters_by_lens(seeded_client: TestClient, db: Session):
    aaa = db.query(Stock).filter_by(ticker="AAA").one()
    _seed_history(db, aaa.id, "qualita", {2: 70.0})
    _seed_history(db, aaa.id, "tecnico", {2: 40.0, 1: 42.0})
    # Default lens is qualita — the tecnico rows must not leak in.
    resp = seeded_client.get("/api/stocks/AAA/score-history")
    assert resp.status_code == 200
    assert [p["composite"] for p in resp.json()["points"]] == [70.0]
    # Explicit tecnico returns only that lens.
    resp = seeded_client.get("/api/stocks/AAA/score-history?lens=tecnico")
    assert resp.status_code == 200
    data = resp.json()
    assert data["lens"] == "tecnico"
    assert [p["composite"] for p in data["points"]] == [40.0, 42.0]


def test_score_history_invalid_lens_422(seeded_client: TestClient):
    resp = seeded_client.get("/api/stocks/AAA/score-history?lens=bogus")
    assert resp.status_code == 422


def test_score_history_days_window(seeded_client: TestClient, db: Session):
    aaa = db.query(Stock).filter_by(ticker="AAA").one()
    _seed_history(db, aaa.id, "qualita", {200: 60.0, 10: 75.0})
    # Default window (180d) drops the 200-days-ago point.
    resp = seeded_client.get("/api/stocks/AAA/score-history")
    assert [p["composite"] for p in resp.json()["points"]] == [75.0]
    # Widest window (365d) includes both.
    resp = seeded_client.get("/api/stocks/AAA/score-history?days=365")
    assert [p["composite"] for p in resp.json()["points"]] == [60.0, 75.0]
    # Narrowest window (7d) excludes everything seeded here.
    resp = seeded_client.get("/api/stocks/AAA/score-history?days=7")
    assert resp.json()["points"] == []


def test_score_history_days_bounds_422(seeded_client: TestClient):
    assert seeded_client.get("/api/stocks/AAA/score-history?days=6").status_code == 422
    assert seeded_client.get("/api/stocks/AAA/score-history?days=366").status_code == 422


def test_score_history_lowercase_ticker_resolves(seeded_client: TestClient, db: Session):
    """The path param is upper-cased before the Stock lookup."""
    aaa = db.query(Stock).filter_by(ticker="AAA").one()
    _seed_history(db, aaa.id, "qualita", {1: 81.0})
    resp = seeded_client.get("/api/stocks/aaa/score-history")
    assert resp.status_code == 200
    assert resp.json()["ticker"] == "AAA"


def test_score_history_unknown_ticker_404(seeded_client: TestClient):
    resp = seeded_client.get("/api/stocks/NOPE/score-history")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_score_history_no_rows_returns_empty_points(seeded_client: TestClient):
    """Known ticker, zero captured snapshots → 200 with points: [] (NOT 404):
    the table only accrues forward, so 'no history yet' is a normal state."""
    resp = seeded_client.get("/api/stocks/AAA/score-history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "AAA"
    assert data["points"] == []


def test_score_history_unauthenticated_401(db: Session):
    db.add(Stock(ticker="X", exchange="NMS", name="X"))
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.get("/api/stocks/X/score-history")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()
