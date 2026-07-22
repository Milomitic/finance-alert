"""SSE scan-status stream: emits an initial `status` event carrying the current
scan snapshot. Reuses the streaming transport harness from
test_api_platform_stream (buffering HTTP clients can't read an infinite stream).
"""
import asyncio
import json
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from app.main import app
from app.models import ScanRun
from app.models.scan_run import KIND_ALERTS_SCAN
from tests.test_api_platform_stream import (
    _parse_sse,
    _setup_overrides,
    _StreamingASGITransport,
)


def _first_status_events() -> list:
    async def _run() -> bytes:
        transport = _StreamingASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            buf = b""
            async with client.stream(
                "GET", "/api/alerts/scan-status/stream", timeout=10.0
            ) as response:
                assert response.status_code == 200
                assert "text/event-stream" in response.headers.get("content-type", "")
                async for chunk in response.aiter_raw():
                    buf += chunk
                    if b"event: status" in buf:
                        break
                    if len(buf) > 50_000:
                        break
            return buf

    buf = asyncio.run(_run())
    return [json.loads(d) for ev, d in _parse_sse(buf) if ev == "status"]


def test_stream_initial_status_when_no_scan(db: Session):
    _setup_overrides(db)
    try:
        statuses = _first_status_events()
        assert statuses, "no status event emitted"
        assert statuses[0]["is_running"] is False
    finally:
        app.dependency_overrides.clear()


def test_stream_reflects_a_running_scan(db: Session):
    db.add(
        ScanRun(
            kind=KIND_ALERTS_SCAN,
            trigger="manual",
            status="running",
            started_at=datetime.now(UTC),
            current_target="fase test",
            progress_done=40,
            progress_total=100,
        )
    )
    db.commit()
    _setup_overrides(db)
    try:
        statuses = _first_status_events()
        assert statuses and statuses[0]["is_running"] is True
        assert statuses[0]["current_target"] == "fase test"
    finally:
        app.dependency_overrides.clear()


def test_stream_requires_auth(db: Session):
    # No get_current_user override → the dependency rejects BEFORE streaming.
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        r = client.get("/api/alerts/scan-status/stream")
    assert r.status_code == 401
