"""SSE stream emits: snapshot (initial), log (each new record), keepalive
(idle). We don't test the 30s keepalive (too slow); we test snapshot + log.

Testing approach: httpx.ASGITransport and starlette TestClient both buffer the
entire response body before returning, so neither works for an infinite SSE
stream. We use a custom streaming ASGI transport based on asyncio queues that
allows the consumer to break out early and cancel the ASGI app task.
"""
import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from loguru import logger
from starlette.types import ASGIApp

from app.api import deps as deps_module
from app.core.logging import configure_logging
from app.main import app
from app.models import User

# ---------------------------------------------------------------------------
# Minimal streaming ASGI transport (asyncio-based)
# ---------------------------------------------------------------------------

class _StreamingASGITransport(httpx.AsyncBaseTransport):
    """An httpx async transport that runs the ASGI app in an asyncio task and
    streams body chunks through a queue. The caller can break out of the async
    iterator and the ASGI task will be cancelled.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        scope: dict[str, Any] = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": request.method,
            "headers": [(k.lower(), v) for k, v in request.headers.raw],
            "scheme": request.url.scheme,
            "path": request.url.path,
            "raw_path": request.url.raw_path.split(b"?")[0],
            "query_string": request.url.query,
            "server": (request.url.host, request.url.port or 80),
            "client": ("testclient", 50000),
            "root_path": "",
        }

        body_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        response_started: asyncio.Future[tuple[int, list]] = asyncio.get_running_loop().create_future()
        request_complete = False
        disconnect_event = asyncio.Event()

        async def receive() -> dict[str, Any]:
            nonlocal request_complete
            if not request_complete:
                request_complete = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await disconnect_event.wait()
            return {"type": "http.disconnect"}

        async def send_to_app(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                response_started.set_result((
                    message["status"],
                    message.get("headers", []),
                ))
            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                if body:
                    await body_queue.put(body)
                if not message.get("more_body", False):
                    await body_queue.put(None)  # sentinel = done

        # Start the ASGI app as a background task
        app_task = asyncio.create_task(self._app(scope, receive, send_to_app))

        # Wait for response headers
        status_code, raw_headers = await response_started

        # Build a streaming response body

        class _StreamBody(httpx.AsyncByteStream):
            async def __aiter__(self) -> AsyncIterator[bytes]:
                while True:
                    chunk = await body_queue.get()
                    if chunk is None:
                        break
                    yield chunk

            async def aclose(self) -> None:
                # Signal the ASGI app that the client disconnected
                disconnect_event.set()
                app_task.cancel()
                try:
                    await app_task
                except (asyncio.CancelledError, Exception):
                    pass

        response = httpx.Response(
            status_code=status_code,
            headers=raw_headers,
            stream=_StreamBody(),
            request=request,
        )
        return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_sse(chunk: bytes) -> list[tuple[str, str]]:
    """Parse a raw SSE chunk into [(event, data), ...] tuples."""
    events: list[tuple[str, str]] = []
    current_event: str | None = None
    current_data_parts: list[str] = []
    for line in chunk.decode("utf-8", errors="replace").splitlines():
        if line.startswith(":"):
            continue
        if line == "":
            if current_event and current_data_parts:
                events.append((current_event, "\n".join(current_data_parts)))
            current_event = None
            current_data_parts = []
            continue
        if line.startswith("event:"):
            current_event = line[6:].strip()
        elif line.startswith("data:"):
            current_data_parts.append(line[5:].strip())
    if current_event and current_data_parts:
        events.append((current_event, "\n".join(current_data_parts)))
    return events


def _setup_overrides(db) -> User:
    """Override get_db and get_current_user on the FastAPI app.
    Mirrors the pattern in test_api_platform_health.py."""
    user = User(username="test", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[deps_module.get_db] = lambda: db
    app.dependency_overrides[deps_module.get_current_user] = lambda: user
    return user


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_stream_emits_initial_snapshot(db):
    configure_logging()
    _setup_overrides(db)
    try:
        async def _run() -> bytes:
            transport = _StreamingASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                buf = b""
                async with client.stream(
                    "GET", "/api/platform/stream", timeout=10.0
                ) as response:
                    assert response.status_code == 200
                    assert "text/event-stream" in response.headers.get(
                        "content-type", ""
                    )
                    async for chunk in response.aiter_raw():
                        buf += chunk
                        if b"event: snapshot" in buf:
                            break
                        if len(buf) > 50_000:
                            break
                return buf

        buf = asyncio.run(_run())
        events = _parse_sse(buf)
        assert any(ev == "snapshot" for ev, _ in events), (
            f"no snapshot event in first chunk; got: {[ev for ev, _ in events]}"
        )
    finally:
        app.dependency_overrides.clear()


def test_stream_pushes_log_record_after_warning(db):
    configure_logging()
    _setup_overrides(db)

    try:
        async def _run() -> bytes:
            transport = _StreamingASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                buf = b""

                # Schedule a warning to fire 1s after we start streaming.
                # Fires in the same event loop, so call_soon_threadsafe
                # on the loop from the SSE endpoint correctly enqueues it.
                async def _emit_warning() -> None:
                    await asyncio.sleep(1.0)
                    logger.warning("stream-test-marker-zzzzzzzz")

                warning_task = asyncio.create_task(_emit_warning())
                try:
                    async with client.stream(
                        "GET", "/api/platform/stream", timeout=10.0
                    ) as response:
                        assert response.status_code == 200
                        async for chunk in response.aiter_raw():
                            buf += chunk
                            if b"stream-test-marker-zzzzzzzz" in buf:
                                break
                            if len(buf) > 200_000:
                                break
                finally:
                    warning_task.cancel()
                    try:
                        await warning_task
                    except asyncio.CancelledError:
                        pass

                return buf

        buf = asyncio.run(_run())
        events = _parse_sse(buf)
        log_events = [json.loads(data) for ev, data in events if ev == "log"]
        assert any(
            "stream-test-marker-zzzzzzzz" in rec["message"]
            for rec in log_events
        ), (
            f"no matching log event; got messages: "
            f"{[rec.get('message') for rec in log_events]}"
        )
    finally:
        app.dependency_overrides.clear()
