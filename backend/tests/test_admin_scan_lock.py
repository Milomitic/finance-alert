"""The heavy admin endpoints must hold the single-scan slot.

`redownload-ohlcv` always did. `warmup-fundamentals` did not, though it is the
same shape of work — minutes of upstream fetching followed by
`score_service.recompute_all`, which is the recompute half of a scan. Two
writers on the same score rows, competing for the same rate-limited upstream;
on SQLite that is the "database is locked" contention scan_lock exists to
prevent. Fixed 2026-09-02.

These tests take the slot for real and assert a 409, so they fail if either
endpoint stops honouring it.
"""
from fastapi.testclient import TestClient

from app.main import app
from app.services import scan_lock


def _post(url: str, **kw):
    """Authenticated POST. The auth check is covered in
    test_admin_endpoints_auth.py; here it would only mask the 409."""
    from app.api.deps import get_current_user
    from app.models import User

    app.dependency_overrides[get_current_user] = lambda: User(
        id=1, username="t", password_hash="x",
    )
    try:
        return TestClient(app).post(url, **kw)
    finally:
        app.dependency_overrides.clear()


def test_warmup_refuses_while_a_scan_holds_the_slot(db):
    with scan_lock.scan_slot() as acquired:
        assert acquired          # this test now IS the scan
        r = _post("/api/admin/warmup-fundamentals?limit=1")
    assert r.status_code == 409
    assert "scan" in r.json()["detail"].lower()


def test_redownload_refuses_while_a_scan_holds_the_slot(db):
    with scan_lock.scan_slot() as acquired:
        assert acquired
        r = _post("/api/admin/redownload-ohlcv?limit=1")
    assert r.status_code == 409


def test_the_slot_is_released_afterwards(db):
    """A 409 must not leave the slot held — the context manager releases only
    what it acquired, and the guard raises INSIDE the `with`."""
    with scan_lock.scan_slot() as acquired:
        assert acquired
        _post("/api/admin/warmup-fundamentals?limit=1")
    assert not scan_lock.is_running()
