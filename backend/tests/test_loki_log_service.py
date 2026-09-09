"""Infra logs: an empty answer and no answer must not look alike.

Loki is a network dependency, unlike the app's own log buffer, so it adds a
failure the health page never had to represent: the query did not happen. If
that collapses into an empty list the panel renders a calm, empty component
while the log pipeline is down — a broken monitor reporting good news, which is
the shape this codebase keeps finding and removing.

The other invariant is the source table. `query()` takes a KEY, and a key it
does not know is refused before any request is built. Were it to accept LogQL
the endpoint would be an authenticated proxy for reading every namespace's
output, which includes whatever any component happens to print.
"""

import json
import urllib.parse

import pytest

from app.services import loki_log_service as loki


def _envelope(streams):
    return {"status": "success", "data": {"resultType": "streams", "result": streams}}


def _stream(labels, values):
    return {"stream": labels, "values": values}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Default to Loki being unreachable; each test opts into an answer."""
    monkeypatch.setattr(loki, "_fetch", lambda *a, **k: None)


def _answer(monkeypatch, payload):
    monkeypatch.setattr(loki, "_fetch", lambda *a, **k: payload)


class TestUnreachableIsNotEmpty:
    def test_a_failed_query_returns_None(self, monkeypatch):
        assert loki.query("argocd") is None

    def test_an_answered_query_with_nothing_in_it_returns_an_EMPTY_LIST(
        self, monkeypatch
    ):
        # The distinction the panel depends on. Same shape on screen, opposite
        # meanings: "the component was quiet" versus "I could not look".
        _answer(monkeypatch, _envelope([]))

        result = loki.query("argocd")

        assert result == []
        assert result is not None

    def test_a_malformed_envelope_is_unreachable_not_empty(self, monkeypatch):
        # A 200 carrying something unexpected is still "no answer". Reading it
        # as zero records would be inventing a fact from a parse failure.
        _answer(monkeypatch, {"status": "error", "data": {}})
        assert loki.query("argocd") is None

        _answer(monkeypatch, {"status": "success", "data": "non un oggetto"})
        assert loki.query("argocd") is None


class TestTheSourceTableIsClosed:
    def test_an_unknown_key_is_refused(self, monkeypatch):
        _answer(monkeypatch, _envelope([]))
        assert loki.query("non-esiste") is None

    def test_a_logql_expression_is_not_a_key(self, monkeypatch):
        # The injection shape: if a selector were accepted here it would read
        # every namespace. It is simply not a key, so it never reaches _fetch.
        _answer(monkeypatch, _envelope([]))
        assert loki.query('{namespace="kube-system"}') is None

    def test_every_offered_source_is_queryable(self, monkeypatch):
        # The picker and the query must not drift apart: anything the UI can
        # offer has to be something the backend accepts.
        _answer(monkeypatch, _envelope([]))
        for option in loki.sources_payload():
            assert loki.query(option["key"]) == [], option["key"]

    def test_no_selector_is_built_from_the_request(self):
        # Every selector is a literal in the module.
        for src in loki.SOURCES.values():
            assert src.selector.startswith("{") and src.selector.endswith("}")


class TestLevelParsing:
    @pytest.mark.parametrize(
        "line,expected",
        [
            ('{"level":"error","msg":"backup fallito"}', "ERROR"),   # CNPG, JSON
            ("time=... level=warning msg=retry", "WARNING"),          # logfmt
            ("2026-09-09 [ERROR] qualcosa", "ERROR"),                 # bracketed
            ("level=fatal terminating", "CRITICAL"),                  # mappato
            ("level=warn deprecato", "WARNING"),                      # abbreviato
        ],
    )
    def test_it_recognises_the_formats_these_components_use(self, line, expected):
        assert loki._parse_level(line) == expected

    def test_an_unrecognisable_line_is_INFO(self):
        # Documented fallback. It is exactly why the UI must not open an infra
        # source filtered at WARNING: an unclassified error would be hidden.
        assert loki._parse_level("connesso a 10.42.0.1:5432") == "INFO"

    def test_a_structured_field_beats_the_word_in_the_message(self):
        # The bare-word pattern is last on purpose. Without that ordering, a
        # line reporting a recovered error would be classified as one.
        assert loki._parse_level('level=info msg="ERROR risolto"') == "INFO"


class TestRecords:
    def test_it_maps_a_loki_entry_into_the_app_log_shape(self, monkeypatch):
        _answer(monkeypatch, _envelope([
            _stream(
                {"pod": "argocd-server-1", "container": "argocd-server"},
                [["1757000000000000000", "level=error msg=sync fallito"]],
            )
        ]))

        rows = loki.query("argocd")

        assert len(rows) == 1
        r = rows[0]
        assert r["level"] == "ERROR"
        assert r["module"] == "argocd-server-1"
        assert r["message"] == "level=error msg=sync fallito"
        assert r["ts"] == pytest.approx(1757000000.0)
        # The UI reuses the app's log row, so every key it reads must exist.
        assert set(r) >= {"ts", "level", "module", "function", "line", "message"}

    def test_newest_first_across_several_streams(self, monkeypatch):
        _answer(monkeypatch, _envelope([
            _stream({"pod": "a"}, [["1757000000000000000", "vecchio"]]),
            _stream({"pod": "b"}, [["1757000900000000000", "nuovo"]]),
        ]))

        rows = loki.query("argocd")

        assert [r["message"] for r in rows] == ["nuovo", "vecchio"]

    def test_a_level_floor_drops_the_quieter_lines(self, monkeypatch):
        _answer(monkeypatch, _envelope([
            _stream({"pod": "a"}, [
                ["1757000000000000000", "level=info avviato"],
                ["1757000001000000000", "level=error caduto"],
            ])
        ]))

        rows = loki.query("argocd", level="WARNING")

        assert [r["level"] for r in rows] == ["ERROR"]

    def test_a_broken_entry_is_skipped_not_fatal(self, monkeypatch):
        # One malformed row must not cost the whole panel.
        _answer(monkeypatch, _envelope([
            _stream({"pod": "a"}, [
                ["non-un-numero", "rotto"],
                ["1757000000000000000", "buono"],
            ])
        ]))

        rows = loki.query("argocd")

        assert [r["message"] for r in rows] == ["buono"]

    def test_the_limit_is_honoured_after_merging_streams(self, monkeypatch):
        _answer(monkeypatch, _envelope([
            _stream({"pod": "a"}, [[str(1757000000000000000 + i), f"r{i}"] for i in range(5)]),
            _stream({"pod": "b"}, [[str(1757000000000000000 + i), f"s{i}"] for i in range(5)]),
        ]))

        assert len(loki.query("argocd", limit=3)) == 3


class TestTheQueryItself:
    def test_it_asks_for_the_window_it_was_given(self, monkeypatch):
        seen = {}

        def spy(selector, *, limit, minutes):
            seen.update(selector=selector, limit=limit, minutes=minutes)
            return _envelope([])

        monkeypatch.setattr(loki, "_fetch", spy)
        loki.query("postgres", limit=42, minutes=15)

        assert seen["limit"] == 42
        assert seen["minutes"] == 15
        assert seen["selector"] == loki.SOURCES["postgres"].selector

    def test_the_url_is_a_range_query_with_nanosecond_bounds(self, monkeypatch):
        captured = {}

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps(_envelope([])).encode()

        def fake_urlopen(url, timeout=None):
            captured["url"] = url
            return _Resp()

        monkeypatch.undo()  # drop the _no_network stub so the real _fetch runs
        monkeypatch.setattr(loki.urllib.request, "urlopen", fake_urlopen)

        loki.query("grafana", minutes=30)

        url = captured["url"]
        assert "/loki/api/v1/query_range?" in url
        assert "direction=backward" in url

        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        start, end = int(qs["start"][0]), int(qs["end"][0])
        # NANOSECONDS. Passing seconds here returns an empty result rather than
        # an error, so the panel would read "component quiet" forever.
        assert len(qs["start"][0]) == 19, qs["start"][0]
        assert (end - start) == 30 * 60 * 1_000_000_000
        assert qs["query"] == [loki.SOURCES["grafana"].selector]
