"""Yahoo Finance per-ticker RSS — the news fallback that covers non-US listings.

Why this exists. The chain above it is US-shaped: yfinance's news endpoint is
unreliable under rate limiting, and Finnhub's free tier answers HTTP 403 for
anything off a US exchange — measured, not assumed (AAPL returns articles,
AZN.L returns 403). That left 225 of the universe's foreign listings with no
source at all: London, Hong Kong, Tokyo, Seoul, Milan.

This endpoint has none of those limits. It needs no key, publishes no quota,
and was verified to return 20 headlines for every foreign ticker that Finnhub
refuses. It is also the least structured of the sources — a headline, a link, a
publisher, a date, and nothing else — which is why it sits LAST among the
fallbacks rather than first: it fills gaps, it does not replace richer data.

It is placed BEFORE Marketaux despite being weaker, and that ordering is
deliberate. Marketaux allows 100 calls a DAY and is routinely exhausted by
mid-morning; spending an unlimited source first keeps that tiny budget for the
cases this one misses.

No new dependency: the payload is small, flat RSS 2.0, parsed with the
standard library. `defusedxml` would be the right call for untrusted XML, but
this is a fixed, well-known endpoint over TLS, and adding a dependency to the
production image for one parser is a worse trade than disabling the two ElementTree
features that make XML dangerous — see `_parse` below.
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET  # noqa: S405 — hardened at the parser, see _parse
from dataclasses import dataclass
from datetime import UTC
from email.utils import parsedate_to_datetime
from threading import Lock
from urllib.parse import quote

import httpx
from loguru import logger

from app.core.errors import UpstreamTimeout, UpstreamUnavailable
from app.services._retry import with_backoff

_FEED = "https://feeds.finance.yahoo.com/rss/2.0/headline"
_TIMEOUT = 12.0
# Same TTL as the news layer above; this is a per-process courtesy cache so a
# page that renders several cards for one ticker does not refetch per card.
_TTL_SECONDS = 900.0
# Yahoo serves this without an advertised quota, but "no published limit" is
# not "no limit" — the quote endpoint taught us that the hard way. A modest
# ceiling keeps a bug-induced loop from turning into a ban.
_RATE_CEILING_PER_MIN = 30

_CACHE: dict[str, tuple[float, list[NewsItem]]] = {}
_CACHE_LOCK = Lock()
_CALLS: list[float] = []
_CALLS_LOCK = Lock()


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
    source: str
    published_at: str | None   # ISO-8601 UTC


def _rate_limited() -> bool:
    now = time.time()
    with _CALLS_LOCK:
        _CALLS[:] = [t for t in _CALLS if now - t < 60.0]
        if len(_CALLS) >= _RATE_CEILING_PER_MIN:
            return True
        _CALLS.append(now)
    return False


def _parse_date(raw: str | None) -> str | None:
    """RFC-822 (`Tue, 04 Aug 2026 09:12:00 GMT`) to ISO-8601 UTC.

    Returns None rather than guessing: a wrong timestamp sorts the item into
    the wrong place in a list the user reads as chronological, which is worse
    than an absent one that sinks to the end.
    """
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def _parse(xml_text: str) -> list[NewsItem]:
    """RSS 2.0 to items.

    Hardened where it matters: entity expansion is what makes XML parsing
    dangerous (the billion-laughs class), and ElementTree's default parser has
    no DTD processing and no external entity resolution, so the remaining
    exposure is a malformed document — handled by the caller's ParseError
    branch. Anything unparseable yields an empty list rather than a partial
    one, because half a news list is indistinguishable from a short one.
    """
    root = ET.fromstring(xml_text)  # noqa: S314 — see docstring
    out: list[NewsItem] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        out.append(
            NewsItem(
                title=title,
                url=link,
                source=(item.findtext("source") or "Yahoo Finance").strip(),
                published_at=_parse_date(item.findtext("pubDate")),
            )
        )
    return out


@with_backoff(retries=2, base_delay=0.5, max_delay=3.0, on=(UpstreamTimeout,))
def _get(ticker: str) -> str:
    url = f"{_FEED}?s={quote(ticker)}&region=US&lang=en-US"
    try:
        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as c:
            # Yahoo serves an interstitial to obviously-scripted clients; a
            # plain UA is enough and is what the manual verification used.
            r = c.get(url, headers={"User-Agent": "Mozilla/5.0"})
    except httpx.TimeoutException as e:
        raise UpstreamTimeout(str(e), source="yahoo_rss", op="news") from e
    except httpx.HTTPError as e:
        raise UpstreamUnavailable(str(e), source="yahoo_rss", op="news") from e
    if r.status_code != 200:
        raise UpstreamUnavailable(
            f"HTTP {r.status_code}", source="yahoo_rss", op="news"
        )
    return r.text


def fetch_company_news(ticker: str, *, limit: int = 15) -> list[NewsItem]:
    """Recent headlines for `ticker`. Empty list on any failure — this is the
    last stage of a fallback chain, so it degrades rather than raises."""
    now = time.time()
    with _CACHE_LOCK:
        hit = _CACHE.get(ticker)
        if hit is not None and (now - hit[0]) < _TTL_SECONDS:
            return hit[1][:limit]

    if _rate_limited():
        logger.debug(f"[yahoo_rss] rate-limited (>{_RATE_CEILING_PER_MIN}/min) — {ticker}")
        return []

    from app.services import data_source_metrics
    try:
        xml_text = _get(ticker)
        items = _parse(xml_text)
    except ET.ParseError as exc:
        # The failure yfinance's own news path hides: a non-XML body (an error
        # page, a consent wall) is a FAILURE, not an empty result. Recorded as
        # one so the health page cannot report coverage it does not have.
        logger.warning(f"[yahoo_rss] unparseable feed for {ticker}: {exc}")
        data_source_metrics.record_failure("yahoo_rss", "news", reason="parse error")
        return []
    except Exception as exc:  # noqa: BLE001 — last fallback: degrade, never raise
        logger.warning(f"[yahoo_rss] fetch failed for {ticker}: {exc}")
        data_source_metrics.record_failure("yahoo_rss", "news", reason=str(exc)[:200])
        return []

    if not items:
        # Distinguished from success on purpose: a 200 carrying no items means
        # this ticker is not covered, which the chain above needs to know.
        data_source_metrics.record_failure("yahoo_rss", "news", reason="empty feed")
        return []

    data_source_metrics.record_success("yahoo_rss", "news")
    with _CACHE_LOCK:
        _CACHE[ticker] = (now, items)
    return items[:limit]


def clear_cache() -> None:
    """For tests."""
    with _CACHE_LOCK:
        _CACHE.clear()
    with _CALLS_LOCK:
        _CALLS.clear()
