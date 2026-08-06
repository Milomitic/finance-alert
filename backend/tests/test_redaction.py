"""`scrub_secrets` — the guard on credentials reaching log lines.

The first test is the incident verbatim: the exact string `requests` produced,
which put a live Finnhub key into Loki 1,061 times in 24 hours.
"""
import pytest

from app.core.redaction import REDACTED, scrub_secrets

FAKE_KEY = "d00fake0key0000000000000000000000000000f"


class TestTheIncident:
    def test_redacts_the_finnhub_error_that_leaked(self):
        """Verbatim shape of str(requests.HTTPError) for the failing call."""
        line = (
            "[finnhub] earnings calendar fetch failed: 403 Client Error: Forbidden "
            f"for url: https://finnhub.io/api/v1/calendar/earnings?from=2021-08-02"
            f"&to=2026-12-03&token={FAKE_KEY}&symbol=TEN.MI"
        )
        out = scrub_secrets(line)
        assert FAKE_KEY not in out
        assert REDACTED in out

    def test_the_line_stays_diagnosable(self):
        """Redaction that eats the whole URL would trade one problem for
        another — the reason the call failed is the point of the log line."""
        line = (
            "403 Client Error: Forbidden for url: "
            f"https://finnhub.io/api/v1/calendar/earnings?from=2021-08-02&token={FAKE_KEY}"
            "&symbol=TEN.MI"
        )
        out = scrub_secrets(line)
        assert "403 Client Error: Forbidden" in out
        assert "finnhub.io/api/v1/calendar/earnings" in out
        assert "symbol=TEN.MI" in out       # the value that explains the 403
        assert "from=2021-08-02" in out


class TestParameterNames:
    @pytest.mark.parametrize(
        "name", ["token", "api_key", "api-key", "apikey", "api_token", "access_token",
                 "secret", "password", "TOKEN", "ApiKey"],
    )
    def test_covers_the_names_upstreams_actually_use(self, name):
        out = scrub_secrets(f"https://x.test/v1/thing?a=1&{name}={FAKE_KEY}&b=2")
        assert FAKE_KEY not in out
        assert "a=1" in out and "b=2" in out

    def test_covers_the_json_body_form(self):
        # Marketaux echoes the token back inside its JSON error body.
        out = scrub_secrets(f'{{"error": "bad", "api_token": "{FAKE_KEY}"}}')
        assert FAKE_KEY not in out

    def test_leaves_innocent_fields_alone(self):
        line = "https://x.test/v1/thing?symbol=AAPL&from=2026-01-01&limit=50"
        assert scrub_secrets(line) == line


class TestDoesNotRaise:
    """This runs inside exception handlers. Raising here would replace a
    logged warning with an unhandled error in the failure path."""

    @pytest.mark.parametrize("value", ["", None])
    def test_empty_input(self, value):
        assert scrub_secrets(value) == value

    def test_no_secret_present(self):
        assert scrub_secrets("plain message") == "plain message"

    def test_secret_at_end_of_string(self):
        out = scrub_secrets(f"https://x.test/v1?token={FAKE_KEY}")
        assert FAKE_KEY not in out
