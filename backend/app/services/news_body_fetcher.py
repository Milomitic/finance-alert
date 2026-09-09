"""Last-resort article-body fetcher for the analyst-action extractor.

Why this exists
───────────────
yfinance's news payload gives us a `title` and a short `summary`
(typically 100–500 chars). For analyst-flavored articles that is
often enough to extract firm + action ("Wedbush raises Apple
target") but NOT the price target itself ("…to a new high"), which
tends to live in paragraph 2-3 of the actual article body. When the
title and summary aren't sufficient we'd previously just give up and
ship the row with `current_price_target=None`.

This module is the third stage: given the article URL, do a
best-effort HTTP fetch + HTML-to-text extraction so the regex
extractor can search the full body for the missing target.

Why not bring in a real library
──────────────────────────────
Production tools use `readability-lxml`, `newspaper3k`, `trafilatura`
to do extraction well. They each add 5-15 MB to the wheel size, want
non-trivial dependencies (lxml, NLTK, cssselect), and produce
marginal accuracy gains for our narrow use case: we don't need
clean paragraph segmentation, just enough text to grep for a $-
prefixed number near a firm name. A 50-line BeautifulSoup pass
gets us 80% of the value at 0% of the dependency cost.

Quota / quality guards
──────────────────────
- 5s network budget per URL (OS DNS resolution uses its own timeout).
- 15-minute circuit breaker after 3 consecutive failures on a domain
  (paywall / anti-bot guard) to avoid wasting budget hammering hosts
  that won't give us anything.
- Per-URL cache (24h TTL): articles don't change post-publication,
  caching avoids re-fetching when the user revisits the same stock.
- Skip-list for known paywalled / JS-heavy domains where the body
  text is always replaced by a "subscribe" wall.
- 200 KB response cap — we want excerpts, not whole pages.

Failure mode
────────────
Every error returns `None` silently. The extractor falls back to
title+summary as it did before; no exception propagates to the
caller. This is a STRICTLY OPTIONAL enrichment.
"""
from __future__ import annotations

import datetime as _dt
import re
import threading
from collections import OrderedDict
from html import unescape
from urllib.parse import urlparse

from loguru import logger
from urllib3.exceptions import HTTPError

from app.core.app_metrics import ARTICLE_FETCH
from app.core.public_http import ArticlePolicyError, fetch_public_text

_TIMEOUT = 5.0
_MAX_BYTES = 200 * 1024  # 200 KB hard cap on body length
_USER_AGENT = (
    "Mozilla/5.0 (compatible; FinanceAlert/0.1; +https://finance-alert.local)"
)

# Hosts whose response is mostly a paywall / JS shell — body fetch is
# a waste of time. Add more here when we observe junk in the cache.
_PAYWALL_HOSTS: set[str] = {
    "www.wsj.com",
    "wsj.com",
    "www.bloomberg.com",
    "bloomberg.com",
    "www.ft.com",
    "ft.com",
    "www.nytimes.com",
    "nytimes.com",
    "www.barrons.com",
    "barrons.com",
    "www.reuters.com",  # JS-rendered article body
    "reuters.com",
    "seekingalpha.com",  # behind login
    "www.seekingalpha.com",
}

# Per-host failure counter — after N consecutive failures we stop
# trying that host for a fixed window. Cheaper than per-URL backoff
# and catches whole-domain blocks (cloudflare challenge, geo-fence).
_HOST_FAIL_COUNT: dict[str, int] = {}
_HOST_BLOCKED_UNTIL: dict[str, _dt.datetime] = {}
_HOST_FAIL_THRESHOLD = 3
_HOST_BLOCK_DURATION = _dt.timedelta(minutes=15)

# Per-URL response cache. Articles are immutable after publication,
# so a 24h cache is comfortable. Explicit LRU capacity also bounds dead URLs,
# including negative cache entries, across a long-lived cloud process.
_BODY_CACHE: OrderedDict[str, tuple[_dt.datetime, str | None]] = OrderedDict()
_MAX_CACHE_ENTRIES = 128
_MAX_TRACKED_HOSTS = 128
_FETCH_SLOTS = threading.BoundedSemaphore(4)
_BODY_TTL = _dt.timedelta(hours=24)
_CACHE_LOCK = threading.Lock()


def _cache_body(url: str, body: str | None) -> None:
    now = _dt.datetime.now(_dt.UTC)
    with _CACHE_LOCK:
        expired = [key for key, (ts, _) in _BODY_CACHE.items() if now - ts >= _BODY_TTL]
        for key in expired:
            del _BODY_CACHE[key]
        _BODY_CACHE[url] = (now, body)
        _BODY_CACHE.move_to_end(url)
        while len(_BODY_CACHE) > _MAX_CACHE_ENTRIES:
            _BODY_CACHE.popitem(last=False)


def _host_blocked(host: str) -> bool:
    """Per-host short-circuit: once a host has failed N times in a row
    we suspend fetches for `_HOST_BLOCK_DURATION` minutes. Reset on the
    next clean success."""
    until = _HOST_BLOCKED_UNTIL.get(host)
    if until is None:
        return False
    if until <= _dt.datetime.now(_dt.UTC):
        _HOST_BLOCKED_UNTIL.pop(host, None)
        _HOST_FAIL_COUNT.pop(host, None)
        return False
    return True


def _record_host_failure(host: str) -> None:
    if host not in _HOST_FAIL_COUNT and len(_HOST_FAIL_COUNT) >= _MAX_TRACKED_HOSTS:
        oldest = next(iter(_HOST_FAIL_COUNT))
        _HOST_FAIL_COUNT.pop(oldest, None)
        _HOST_BLOCKED_UNTIL.pop(oldest, None)
    n = _HOST_FAIL_COUNT.get(host, 0) + 1
    _HOST_FAIL_COUNT[host] = n
    if n >= _HOST_FAIL_THRESHOLD:
        _HOST_BLOCKED_UNTIL[host] = (
            _dt.datetime.now(_dt.UTC) + _HOST_BLOCK_DURATION
        )
        logger.debug(
            f"[news_body] host {host} blocked until "
            f"{_HOST_BLOCKED_UNTIL[host].isoformat()} (3 failures in a row)"
        )


def _record_host_success(host: str) -> None:
    _HOST_FAIL_COUNT.pop(host, None)
    _HOST_BLOCKED_UNTIL.pop(host, None)


# Tag-strip regexes. We want to KEEP inline text within paragraphs,
# headings, list items, so we replace those tags with spaces (not
# delete) to preserve word separation. <script> and <style> are
# nuked along with their content because they're noise.
_RE_SCRIPT_STYLE = re.compile(
    r"<(script|style|noscript)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
_RE_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_RE_ANY_TAG = re.compile(r"<[^>]+>")
_RE_WS = re.compile(r"\s+")


def _html_to_text(html: str) -> str:
    """Cheap HTML → plain-text. Not perfect (no paragraph awareness,
    no entity-edge cases beyond `unescape`) but enough for downstream
    regex to find dollar amounts and firm names. Caps the result at
    `_MAX_BYTES` characters so a 5 MB recipe page doesn't blow up the
    extractor's regex evaluation cost."""
    if not html:
        return ""
    s = _RE_SCRIPT_STYLE.sub(" ", html)
    s = _RE_HTML_COMMENT.sub(" ", s)
    s = _RE_ANY_TAG.sub(" ", s)
    s = unescape(s)
    s = _RE_WS.sub(" ", s).strip()
    if len(s) > _MAX_BYTES:
        s = s[:_MAX_BYTES]
    return s


def fetch_article_body(url: str | None) -> str | None:
    """Fetch the article at `url` and return plain-text body, or None
    on any error / paywall / cache miss. Strict 5s timeout, 200 KB
    cap, 24h cache.

    Production callers should treat this as best-effort — the
    extractor must still work when None is returned. Errors are
    logged at DEBUG level (high-volume; INFO would spam), so the
    `finance_alert_article_fetch_total` counter is what makes the
    reason visible in production: every exit below records one."""
    if not url:
        return None
    if len(url) > 4096 or any(ord(c) <= 32 or ord(c) == 127 for c in url):
        ARTICLE_FETCH.labels(outcome="policy").inc()
        return None

    # Cache check first — articles don't mutate post-publication.
    now = _dt.datetime.now(_dt.UTC)
    with _CACHE_LOCK:
        cached = _BODY_CACHE.get(url)
        if cached is not None and (now - cached[0]) < _BODY_TTL:
            _BODY_CACHE.move_to_end(url)
            ARTICLE_FETCH.labels(outcome="cached").inc()
            return cached[1]
        _BODY_CACHE.pop(url, None)

    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
    except ValueError:
        ARTICLE_FETCH.labels(outcome="policy").inc()
        return None
    if not host:
        ARTICLE_FETCH.labels(outcome="policy").inc()
        return None

    # Skip known paywalled domains — fetching is just burning a
    # 5-second timeout for nothing.
    if host in _PAYWALL_HOSTS:
        _cache_body(url, None)
        ARTICLE_FETCH.labels(outcome="paywall_skip").inc()
        return None

    # Per-host circuit breaker. Split from the slot check below because they
    # mean opposite things: "this host keeps failing us" versus "we are at our
    # own concurrency ceiling". Collapsed into one `or` they were the same
    # silent None, which is the confusion this counter exists to end.
    with _CACHE_LOCK:
        blocked = _host_blocked(host)
    if blocked:
        ARTICLE_FETCH.labels(outcome="breaker").inc()
        return None
    if not _FETCH_SLOTS.acquire(blocking=False):
        ARTICLE_FETCH.labels(outcome="saturated").inc()
        return None

    try:
        raw_html = fetch_public_text(
            url, max_bytes=_MAX_BYTES, timeout=_TIMEOUT, user_agent=_USER_AGENT,
        )
        text = _html_to_text(raw_html)
        with _CACHE_LOCK:
            _record_host_success(host)
        _cache_body(url, text or None)
        ARTICLE_FETCH.labels(outcome="ok" if text else "empty").inc()
        return text or None
    except (HTTPError, OSError, ValueError) as exc:
        # ArticlePolicyError before ValueError and TimeoutError before OSError:
        # each is a subclass of the one after it, so the broad name would
        # swallow the specific one and the counter would report the opposite of
        # what happened.
        if isinstance(exc, ArticlePolicyError):
            outcome = "policy"
        elif isinstance(exc, TimeoutError):
            outcome = "timeout"
        elif isinstance(exc, ValueError):
            outcome = "http"
        else:
            outcome = "error"
        ARTICLE_FETCH.labels(outcome=outcome).inc()
        # Exception messages may contain credentials/query strings from URLs.
        logger.debug(f"[news_body] {host} fetch failed: {type(exc).__name__} ({outcome})")
        with _CACHE_LOCK:
            _record_host_failure(host)
        _cache_body(url, None)
        return None
    finally:
        _FETCH_SLOTS.release()


def _clear_caches_for_tests() -> None:
    """Reset all internal state. Tests use this to isolate fetches."""
    with _CACHE_LOCK:
        _BODY_CACHE.clear()
        _HOST_FAIL_COUNT.clear()
        _HOST_BLOCKED_UNTIL.clear()
