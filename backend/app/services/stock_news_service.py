"""yfinance news wrapper with in-memory TTL cache."""
from datetime import UTC, datetime, timedelta
from typing import Any

from loguru import logger

NEWS_TTL = timedelta(hours=1)
_CACHE: dict[str, tuple[datetime, list[dict[str, Any]]]] = {}


def _normalize_yf_item(raw: dict) -> dict[str, Any] | None:
    """yfinance.Ticker.news returns dicts of varying shape across versions.
    Normalize to {title, link, publisher, published_at: ISO8601 str | None}."""
    title = raw.get("title")
    link = raw.get("link") or raw.get("url")
    publisher = raw.get("publisher") or raw.get("source")
    ts = raw.get("providerPublishTime") or raw.get("publish_time")
    if not title or not link:
        return None
    published_at = (
        datetime.fromtimestamp(ts, tz=UTC).isoformat() if isinstance(ts, (int, float)) else None
    )
    return {
        "title": str(title),
        "link": str(link),
        "publisher": str(publisher) if publisher else "Unknown",
        "published_at": published_at,
    }


def get_news(ticker: str, limit: int = 5) -> list[dict[str, Any]]:
    """Fetch news for a ticker. Cached for 1h. Returns [] on any error."""
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
    _CACHE[ticker] = (now, normalized)
    return normalized[:limit]


def clear_cache() -> None:
    """For tests."""
    _CACHE.clear()
