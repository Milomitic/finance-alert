"""yfinance news wrapper with in-memory TTL cache."""
from datetime import UTC, datetime, timedelta
from typing import Any

from loguru import logger

from app.services.news_sentiment import classify_title

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
    title_str = str(title)
    # `summary` is the plain-text article preview yfinance ≥0.2.40 ships
    # alongside the title. Cheaper signal source for the analyst-action
    # extractor than HTTP-scraping the article URL, and the body often
    # spells out what the headline truncates ("Goldman raised its target
    # from $245 to $260, citing Q4 strength" vs the title's bare "Apple
    # gets target hike"). Stored as raw text — the consumer is server-
    # side regex, not the UI.
    summary_v = inner.get("summary")
    summary_str = str(summary_v) if summary_v else None
    return {
        "title": title_str,
        "link": str(link),
        "publisher": str(publisher) if publisher else "Unknown",
        "published_at": published_at,
        # Server-side keyword-based sentiment ("bullish" | "neutral" |
        # "bearish") so the UI can render a colored chip without doing
        # the classification client-side. Persisted into the L2 cache
        # alongside the rest of the item — a re-fetch is the only way
        # to update sentiment for a given headline.
        "sentiment": classify_title(title_str),
        # Plain-text article preview. Used by the analyst-action
        # extractor (server-side); not currently surfaced to the UI.
        # Optional — older cached payloads have None.
        "summary": summary_str,
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
    from app.services import data_source_metrics
    try:
        import yfinance as yf
        raw_items = yf.Ticker(ticker).news or []
        data_source_metrics.record_success("yfinance", "news")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[news] yfinance fetch failed for {ticker}: {exc}")
        data_source_metrics.record_failure(
            "yfinance", "news", reason=str(exc)[:200]
        )
        # Cache empty result in L1 only to avoid hammering on failure.
        # Don't persist failures to L2 — a transient yfinance outage shouldn't
        # poison the cache for an hour across restarts.
        _CACHE[ticker] = (now, [])
        return []
    normalized = [n for raw in raw_items if (n := _normalize_yf_item(raw))]
    normalized.sort(key=lambda n: n.get("published_at") or "", reverse=True)

    if not normalized:
        # yfinance returned 0 usable headlines → try fallbacks in
        # quota-friendliness order:
        #   1. Finnhub (60/min, ~free for our volumes) — added because
        #      yfinance's company-news coverage is patchy for non-US
        #      large-caps AND its analyst-flavored headlines are scarce
        #      even for US large-caps (yfinance prioritizes
        #      generalist "Meta layoffs" headlines over "Wedbush
        #      raises target"). Finnhub aggregates Benzinga / MarketBeat
        #      style publishers that DO carry the analyst-firm-named
        #      headlines.
        #   2. Marketaux (100/day, gated by quota guard + breaker) —
        #      only consulted if Finnhub also returns empty. Same
        #      transformation into the shared news shape.
        # On a typical browsing session: yfinance covers ~80% of
        # tickers, Finnhub covers the rest, Marketaux is rarely needed.
        try:
            from app.services import finnhub_news_service
            finnhub_items = finnhub_news_service.fetch_company_news(
                ticker, limit=15
            )
            if finnhub_items:
                logger.info(
                    f"[news] yfinance empty for {ticker}, using Finnhub "
                    f"fallback ({len(finnhub_items)} items)"
                )
                normalized = [
                    {
                        "title": item.title,
                        "link": item.url,
                        "publisher": item.source or "Finnhub",
                        "published_at": item.published_at or None,
                        "sentiment": classify_title(item.title),
                        "summary": item.summary,
                    }
                    for item in finnhub_items
                ]
        except Exception as exc:  # noqa: BLE001 — fallback can fail, that's OK
            logger.warning(f"[news] finnhub fallback failed for {ticker}: {exc}")

    if not normalized:
        try:
            from app.services import marketaux_news_service
            fallback = marketaux_news_service.fetch_news(ticker, limit=10)
            if fallback:
                logger.info(
                    f"[news] yfinance+finnhub empty for {ticker}, using "
                    f"Marketaux fallback ({len(fallback)} items)"
                )
                normalized = [
                    {
                        "title": item.title,
                        "link": item.url,
                        "publisher": item.source or "Unknown",
                        "published_at": item.published_at or None,
                        "sentiment": classify_title(item.title),
                        "summary": None,
                    }
                    for item in fallback
                ]
        except Exception as exc:  # noqa: BLE001 — fallback can fail, that's OK
            logger.warning(f"[news] marketaux fallback failed for {ticker}: {exc}")

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


def hydrate_l1_from_db() -> tuple[int, int]:
    """Populate the in-memory L1 cache from the persistent L2 table at
    startup. Mirrors stock_fundamentals_service.hydrate_l1_from_db.

    Returns:
        (loaded, skipped) — loaded is the number of fresh entries hydrated;
        skipped is the count of rows that failed deserialization."""
    try:
        from app.core.db import SessionLocal
        from app.services import fetch_cache_store
        ttl_sec = int(NEWS_TTL.total_seconds())
        with SessionLocal() as db:
            entries, skipped = fetch_cache_store.hydrate_all_news(db, ttl_sec)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[news] L1 hydration failed: {exc}")
        return 0, 0
    _CACHE.update(entries)
    loaded = len(entries)
    if loaded or skipped:
        logger.info(f"[news] hydrated L1 with {loaded} entries from L2 (skipped {skipped})")
    return loaded, skipped
