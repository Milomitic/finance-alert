"""Single owner of "never let a credential reach a log line".

WHY THIS EXISTS, with the incident that produced it
───────────────────────────────────────────────────
`finnhub_earnings_service` passes its API key as a query parameter, then logs
failures as `logger.warning(f"... failed: {exc}")`. `requests` builds its
HTTPError message as "403 Client Error: Forbidden for url: <the full URL>",
and the full URL carries `&token=<the key>`. So every failed call wrote the
live credential into the log stream — measured at **1,061 lines in 24 hours**,
shipped to Loki and readable by anyone with a Grafana Viewer token.

The failure mode is the one this repo keeps meeting: it self-reports as
success. Nothing errors, nothing is slow, the log line looks like a normal
upstream warning. It is only visible if you read the URL to its end.

`marketaux_news_service` had already been fixed for the same class of bug with
its own private `_scrub_token`. That is exactly why this module is shared: a
per-service scrubber protects the one service someone happened to audit, and
the next integration re-introduces the leak. Anything that logs an exception
from an authenticated HTTP call goes through `scrub_secrets`.

Redaction is not a substitute for rotating a key that has already been
written to a log.
"""
from __future__ import annotations

import re

# Credential-looking names, matched case-insensitively.
_SECRET_NAMES = r"(?:api[-_]?token|api[-_]?key|apikey|access[-_]?token|token|secret|password|passwd|pwd)"

# 1) Query-string form: ...?token=abc&symbol=X  /  ...&api_key=abc
#    The value stops at & or whitespace or a quote, so the rest of the URL —
#    which is the useful part of the log line — survives.
_QUERY_SECRET = re.compile(rf"([?&]{_SECRET_NAMES}=)[^&\s\"'<>]+", re.IGNORECASE)

# 2) Key/value form as it appears in JSON error bodies and reprs:
#    "api_token": "abc" / api_key=abc / 'token': 'abc'
_KV_SECRET = re.compile(
    rf"({_SECRET_NAMES}[\"']?\s*[:=]\s*[\"']?)[^\"'&\s,}}\]]+", re.IGNORECASE
)

REDACTED = "[REDACTED]"


def scrub_secrets(text: str) -> str:
    """Return `text` with any credential-looking value replaced by [REDACTED].

    Deliberately over-broad on the NAME and conservative on the VALUE: a
    false positive costs one unreadable field in a log line, a false negative
    costs a live credential in a log aggregator. The surrounding URL, status
    code and endpoint all survive, so the line stays diagnosable.
    """
    if not text:
        return text
    return _KV_SECRET.sub(rf"\1{REDACTED}", _QUERY_SECRET.sub(rf"\1{REDACTED}", text))
