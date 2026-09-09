"""The per-handler latency histogram has to reach past one second.

Its default buckets are `(0.1, 0.5, 1)`. With those, `histogram_quantile` on
anything slower returns 1.000 — the highest finite edge — and it looks like a
measurement. Measured against live Prometheus on 2026-09-09, NINE handlers all
reported a p95 of exactly 1.000 while their true means were 4.6s
(/api/stocks/quotes), 2.6s (multi-tf-kpis) and 2.1s (fundamentals). Every one
of them sat above the last boundary the histogram could see.

The library's other histogram, `http_request_duration_highr_seconds`, does have
fine buckets but carries no handler label, so it can say the app is slow and
never which endpoint. That split is the helper's design; what it leaves behind
is a per-endpoint blind spot above one second, which is the range this app
lives in — quotes depend on an upstream measured at 43-50s under rate limiting
(see CLAUDE.md).

A latency number that cannot exceed its own ceiling is the same defect as a
wrong one, so the ceiling is pinned here.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def metrics_text() -> str:
    client = TestClient(app)
    client.get("/api/health")
    return client.get("/metrics").text


def _edges(text: str, metric: str) -> list[float]:
    out = set()
    for line in text.splitlines():
        if line.startswith(f"{metric}_bucket") and 'le="' in line:
            raw = line.split('le="', 1)[1].split('"', 1)[0]
            out.add(float(raw))
    return sorted(out)


class TestThePerHandlerHistogram:
    def test_it_can_measure_beyond_one_second(self, metrics_text):
        edges = _edges(metrics_text, "http_request_duration_seconds")
        finite = [e for e in edges if e != float("inf")]

        assert max(finite) > 1.0, (
            "the per-handler histogram tops out at its old ceiling; every p95 "
            f"above it will silently report {max(finite)}"
        )

    def test_it_reaches_the_upstreams_documented_worst_case(self, metrics_text):
        # yfinance has been measured at 43-50s under rate limiting. Without a
        # boundary past that, the incident is indistinguishable from any other
        # slow request.
        edges = _edges(metrics_text, "http_request_duration_seconds")
        assert max(e for e in edges if e != float("inf")) >= 60.0

    def test_it_still_resolves_fast_requests(self, metrics_text):
        # Widening must not cost the low end: most endpoints answer in tens of
        # milliseconds and a histogram starting at 1s would flatten them all
        # into one bucket.
        edges = _edges(metrics_text, "http_request_duration_seconds")
        assert min(edges) <= 0.1

    def test_it_still_carries_the_handler_label(self, metrics_text):
        # The whole reason for touching the low-resolution metric rather than
        # the high-resolution one: this is the only latency series that can say
        # WHICH endpoint was slow.
        assert 'http_request_duration_seconds_bucket{handler="' in metrics_text


class TestTheHighResolutionHistogramIsUntouched:
    def test_it_is_still_exported(self, metrics_text):
        # It answers a different question — how the app behaves overall — and
        # nothing here should have cost it.
        assert "http_request_duration_highr_seconds_bucket" in metrics_text
