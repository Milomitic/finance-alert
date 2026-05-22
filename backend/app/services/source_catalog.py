"""Static catalog of known data sources for the platform-health UI.

The `data_source_metrics` module only tracks (source, op) pairs that have
actually been called. The UI needs to show ALL known sources — including
those that haven't been exercised yet (idle) — so the operator knows the
inventory at a glance. This module supplies the metadata (friendly name,
free-tier rate limit, fallback role) and merges it with the live counters.

Rate-limit semantics:
- `per_minute`: free tier allows N calls per rolling minute (Finnhub, FRED).
- `per_day`: free tier allows N calls per rolling day (Marketaux).
- Both None: no documented limit (yfinance, SEC EDGAR — they just
  start failing when overused).
"""
from dataclasses import dataclass

from app.services import data_source_metrics
from app.services.data_source_metrics import SourceMetric


@dataclass(frozen=True)
class SourceSpec:
    """Catalog entry — what we know about a data source statically."""
    source: str
    op: str
    label: str             # human-readable friendly name
    role: str              # "primary" | "fallback" | "scheduled"
    per_minute: int | None
    per_day: int | None
    notes: str = ""


# The full inventory. Adding a new source should land here so the UI
# surfaces it even before its first call.
KNOWN_SOURCES: list[SourceSpec] = [
    # ── yfinance (primary for most ops) ──
    SourceSpec("yfinance", "ohlcv", "Yahoo Finance — OHLCV", "primary",
               per_minute=None, per_day=None,
               notes="Batch downloader. Probe ogni 30 min (heavy)."),
    SourceSpec("yfinance", "fundamentals", "Yahoo Finance — Fundamentals", "primary",
               per_minute=None, per_day=None,
               notes="Ticker.info — slow. Probe ogni 30 min."),
    SourceSpec("yfinance", "market_cap", "Yahoo Finance — Market Cap", "primary",
               per_minute=None, per_day=None,
               notes="fast_info.market_cap. Probe ogni 5 min."),
    SourceSpec("yfinance", "live_quote", "Yahoo Finance — Live Quote", "primary",
               per_minute=None, per_day=None,
               notes="fast_info polling (10s cache). Probe ogni 5 min."),
    SourceSpec("yfinance", "news", "Yahoo Finance — News", "primary",
               per_minute=None, per_day=None,
               notes="Ticker.news. Probe ogni 5 min."),

    # ── Fallbacks ──
    # NOTE: no fallback for OHLCV. Stooq required an API key (May 2026)
    # and no free tier (Polygon 5/min, Tiingo 1000/day, Finnhub
    # /stock/candle paywalled) can service ~1100 tickers per scan. When
    # the yfinance breaker opens, scans skip and retry the next cycle.
    SourceSpec("finnhub", "earnings", "Finnhub — Earnings", "fallback",
               per_minute=60, per_day=None,
               notes="Earnings actuals ~30min vs yfinance ~1-3h. Probe ogni 5 min."),
    SourceSpec("twelvedata", "earnings", "Twelve Data — Earnings", "fallback",
               per_minute=8, per_day=800,
               notes=("Tier-3 EPS actuals (solo EPS, no revenue) dietro "
                      "yfinance+Finnhub. Provider separato da Finnhub → "
                      "regge quando il breaker Finnhub è aperto. Rate "
                      "client 6/min + breaker su 429.")),
    SourceSpec("finnhub", "news", "Finnhub — Company news", "fallback",
               per_minute=60, per_day=None,
               notes=("Fallback news quando yfinance restituisce 0 articoli. "
                      "Cache 1h per ticker → quota usata trascurabile. "
                      "Probe ogni 30 min (slow set).")),
    SourceSpec("finnhub", "upgrades", "Finnhub — Analyst upgrade/downgrade", "fallback",
               per_minute=60, per_day=None,
               notes=("Eventi rating analisti strutturati — sostituto del "
                      "feed yfinance upgrades_downgrades ormai stale. "
                      "Cache 24h per ticker. Probe ogni 30 min.")),
    SourceSpec("finnhub", "recommendation", "Finnhub — Recommendation trends", "fallback",
               per_minute=60, per_day=None,
               notes=("Aggregati buy/hold/sell per ticker — sostituto del "
                      "feed yfinance recommendations quando torna stale. "
                      "Cache 24h. Triggerato solo se yfinance vuoto. ")),
    SourceSpec("marketaux", "news", "Marketaux — News", "fallback",
               per_minute=None, per_day=100,
               notes=("Free tier 100/day. Cache 12h per ticker + circuit "
                      "breaker su 429/quota → ~6-10 unità/day in uso reale. "
                      "Probe smart-elision: salta se Finnhub copre il caso "
                      "o se ultima call < 4h.")),

    # ── Scheduled / macro ──
    SourceSpec("fred", "macro", "FRED — Macro series", "scheduled",
               per_minute=120, per_day=None,
               notes="FRED. Job ogni 2h + probe ogni 5 min."),
    SourceSpec("forexfactory", "consensus", "ForexFactory — Macro consensus", "scheduled",
               per_minute=None, per_day=None,
               notes="XML weekly calendar. Probe HEAD ogni 30 min (reachability)."),
    SourceSpec("sec_13f", "filings", "SEC EDGAR — 13F filings", "scheduled",
               per_minute=None, per_day=None,
               notes="EDGAR submissions endpoint. Probe ogni 30 min (CIK Berkshire)."),
    SourceSpec("nasdaq", "premarket", "Nasdaq — Pre-market volume", "scheduled",
               per_minute=None, per_day=None,
               notes=("Endpoint non ufficiale api.nasdaq.com (no key). "
                      "Arricchimento volume pre-market sui ~20 nomi "
                      "mostrati. Probe ogni 30 min (AAPL, reachability).")),
]


@dataclass
class SourceWithUsage:
    """Catalog entry + live metrics + rate-limit usage snapshot."""
    source: str
    op: str
    label: str
    role: str
    per_minute_limit: int | None
    per_day_limit: int | None
    notes: str
    # Live counters (None when the source has never been called)
    success: int
    failure: int
    success_rate: float       # -1 when no calls yet
    last_success_at: float | None
    last_failure_at: float | None
    last_failure_reason: str | None
    health: str               # "healthy" | "degraded" | "failing" | "idle"
    # Sliding-window usage. Only computed for sources with a declared limit;
    # None for unrestricted sources so the UI can render "—".
    calls_last_minute: int | None
    calls_last_day: int | None


def _zero_metric(source: str, op: str) -> SourceMetric:
    """A 'never called' synthetic metric to use as base when no counter exists."""
    return SourceMetric(
        source=source, op=op,
        success=0, failure=0,
        success_rate=-1.0,
        last_success_at=None, last_failure_at=None, last_failure_reason=None,
        health="idle",
    )


def full_snapshot() -> list[SourceWithUsage]:
    """Return one entry per KNOWN_SOURCES, enriched with live counters and
    sliding-window rate-limit usage. Idle sources appear with zero counts."""
    live: dict[tuple[str, str], SourceMetric] = {
        (m.source, m.op): m for m in data_source_metrics.snapshot()
    }

    out: list[SourceWithUsage] = []
    for spec in KNOWN_SOURCES:
        m = live.get((spec.source, spec.op)) or _zero_metric(spec.source, spec.op)

        # Only compute usage for sources with a known limit (saves the
        # ring-buffer scan when not needed). Compute the appropriate
        # window per limit.
        calls_last_minute = (
            data_source_metrics.calls_in_window(spec.source, spec.op, 60.0)
            if spec.per_minute is not None else None
        )
        calls_last_day = (
            data_source_metrics.calls_in_window(spec.source, spec.op, 86400.0)
            if spec.per_day is not None else None
        )

        out.append(SourceWithUsage(
            source=spec.source, op=spec.op, label=spec.label, role=spec.role,
            per_minute_limit=spec.per_minute,
            per_day_limit=spec.per_day,
            notes=spec.notes,
            success=m.success, failure=m.failure,
            success_rate=m.success_rate,
            last_success_at=m.last_success_at,
            last_failure_at=m.last_failure_at,
            last_failure_reason=m.last_failure_reason,
            health=m.health,
            calls_last_minute=calls_last_minute,
            calls_last_day=calls_last_day,
        ))
    return out
