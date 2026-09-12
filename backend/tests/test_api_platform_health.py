"""Integration tests for /api/platform/health and /api/platform/logs.

Fixture pattern: each test defines or uses a local `client` fixture that:
  - creates an in-memory DB session (via the `db` fixture from conftest.py)
  - overrides both get_db and get_current_user on the FastAPI app
  - yields a TestClient
  - clears the overrides afterwards

For "requires_auth" tests we construct an unauthenticated TestClient inline
(no dependency overrides) so the cookie check fires and returns 401.
"""
import pytest
from fastapi.testclient import TestClient
from loguru import logger
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.logging import configure_logging
from app.main import app
from app.models import User


@pytest.fixture(autouse=True)
def _clean_source_metrics():
    """data_source_metrics is process-global: earlier test modules may have
    left failing counters behind, which would leak into the server-side
    rollup (`overall`) these tests assert on."""
    from app.services import data_source_metrics

    data_source_metrics.reset()
    yield
    data_source_metrics.reset()


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# /api/platform/health
# ---------------------------------------------------------------------------

def test_health_endpoint_requires_auth():
    """No session cookie → 401. Use TestClient without the lifespan (no `with`
    context manager) to avoid the startup hook hitting the production DB."""
    c = TestClient(app, raise_server_exceptions=True)
    r = c.get("/api/platform/health")
    assert r.status_code in (401, 403)


def test_health_endpoint_returns_expected_keys(client: TestClient):
    r = client.get("/api/platform/health")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {
        "data_sources", "yfinance_breaker", "scheduler", "scans", "cache",
        "overall", "reasons", "suggestions",
        "data_health",
        "deploy",
    }
    assert isinstance(body["data_sources"], list)
    assert isinstance(body["scheduler"], list)
    assert isinstance(body["scans"], list)
    assert "fundamentals" in body["cache"]
    assert "news" in body["cache"]
    assert "db" in body["cache"]
    # OHLCV freshness row (SAL-2, "Dati" row on the CacheCard).
    assert "ohlcv" in body["cache"]
    assert set(body["cache"]["ohlcv"].keys()) == {"max_date", "stocks_at_max"}
    # Server-side rollup (SAL-1): one truth for banner/SSE/Telegram.
    assert body["overall"] in ("operational", "degraded", "outage")
    assert isinstance(body["reasons"], list)
    # Gap-analysis hints (SAL-2: folded in from the deleted
    # /api/health/data-sources endpoint). Idle catalog → no suggestions.
    assert isinstance(body["suggestions"], list)


def test_health_suggestions_surface_gap_analysis(client: TestClient):
    """When an op's ONLY source is failing, the gap-analysis hint rides in
    the platform payload (the deleted endpoint's useful half)."""
    from app.services import data_source_metrics

    for _ in range(5):
        data_source_metrics.record_failure("yfinance", "fundamentals", reason="429")
    r = client.get("/api/platform/health")
    assert r.status_code == 200
    suggestions = r.json()["suggestions"]
    assert any(s["op"] == "fundamentals" for s in suggestions)
    hit = next(s for s in suggestions if s["op"] == "fundamentals")
    assert set(hit.keys()) == {"op", "why", "suggestion"}


def test_health_scheduler_lists_registered_jobs_before_first_event(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
):
    """SAL-1 scheduler truth: EVERY registered job appears in the payload —
    with next_run_time/trigger metadata — even before its first run/error
    event. Before this, a cron that never fired was invisible (the way the
    13F refreshes died unnoticed for months)."""
    # Force a FRESH (never-started) scheduler singleton: earlier tests that
    # run the app lifespan start+stop the shared one, draining its pending
    # job list — get_jobs() would return [] and the test would be
    # order-dependent. monkeypatch restores the old instance afterwards.
    import app.scheduler as scheduler_mod

    monkeypatch.setattr(scheduler_mod, "_scheduler", None)

    r = client.get("/api/platform/health")
    assert r.status_code == 200
    jobs = {j["job_id"]: j for j in r.json()["scheduler"]}
    # Core cron jobs registered in app/scheduler/__init__.py must be present
    # even though no scheduler event ever fired in this test process.
    for expected in ("scan_alerts", "refresh_sec_13f", "refresh_institutionals",
                     "db_backup", "health_probes_fast"):
        assert expected in jobs, f"registered job {expected} missing from payload"
        j = jobs[expected]
        # Merged shape: stats fields (zeroed) + registration metadata keys.
        assert j["runs"] == 0
        assert "next_run_time" in j
        assert "trigger" in j
        assert j["trigger"] is not None


def test_health_overall_degraded_when_last_scan_failed(client: TestClient, db: Session):
    """The rollup flags a crashed LAST scan as degraded (a user-cancelled
    run must not)."""
    from datetime import UTC, datetime

    from app.models import ScanRun

    run = ScanRun(
        trigger="cron", status="failed", error_message="boom",
        started_at=datetime.now(UTC), completed_at=datetime.now(UTC),
    )
    db.add(run)
    db.commit()

    r = client.get("/api/platform/health")
    body = r.json()
    assert body["overall"] == "degraded"
    assert any("Ultimo scan fallito" in reason for reason in body["reasons"])


def test_health_overall_degraded_when_scan_succeeded_over_nothing(
    client: TestClient, db: Session
):
    """End-to-end over the REAL endpoint, not a SimpleNamespace.

    The unit tests for this rule feed hand-built objects, so they stay green
    even if the API payload model stops carrying the work counters — and then
    the rule reads None ("unknown") and silently never fires on the two paths
    that actually reach the user. This exercises ScanRun → _recent_scans →
    RecentScanOut → compute_rollup, which is where that break would happen."""
    from datetime import UTC, datetime

    from app.models import ScanRun

    now = datetime.now(UTC)
    db.add(ScanRun(
        trigger="cron", status="success",
        started_at=now, completed_at=now,
        stocks_scanned=0, stocks_skipped=999,
    ))
    db.commit()

    body = client.get("/api/platform/health").json()
    assert body["overall"] == "degraded"
    assert any("nessun titolo analizzato" in r for r in body["reasons"]), body["reasons"]


# ---------------------------------------------------------------------------
# /api/platform/logs
# ---------------------------------------------------------------------------

def test_logs_endpoint_requires_auth():
    """No session cookie → 401. Use TestClient without the lifespan (no `with`
    context manager) to avoid the startup hook hitting the production DB."""
    c = TestClient(app, raise_server_exceptions=True)
    r = c.get("/api/platform/logs")
    assert r.status_code in (401, 403)


def test_logs_endpoint_returns_recent_records(client: TestClient):
    configure_logging()
    logger.warning("test-marker-logs-endpoint-aaa")
    r = client.get("/api/platform/logs?limit=200")
    assert r.status_code == 200
    records = r.json()
    assert any("test-marker-logs-endpoint-aaa" in rec["message"] for rec in records)


def test_logs_endpoint_filters_by_level(client: TestClient):
    configure_logging()
    logger.info("test-marker-info-bbb")
    logger.error("test-marker-error-ccc")
    r = client.get("/api/platform/logs?level=ERROR&limit=200")
    assert r.status_code == 200
    records = r.json()
    msgs = [rec["message"] for rec in records]
    assert any("test-marker-error-ccc" in m for m in msgs)
    assert not any("test-marker-info-bbb" in m for m in msgs)


def test_logs_endpoint_filters_by_search_substring(client: TestClient):
    configure_logging()
    logger.warning("unique-string-zzz123")
    r = client.get("/api/platform/logs?search=zzz123&limit=200")
    assert r.status_code == 200
    records = r.json()
    assert len(records) >= 1
    assert all("zzz123" in rec["message"] for rec in records)


def test_data_health_ages_are_real_days_not_string_subtraction(client, db):
    """Le eta' si calcolano in Python, non in SQL.

    Postgres valuta `CURRENT_DATE - MAX(date)` come giorni interi; SQLite tratta
    le date come stringhe e la stessa espressione NON fallisce — sottrae due
    stringhe e restituisce un numero privo di senso. Il campo si popolerebbe
    comunque, quindi nessuna asserzione sulla presenza l'avrebbe vista. Qui si
    asserisce il VALORE contro una riga di eta' nota.
    """
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import text

    from app.models import Stock

    s = Stock(ticker="ZZAGE", name="T", exchange="TEST", currency="USD")
    db.add(s)
    db.flush()
    d = (datetime.now(UTC).date() - timedelta(days=5)).isoformat()
    db.execute(
        text("INSERT INTO ohlcv_daily (stock_id, date, open, high, low, close, volume)"
             " VALUES (:s, :d, 1, 1, 1, 1, 1)"),
        {"s": s.id, "d": d},
    )
    db.commit()

    body = client.get("/api/platform/health").json()
    age = body["data_health"]["ohlcv_age_days"]
    assert age is not None, "l'eta' non deve essere nulla con dati presenti"
    assert 0 <= age <= 5, f"eta' implausibile: {age}"


def test_deploy_block_reports_what_is_running(client):
    """La sola risposta diretta a 'la mia modifica e' a schermo'."""
    body = client.get("/api/platform/health").json()
    dep = body["deploy"]
    assert "git_sha" in dep
    assert dep["uptime_seconds"] is not None and dep["uptime_seconds"] >= 0


class TestProvenienzaImmagine:
    """Il blocco `deploy` porta cosa l'immagine puo' dimostrare di se'.

    Non e' cosmesi da cruscotto: il 12 settembre 2026 il livello che scarica le
    patch Debian e' risultato inerte da 24 giorni e NESSUNA superficie dell'app
    lo mostrava, quindi l'unico modo di scoprirlo e' stato che trivy rompesse
    la pipeline. Queste date rendono quel guasto leggibile prima.
    """

    def test_i_campi_esistono_e_in_sviluppo_dicono_NON_SO(self, client):
        """In sviluppo `/etc/image-provenance.json` non esiste.

        ⚠️ Il contratto e' che i campi ci siano e valgano `None`, non che
        spariscano: un campo assente si legge come «questa versione non lo
        sa», un `None` esplicito come «non lo so ADESSO». Il cruscotto deve
        poter distinguere le due cose."""
        r = client.get("/api/platform/health")
        assert r.status_code == 200
        deploy = r.json()["deploy"]
        for campo in ("image_built_at", "apt_security_date", "apt_age_days", "apt_stale"):
            assert campo in deploy, campo
        assert deploy["apt_stale"] is None

    def test_con_una_provenienza_fresca_il_payload_la_riporta(self, client, tmp_path, monkeypatch):
        import json

        from app.services import image_provenance

        f = tmp_path / "image-provenance.json"
        f.write_text(json.dumps({
            "apt_security_date": _oggi_iso(),
            "built_at": "2026-09-12T14:39:33Z",
        }), encoding="utf-8")
        monkeypatch.setattr(image_provenance, "PROVENANCE_PATH", f)

        deploy = client.get("/api/platform/health").json()["deploy"]
        assert deploy["apt_age_days"] == 0
        assert deploy["apt_stale"] is False
        assert deploy["image_built_at"] is not None

    def test_una_provenienza_VECCHIA_viene_segnalata(self, client, tmp_path, monkeypatch):
        """Il controllo negativo del test sopra: se questo non diventasse
        `True`, «stantia» sarebbe una parola che non si accende mai — e un
        semaforo sempre verde e' esattamente il guasto che stiamo chiudendo."""
        import json
        from datetime import UTC, datetime, timedelta

        from app.services import image_provenance

        vecchia = (
            datetime.now(UTC).date()
            - timedelta(days=image_provenance.STALE_AFTER_DAYS + 3)
        )
        f = tmp_path / "image-provenance.json"
        f.write_text(json.dumps({
            "apt_security_date": vecchia.isoformat(),
            "built_at": "2026-08-19T10:00:00Z",
        }), encoding="utf-8")
        monkeypatch.setattr(image_provenance, "PROVENANCE_PATH", f)

        deploy = client.get("/api/platform/health").json()["deploy"]
        assert deploy["apt_stale"] is True
        assert deploy["apt_age_days"] == image_provenance.STALE_AFTER_DAYS + 3


def _oggi_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).date().isoformat()
