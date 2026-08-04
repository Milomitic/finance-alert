"""The news fallback for non-US listings.

Offline by construction. The repo has already been bitten once by tests that
reached real upstreams (B4-2), and a network-dependent test for a FALLBACK is
doubly wrong: it fails when the thing it is testing is needed most.
"""
import pytest

from app.services import yahoo_rss_news_service as svc

_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>AstraZeneca beats estimates</title>
    <link>https://example.com/a</link>
    <source>Reuters</source>
    <pubDate>Tue, 04 Aug 2026 09:30:05 GMT</pubDate>
  </item>
  <item>
    <title>No date here</title>
    <link>https://example.com/b</link>
  </item>
  <item>
    <title>Missing link is dropped</title>
  </item>
</channel></rss>"""


@pytest.fixture(autouse=True)
def _clean():
    svc.clear_cache()
    yield
    svc.clear_cache()


def test_parses_headlines_and_normalises_the_date(monkeypatch):
    monkeypatch.setattr(svc, "_get", lambda t: _FEED)
    items = svc.fetch_company_news("AZN.L")
    assert [i.title for i in items] == [
        "AstraZeneca beats estimates",
        "No date here",
    ], "an item without a link is unusable and must be dropped"
    assert items[0].published_at == "2026-08-04T09:30:05+00:00"
    assert items[0].source == "Reuters"


def test_a_missing_date_is_none_not_a_guess(monkeypatch):
    """The list is read as chronological. A guessed timestamp puts the item in
    the wrong place, which is worse than an absent one sinking to the end."""
    monkeypatch.setattr(svc, "_get", lambda t: _FEED)
    assert svc.fetch_company_news("AZN.L")[1].published_at is None


def test_a_non_xml_body_is_a_failure_not_an_empty_result(monkeypatch):
    """Precisely the bug this whole chain was built to escape: yfinance takes a
    consent page for 'no news' and caches it as success."""
    monkeypatch.setattr(svc, "_get", lambda t: "<html>consent wall</html>")
    recorded: list[tuple] = []
    from app.services import data_source_metrics
    monkeypatch.setattr(
        data_source_metrics, "record_failure",
        lambda *a, **k: recorded.append((a, k)),
    )
    assert svc.fetch_company_news("AZN.L") == []
    assert recorded, "an unparseable body must be recorded as a failure"


def test_an_empty_feed_is_not_counted_as_success(monkeypatch):
    """A 200 carrying no items means the ticker is uncovered — the chain above
    needs that distinction to decide whether to try the next stage."""
    monkeypatch.setattr(
        svc, "_get",
        lambda t: '<?xml version="1.0"?><rss version="2.0"><channel/></rss>',
    )
    from app.services import data_source_metrics
    ok: list = []
    monkeypatch.setattr(data_source_metrics, "record_success", lambda *a, **k: ok.append(a))
    monkeypatch.setattr(data_source_metrics, "record_failure", lambda *a, **k: None)
    assert svc.fetch_company_news("AZN.L") == []
    assert not ok, "an empty feed must never be recorded as a success"


def test_it_never_raises_because_it_is_the_last_stage(monkeypatch):
    """Nothing catches after this one; raising here would take out the whole
    news response rather than degrading it."""
    def boom(_t):
        raise RuntimeError("network on fire")
    monkeypatch.setattr(svc, "_get", boom)
    assert svc.fetch_company_news("AZN.L") == []


def test_the_cache_spares_the_upstream_a_second_call(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(svc, "_get", lambda t: (calls.append(t), _FEED)[1])
    svc.fetch_company_news("AZN.L")
    svc.fetch_company_news("AZN.L")
    assert len(calls) == 1


def test_the_rate_ceiling_holds(monkeypatch):
    """No published quota is not the same as no limit — the quote endpoint
    taught that at 43-50s per request under throttling."""
    monkeypatch.setattr(svc, "_get", lambda t: _FEED)
    for i in range(svc._RATE_CEILING_PER_MIN + 5):
        svc.fetch_company_news(f"T{i}.L")
    assert svc._rate_limited() is True
