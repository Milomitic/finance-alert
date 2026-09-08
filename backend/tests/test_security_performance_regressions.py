"""Real auth/SSE resource lifecycle, HTTP privacy and bounded login state."""
import asyncio
import threading

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import deps, platform_health
from app.core import db as core_db
from app.core import security
from app.core.config import settings
from app.main import app
from app.models import Stock, User
from app.services import login_throttle
from tests.test_api_platform_stream import _StreamingASGITransport


@pytest.mark.parametrize("path", [
    "/api/alerts/scan-status/stream", "/api/scores/recompute-status/stream", "/api/platform/stream",
])
@pytest.mark.asyncio
async def test_authenticated_stream_has_no_idle_connection(tmp_path, monkeypatch, path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'sse.db').as_posix()}",
        connect_args={"check_same_thread": False}, pool_size=2, max_overflow=0,
    )
    core_db.Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine)
    monkeypatch.setattr(core_db, "SessionLocal", maker)
    monkeypatch.setattr(deps, "SessionLocal", maker)
    with maker() as db:
        db.add(User(username="audit", password_hash="unused"))
        db.commit()
    main_thread = threading.get_ident()
    original = platform_health._recent_scans

    def read_scans(db):
        assert threading.get_ident() != main_thread
        return original(db)

    monkeypatch.setattr(platform_health, "_recent_scans", read_scans)

    async def check():
        async with httpx.AsyncClient(
            transport=_StreamingASGITransport(app), base_url="http://testserver",
            cookies={settings.session_cookie_name: security.create_session_token("audit")},
        ) as client:
            # Sequential subscriptions still catch connections retained by an
            # open stream; the pool must be entirely available after each event.
            for _ in range(3):
                async with client.stream("GET", path) as response:
                    assert response.status_code == 200
                    async for _chunk in response.aiter_raw():
                        assert engine.pool.checkedout() == 0
                        break

    try:
        await asyncio.wait_for(check(), timeout=8)
        assert engine.pool.checkedout() == 0
    finally:
        engine.dispose()


@pytest.mark.parametrize("payload", [[], "user", {"u": []}, {"u": ""}, {"u": "x" * 65}])
def test_signed_token_invalid_shape_is_rejected(payload):
    token = security._serializer().dumps(payload)
    assert security.read_session_token(token) is None


def test_http_api_response_cannot_be_cached():
    client = TestClient(app)
    assert client.get("/api/auth/me").headers["Cache-Control"] == "no-store"


def test_cross_site_bodyless_logout_is_rejected():
    client = TestClient(app)
    assert client.post("/api/auth/logout", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.post("/api/auth/logout", headers={"Sec-Fetch-Site": "same-origin"}).status_code == 204


def test_username_flood_is_bounded_and_does_not_evict_locked_user(monkeypatch):
    login_throttle.reset()
    monkeypatch.setattr(login_throttle, "_MAX_TRACKED_USERS", 2)
    monkeypatch.setattr(login_throttle, "_now", lambda: 100.0)
    try:
        for _ in range(settings.login_max_failed_attempts):
            login_throttle.record_failure("victim")
        for i in range(100):
            login_throttle.record_failure(f"unknown{i}")
        assert len(login_throttle._state) == 2
        assert login_throttle.retry_after_seconds("victim") is not None
        assert login_throttle.retry_after_seconds("new") is not None
        monkeypatch.setattr(login_throttle, "_now", lambda: 100.0 + settings.login_lockout_seconds)
        assert login_throttle.retry_after_seconds("new") is None
    finally:
        login_throttle.reset()


def test_untrusted_xml_dtd_is_rejected_by_both_importers():
    from defusedxml.common import DefusedXmlException

    from app.services import sec_13f_scraper, yahoo_rss_news_service

    # Small fixture: proves entity rejection without allocating an XML bomb.
    xml = '<!DOCTYPE rss [<!ENTITY payload "expanded">]><rss>&payload;</rss>'
    with pytest.raises(DefusedXmlException):
        yahoo_rss_news_service._parse(xml)
    assert list(sec_13f_scraper._parse_info_table(xml)) == []


@pytest.mark.parametrize("path", ["/api/stocks/quotes?tickers=AUDIT", "/api/stocks/AUDIT/quote"])
def test_quote_provider_runs_without_reserving_sql(tmp_path, monkeypatch, path):
    from app.services import live_quote_service

    engine = create_engine(
        f"sqlite:///{(tmp_path / 'quotes.db').as_posix()}",
        connect_args={"check_same_thread": False}, pool_size=3, max_overflow=0,
    )
    core_db.Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine)
    monkeypatch.setattr(deps, "SessionLocal", maker)
    with maker() as db:
        db.add(User(username="audit", password_hash="unused"))
        db.add(Stock(ticker="AUDIT", name="Synthetic", exchange="TEST"))
        db.commit()

    def quote(_ticker):
        assert engine.pool.checkedout() == 0
        return live_quote_service.LiveQuote(ticker="AUDIT", price=100)

    monkeypatch.setattr(live_quote_service, "get_quote", quote)
    monkeypatch.setattr(live_quote_service, "get_quotes_batch", lambda _: {"AUDIT": quote("AUDIT")})
    try:
        client = TestClient(app)
        client.cookies.set(settings.session_cookie_name, security.create_session_token("audit"))
        assert client.get(path).status_code == 200
    finally:
        engine.dispose()
