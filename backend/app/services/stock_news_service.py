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
    """Fetch news for a ticker. Two-tier cache (L1 in-memory, L2 fetch_cache).
    Returns [] on any error.

    Items are sorted **descending** by published_at (most recent first) so
    the UI can render them in chronological order without doing a sort pass.
    Items missing a published_at are pushed to the end (least useful).
    """
    now = datetime.now(UTC)
    # L1 — fast in-memory check
    cached = _CACHE.get(ticker)
    if cached and (now - cached[0]) < NEWS_TTL:
        return cached[1][:limit]

    # L2 — DB cache (survives restart). Lazy import to keep this module
    # importable without the SQLAlchemy machinery for unit tests.
    try:
        from app.core.db import SessionLocal
        from app.services import fetch_cache_store
        ttl_sec = int(NEWS_TTL.total_seconds())
        with SessionLocal() as db:
            l2 = fetch_cache_store.read_news(db, ticker, ttl_sec)
        if l2 is not None:
            _CACHE[ticker] = (now, l2)
            return l2[:limit]
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[news] L2 read failed for {ticker}: {exc}")

    # Both layers missed → upstream fetch
    try:
        import yfinance as yf
        raw_items = yf.Ticker(ticker).news or []
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[news] yfinance fetch failed for {ticker}: {exc}")
        # Cache empty result in L1 only to avoid hammering on failure.
        # Don't persist failures to L2 — a transient yfinance outage shouldn't
        # poison the cache for an hour across restarts.
        _CACHE[ticker] = (now, [])
        return []
    normalized = [n for raw in raw_items if (n := _normalize_yf_item(raw))]
    normalized.sort(key=lambda n: n.get("published_at") or "", reverse=True)
    _CACHE[ticker] = (now, normalized)
    # Persist to L2. Non-fatal — L1 still serves consumers if the DB write fails.
    try:
        from app.core.db import SessionLocal
        from app.services import fetch_cache_store
        with SessionLocal() as db:
            fetch_cache_store.write_news(db, ticker, normalized)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[news] L2 write failed for {ticker}: {exc}")
    return normalized[:limit]


def clear_cache() -> None:
    """Clear BOTH layers (L1 in-memory + L2 DB rows). Used by tests to
    isolate themselves; safe in production too — `clear_cache` is otherwise
    only called by intentional refresh paths where dropping persisted
    rows is the desired behavior."""
    _CACHE.clear()
    try:
        from app.core.db import SessionLocal
        from app.models import FetchCache
        with SessionLocal() as db:
            db.query(FetchCache).filter_by(kind="news").delete()
            db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[news] L2 clear failed: {exc}")


def hydrate_l1_from_db() -> int:
    """Populate the in-memory L1 cache from the persistent L2 table at
    startup. Mirrors stock_fundamentals_service.hydrate_l1_from_db.
    Returns the number of fresh entries hydrated."""
    try:
        from app.core.db import SessionLocal
        from app.services import fetch_cache_store
        ttl_sec = int(NEWS_TTL.total_seconds())
        with SessionLocal() as db:
            entries = fetch_cache_store.hydrate_all_news(db, ttl_sec)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[news] L1 hydration failed: {exc}")
        return 0
    _CACHE.update(entries)
    if entries:
        logger.info(f"[news] hydrated L1 with {len(entries)} entries from L2")
    return len(entries)
