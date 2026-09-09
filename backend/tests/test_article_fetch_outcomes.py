"""A blocked source and a broken source must not look the same.

The enrichment is best-effort: every failure returns `None` and the caller
carries on with title+summary. That design is right, and it is also what made
the failure unobservable — a host WE refuse and a host that is DOWN both
arrive as `None`, and the only per-URL detail was a `logger.debug` line, which
production never emits.

It stopped being academic when the SSRF policy shipped. A filter that quietly
drops legitimate publishers is indistinguishable, from the outside, from a
provider outage; the only way to tell was a hand-run probe against the live
cache. `finance_alert_article_fetch_total{outcome=...}` is the answer, and
these tests pin the distinctions it has to keep.
"""

from urllib3.exceptions import HTTPError

from app.core.app_metrics import ARTICLE_FETCH
from app.core.public_http import ArticlePolicyError
from app.services import news_body_fetcher as nbf

URL = "https://example.test/article"


def _count(outcome: str) -> float:
    return ARTICLE_FETCH.labels(outcome=outcome)._value.get()


def _run(monkeypatch, raiser, outcome: str) -> float:
    """Fetch once with `raiser` as the network, return the delta on `outcome`."""
    nbf._clear_caches_for_tests()
    monkeypatch.setattr(nbf, "fetch_public_text", raiser)
    before = _count(outcome)
    assert nbf.fetch_article_body(URL) is None
    return _count(outcome) - before


class TestOurRefusalIsNotTheirFailure:
    def test_a_policy_block_counts_as_policy(self, monkeypatch):
        def blocked(*_a, **_k):
            raise ArticlePolicyError("Non-public article destination")

        assert _run(monkeypatch, blocked, "policy") == 1

    def test_a_policy_block_does_NOT_count_as_an_upstream_failure(self, monkeypatch):
        # The whole point: before ArticlePolicyError existed both were a bare
        # ValueError, so this delta was 1 and the panel blamed the publisher.
        def blocked(*_a, **_k):
            raise ArticlePolicyError("Non-public article destination")

        assert _run(monkeypatch, blocked, "http") == 0

    def test_a_non_2xx_counts_as_http_not_policy(self, monkeypatch):
        def refused(*_a, **_k):
            raise ValueError("Article HTTP failure")

        nbf._clear_caches_for_tests()
        monkeypatch.setattr(nbf, "fetch_public_text", refused)
        before_http, before_policy = _count("http"), _count("policy")
        assert nbf.fetch_article_body(URL) is None
        assert _count("http") - before_http == 1
        assert _count("policy") - before_policy == 0


class TestSubclassOrdering:
    """Each branch is a subclass of the one after it. Get the order wrong and
    the counter reports the opposite of what happened, with nothing raised."""

    def test_a_timeout_is_a_timeout_and_not_a_generic_error(self, monkeypatch):
        # TimeoutError IS an OSError. A broad `except OSError` first would
        # label every timeout "error".
        def slow(*_a, **_k):
            raise TimeoutError("Article time budget exhausted")

        assert _run(monkeypatch, slow, "timeout") == 1

    def test_a_timeout_does_not_land_in_error(self, monkeypatch):
        def slow(*_a, **_k):
            raise TimeoutError("Article time budget exhausted")

        assert _run(monkeypatch, slow, "error") == 0

    def test_a_policy_error_is_still_a_ValueError_for_old_callers(self):
        # Subclassing keeps every pre-existing `except ValueError` working.
        assert issubclass(ArticlePolicyError, ValueError)

    def test_a_transport_error_counts_as_error(self, monkeypatch):
        def broken(*_a, **_k):
            raise HTTPError("connection reset")

        assert _run(monkeypatch, broken, "error") == 1


class TestTheTwoWaysWeGiveUpWithoutAsking:
    """`blocked or not acquire()` collapsed these into one silent None."""

    def test_an_open_circuit_breaker_counts_as_breaker(self, monkeypatch):
        nbf._clear_caches_for_tests()
        monkeypatch.setattr(nbf, "_host_blocked", lambda _h: True)
        before = _count("breaker")
        assert nbf.fetch_article_body(URL) is None
        assert _count("breaker") - before == 1

    def test_our_own_concurrency_ceiling_counts_as_saturated(self, monkeypatch):
        nbf._clear_caches_for_tests()
        monkeypatch.setattr(nbf, "_host_blocked", lambda _h: False)
        monkeypatch.setattr(nbf._FETCH_SLOTS, "acquire", lambda blocking=True: False)
        before = _count("saturated")
        assert nbf.fetch_article_body(URL) is None
        assert _count("saturated") - before == 1

    def test_saturation_is_not_reported_as_the_hosts_fault(self, monkeypatch):
        nbf._clear_caches_for_tests()
        monkeypatch.setattr(nbf, "_host_blocked", lambda _h: False)
        monkeypatch.setattr(nbf._FETCH_SLOTS, "acquire", lambda blocking=True: False)
        before = _count("http") + _count("error") + _count("policy")
        nbf.fetch_article_body(URL)
        assert _count("http") + _count("error") + _count("policy") == before


class TestSuccess:
    def test_a_body_counts_as_ok(self, monkeypatch):
        nbf._clear_caches_for_tests()
        monkeypatch.setattr(nbf, "fetch_public_text", lambda *a, **k: "<p>Hello world</p>")
        before = _count("ok")
        assert nbf.fetch_article_body(URL)
        assert _count("ok") - before == 1

    def test_an_empty_body_is_distinguished_from_a_real_one(self, monkeypatch):
        # A 200 that extracts to nothing is not a fetch failure and must not
        # be counted as one, or the error rate reads high while nothing broke.
        nbf._clear_caches_for_tests()
        monkeypatch.setattr(nbf, "fetch_public_text", lambda *a, **k: "<script>x</script>")
        before_empty, before_ok = _count("empty"), _count("ok")
        assert nbf.fetch_article_body(URL) is None
        assert _count("empty") - before_empty == 1
        assert _count("ok") - before_ok == 0

    def test_a_second_call_is_served_from_cache(self, monkeypatch):
        nbf._clear_caches_for_tests()
        monkeypatch.setattr(nbf, "fetch_public_text", lambda *a, **k: "<p>Hello world</p>")
        nbf.fetch_article_body(URL)
        before = _count("cached")
        nbf.fetch_article_body(URL)
        assert _count("cached") - before == 1
