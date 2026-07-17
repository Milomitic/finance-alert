"""CSRF-lite (require_json) coverage: structural + behavioral (B4-11).

Il test strutturale enumera TUTTE le route mutanti (POST/PATCH/PUT/DELETE)
registrate su `app` e pretende `Depends(require_json)` su ognuna — così un
endpoint mutante aggiunto in futuro senza la dipendenza fa fallire la suite
invece di passare inosservato (stesso spirito di test_admin_endpoints_auth).

I test comportamentali fissano il contratto di require_json dopo la
generalizzazione B4-11:
- richiesta SENZA body e SENZA Content-Type -> permessa (il client FE,
  frontend/src/api/client.ts, stampa l'header solo quando c'è un body);
- Content-Type non-JSON -> 415, anche a body vuoto (un form HTML forgiato
  manda SEMPRE un Content-Type: x-www-form-urlencoded/multipart/text-plain,
  quindi il vettore CSRF-da-form resta chiuso);
- DELETE senza body -> permessa (carve-out storico, ora generalizzato).
"""
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_json
from app.main import app
from app.models import User

MUTATING_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


def _all_api_routes(routes) -> list[APIRoute]:
    """Every APIRoute reachable from `routes`, however FastAPI nests them.

    FastAPI <=0.136 flattened `include_router()`'d routes straight into
    `app.routes`, so a one-level list comprehension saw them all. 0.139 keeps
    each inclusion as a private `_IncludedRouter` wrapper instead, and a flat
    scan silently drops to the handful of routes registered directly on `app` —
    which would make the coverage assert below vacuous rather than failing.
    (That is exactly what test_enumeration_sees_the_real_app caught on the
    upgrade.) So: recurse, and support both shapes without pinning either.
    """
    found: list[APIRoute] = []
    for r in routes:
        if isinstance(r, APIRoute):
            found.append(r)
        # 0.139+: the inclusion wrapper keeps the original APIRouter…
        inner = getattr(r, "original_router", None)
        # …older/other shapes (Mount, APIRouter) expose .routes directly.
        if inner is None:
            inner = r if hasattr(r, "routes") and not isinstance(r, APIRoute) else None
        if inner is not None:
            found.extend(_all_api_routes(getattr(inner, "routes", [])))
    return found


def _mutating_routes() -> list[APIRoute]:
    return [
        r
        for r in _all_api_routes(app.routes)
        if r.methods & MUTATING_METHODS
    ]


def _dependant_uses(dependant, target) -> bool:
    """Walk ricorsivo dell'albero delle dipendenze FastAPI della route."""
    return any(
        dep.call is target or _dependant_uses(dep, target)
        for dep in dependant.dependencies
    )


def test_enumeration_sees_the_real_app() -> None:
    # Sanity: se il conteggio crolla, il test strutturale sta guardando
    # un'app sbagliata/vuota e l'assert di copertura sarebbe vacuo.
    # Al momento della scrittura le route mutanti sono 23.
    assert len(_mutating_routes()) >= 20


def test_every_mutating_route_has_require_json() -> None:
    missing = [
        f"{sorted(r.methods)} {r.path}"
        for r in _mutating_routes()
        if not _dependant_uses(r.dependant, require_json)
    ]
    assert not missing, (
        "Route mutanti senza Depends(require_json) (CSRF-lite, B4-11): "
        + ", ".join(missing)
    )


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_form_content_type_is_rejected_415(client: TestClient) -> None:
    # Un form HTML forgiato arriva come x-www-form-urlencoded: deve morire
    # in require_json (415) prima ancora del parsing del body.
    resp = client.post("/api/auth/login", data={"username": "x", "password": "y"})
    assert resp.status_code == 415


def test_non_json_content_type_rejected_even_without_body(client: TestClient) -> None:
    # Content-Type presente ma non-JSON -> 415 anche a body vuoto: è il caso
    # del form forgiato senza campi (i form stampano sempre un Content-Type).
    resp = client.post(
        "/api/alerts/scan/stop", headers={"Content-Type": "text/plain"}
    )
    assert resp.status_code == 415


def test_bodyless_post_without_content_type_is_allowed(client: TestClient) -> None:
    # Il client FE non stampa Content-Type sui POST senza body (scan/stop,
    # recompute, probes/run, ...): devono passare il gate.
    resp = client.post("/api/alerts/scan/stop")
    assert resp.status_code == 200
    assert resp.json()["was_running"] is False


def test_json_post_with_body_is_allowed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `json=` stampa Content-Type: application/json -> passa il gate.
    # Lo scan vero non deve girare (TestClient esegue i BackgroundTasks
    # in modo sincrono): stub come in test_api_alerts.test_scan_accepted.
    monkeypatch.setattr("app.api.alerts._run_scan_in_background", lambda _ids: None)
    resp = client.post("/api/alerts/scan", json={})
    assert resp.status_code == 202


def test_delete_without_body_is_allowed(client: TestClient) -> None:
    # DELETE senza body né header passa require_json e arriva all'handler
    # (che qui risponde 404 perché l'id non esiste — NON 415).
    resp = client.delete("/api/price-alerts/999999")
    assert resp.status_code == 404
