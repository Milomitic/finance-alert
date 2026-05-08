"""Tests for earnings_session_timing.classify_session_timing.

The function maps (UTC HH:MM, country) -> "pre" | "after" | None.
US session: 14:30-21:00 UTC. Anything < 14:30 = pre, >= 21:00 = after,
mid-session prints (extremely rare in practice) = None.
Non-US countries currently fall through to None -- no session model yet.
"""
from app.services.earnings_session_timing import classify_session_timing


def test_us_pre_market_classified_as_pre() -> None:
    assert classify_session_timing("13:30", "US") == "pre"


def test_us_just_before_open_classified_as_pre() -> None:
    # 14:29 is still pre -- open is at 14:30
    assert classify_session_timing("14:29", "US") == "pre"


def test_us_at_open_returns_none() -> None:
    # 14:30 is the open boundary -- classified as in-session (None)
    assert classify_session_timing("14:30", "US") is None


def test_us_mid_session_returns_none() -> None:
    assert classify_session_timing("17:00", "US") is None


def test_us_at_close_classified_as_after() -> None:
    # 21:00 is the close boundary -- earnings at exactly 21:00 are after
    assert classify_session_timing("21:00", "US") == "after"


def test_us_after_market_classified_as_after() -> None:
    assert classify_session_timing("22:30", "US") == "after"


def test_none_time_returns_none() -> None:
    assert classify_session_timing(None, "US") is None


def test_none_country_returns_none() -> None:
    assert classify_session_timing("13:30", None) is None


def test_unparseable_time_returns_none() -> None:
    assert classify_session_timing("not-a-time", "US") is None


def test_non_us_country_returns_none_for_now() -> None:
    # Future work: model UK/EU sessions. For now we return None to avoid
    # showing a wrong icon.
    assert classify_session_timing("17:00", "GB") is None
