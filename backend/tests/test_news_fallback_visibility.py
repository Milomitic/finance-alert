"""A fallback tier that is not configured must say so.

Production ran with 429 of 999 tickers newsless because the FIRST news
fallback had no API key and returned an empty list — indistinguishable, to
every caller, from "this ticker has no news". Nothing logged it, no metric
counted it, and the health page reported the news source at 99% because the
successes it counted were calls that had quietly returned nothing.
"""
import pytest
from loguru import logger

from app.services import finnhub_news_service as svc


@pytest.fixture
def captured() -> list[str]:
    """loguru does not feed pytest's caplog (that only sees stdlib records),
    so the sink is attached directly."""
    lines: list[str] = []
    sink_id = logger.add(lambda m: lines.append(m), level="WARNING")
    yield lines
    logger.remove(sink_id)


def test_a_missing_key_is_announced(monkeypatch, captured):
    monkeypatch.setattr(svc, "is_enabled", lambda: False)
    svc._WARNED_DISABLED.clear()
    assert svc.fetch_company_news("AAPL") == []
    assert any("not configured" in line for line in captured), (
        "a permanently inert fallback must announce itself at least once"
    )


def test_it_is_announced_once_not_per_call(monkeypatch, captured):
    """A missing key is a PERMANENT condition. One line per call would be
    thousands of identical lines, which trains everyone to filter the very
    channel trying to tell them something."""
    monkeypatch.setattr(svc, "is_enabled", lambda: False)
    svc._WARNED_DISABLED.clear()
    for _ in range(25):
        svc.fetch_company_news("AAPL")
    hits = [line for line in captured if "not configured" in line]
    assert len(hits) == 1, f"expected exactly one warning, got {len(hits)}"


def test_a_configured_key_says_nothing(monkeypatch, captured):
    """It must not fire on the healthy path — that is how a signal becomes
    noise."""
    monkeypatch.setattr(svc, "is_enabled", lambda: True)
    monkeypatch.setattr(svc, "_is_blocked", lambda scope=None: (True, "breaker"))
    svc._WARNED_DISABLED.clear()
    svc.fetch_company_news("AAPL")
    assert not [line for line in captured if "not configured" in line]
