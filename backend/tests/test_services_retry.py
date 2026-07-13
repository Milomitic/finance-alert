"""with_backoff: retry esponenziale con jitter, abort dopo N tentativi, rispetta
solo le eccezioni listate in `on=`."""

import pytest

from app.core.errors import RateLimitError, UpstreamTimeout
from app.services._retry import with_backoff


def test_success_on_first_try_no_retry():
    calls = {"n": 0}

    @with_backoff(retries=3, base_delay=0.01, max_delay=0.1, on=(UpstreamTimeout,))
    def f():
        calls["n"] += 1
        return "ok"

    assert f() == "ok"
    assert calls["n"] == 1


def test_retries_on_listed_exception_and_succeeds():
    calls = {"n": 0}

    @with_backoff(retries=3, base_delay=0.001, max_delay=0.01, on=(UpstreamTimeout,))
    def f():
        calls["n"] += 1
        if calls["n"] < 3:
            raise UpstreamTimeout("transient")
        return "ok"

    assert f() == "ok"
    assert calls["n"] == 3


def test_gives_up_after_retries_and_reraises():
    @with_backoff(retries=2, base_delay=0.001, max_delay=0.01, on=(UpstreamTimeout,))
    def f():
        raise UpstreamTimeout("always")

    with pytest.raises(UpstreamTimeout):
        f()


def test_does_not_retry_unlisted_exception():
    calls = {"n": 0}

    @with_backoff(retries=3, base_delay=0.001, max_delay=0.01, on=(UpstreamTimeout,))
    def f():
        calls["n"] += 1
        raise RateLimitError("not listed")

    with pytest.raises(RateLimitError):
        f()
    assert calls["n"] == 1  # nessun retry


def test_delay_is_exponential_capped_at_max(monkeypatch):
    sleeps: list[float] = []

    def fake_sleep(s: float) -> None:
        sleeps.append(s)

    monkeypatch.setattr("app.services._retry.time.sleep", fake_sleep)

    @with_backoff(retries=4, base_delay=0.1, max_delay=0.5, on=(UpstreamTimeout,), jitter=False)
    def f():
        raise UpstreamTimeout("fail")

    with pytest.raises(UpstreamTimeout):
        f()
    # Senza jitter: 0.1, 0.2, 0.4 (3 sleep tra 4 tentativi), capped a 0.5.
    assert sleeps == [0.1, 0.2, 0.4]
