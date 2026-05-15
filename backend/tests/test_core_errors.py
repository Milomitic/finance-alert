"""Le eccezioni tipate devono comportarsi come Exception ma essere distinguibili
via except specifico — così possiamo refactor-are i broad-except nei router."""
from app.core.errors import (
    RateLimitError, UpstreamError, UpstreamTimeout, UpstreamUnavailable,
)


def test_hierarchy_root_is_exception():
    assert issubclass(UpstreamError, Exception)


def test_upstream_subclasses_inherit_from_upstream_error():
    assert issubclass(RateLimitError, UpstreamError)
    assert issubclass(UpstreamTimeout, UpstreamError)
    assert issubclass(UpstreamUnavailable, UpstreamError)


def test_upstream_error_carries_source_and_op_metadata():
    e = RateLimitError("rate limit hit", source="yfinance", op="fundamentals")
    assert e.source == "yfinance"
    assert e.op == "fundamentals"
    assert "rate limit" in str(e)
