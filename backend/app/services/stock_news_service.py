"""yfinance news wrapper with in-memory TTL cache."""
from datetime import UTC, datetime, timedelta
from typing import Any

from loguru import logger

NEWS_TTL = timedelta(hours=1)
_CACHE: dict[str, tuple[datetime, list[dict[str, Any]]]] = {}


def _normalize_yf_item(raw: dict) -> dict[str, Any] | None:
    """yfinance.Ticker.news returns dicts of varying shape across versions.
    Normalize to {title, link, publisher, published_at: ISO8601 str | None}.

    Two known shapes:
    - NEW (yfinance ≥ ~0.2.40, post mid-2024): nested under `content` →
        {id, content: {title, pubDate, canonicalUrl:{url}, clickThroughUrl:{url},
                       provider:{displayName}, ...}}
    - OLD (legacy flat): {title, link, publisher, providerPublishTime, ...}
    """
    # Unwrap the new nested shape if present, otherwise treat raw as flat.
    inner = raw.get("content") if isinstance(raw.get("content"), dict) else raw

    title = inner.get("title")

    # Link: prefer canonicalUrl (publisher's own page) over clickThroughUrl
    # (Yahoo's wrapper). Fall back to legacy `link`/`url` flat keys.
    link: str | None = None
    for key in ("canonicalUrl", "clickThroughUrl"):
        v = inner.get(key)
        if isinstance(v, dict) and v.get("url"):
            link = v["url"]
            break
    if not link:
        link = inner.get("link") or inner.get("url")

    # Publisher: new shape nests it under provider.displayName; old shape was flat.
    publisher: str | None = None
    prov = inner.get("provider")
    if isinstance(prov, dict):
        publisher = prov.get("displayName") or prov.get("sourceId")
    publisher = publisher or inner.get("publisher") or inner.get("source")

    # published_at: new shape gives an ISO8601 string already; old shape gave a unix ts.
    published_at: str | None = None
    pub = inner.get("pubDate") or inner.get("displayTime")
    if isinstance(pub, str) and pub:
        published_at = pub
    else:
        ts = inner.get("providerPublishTime") or inner.get("publish_time")
        if isinstance(ts, (int, float)):
            published_at = datetime.fromtimestamp(ts, tz=UTC).isoformat()

    if not title or not link:
        return None
    return {
        "title": str(title),
        "link": str(link),
        "publisher": str(publisher) if publisher else "Unknown",
        "published_at": published_at,
    }


def get_news(ticker: str, limit: int = 5) -> list[dict[str, Any]]:
    """Fetch news for a ticker. Cached for 1h. Returns [] on any error.

    Items are sorted **descending** by published_at (most recent first) so
    the UI can render them in chronological order without doing a sort pass.
    Items missing a published_at are pushed to the end (least useful).
    """
    now = datetime.now(UTC)
    cached = _CACHE.get(ticker)
    if cached and (now - cached[0]) < NEWS_TTL:
        return cached[1][:limit]
    try:
        import yfinance as yf
        raw_items = yf.Ticker(ticker).news or []
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[news] yfinance fetch failed for {ticker}: {exc}")
        # Cache empty result to avoid hammering on failure
        _CACHE[ticker] = (now, [])
        return []
    normalized = [n for raw in raw_items if (n := _normalize_yf_item(raw))]
    # ISO 8601 strings (with the trailing Z that yfinance emits) sort
    # lexicographically the same as chronologically — no parsing needed.
    # Sentinel "" pushes items missing pubDate to the end of the list.
    normalized.sort(key=lambda n: n.get("published_at") or "", reverse=True)
    _CACHE[ticker] = (now, normalized)
    return normalized[:limit]


def clear_cache() -> None:
    """For tests."""
    _CACHE.clear()
