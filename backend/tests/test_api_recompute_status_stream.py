"""SSE score-recompute status stream — mirror of the scan-status stream test."""
import asyncio
import json
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from app.main import app
from app.models import ScanRun
from app.models.scan_run import KIND_SCORE_RECOMPUTE
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
                "GET", "/api/scores/recompute-status/stream", timeout=10.0
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


def test_recompute_stream_initial_status_when_none(db: Session):
    _setup_overrides(db)
    try:
        statuses = _first_status_events()
        assert statuses and statuses[0]["is_running"] is False
    finally:
        app.dependency_overrides.clear()


def test_recompute_stream_reflects_running(db: Session):
    db.add(
        ScanRun(
            kind=KIND_SCORE_RECOMPUTE,
            trigger="manual",
            status="running",
            started_at=datetime.now(UTC),
            progress_done=120,
            progress_total=999,
        )
    )
    db.commit()
    _setup_overrides(db)
    try:
        statuses = _first_status_events()
        assert statuses and statuses[0]["is_running"] is True
    finally:
        app.dependency_overrides.clear()
