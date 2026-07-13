"""Point-in-time historical fundamentals from SEC EDGAR XBRL.

WHY (the missing piece for honest backtesting)
══════════════════════════════════════════════
The scoring system's fundamental pillars (value / profitability /
sustainability / growth) are computed from the CURRENT fundamentals
snapshot — we never stored them historically. That makes it impossible
to backtest those pillars: applying today's P/E to a 2019 date is
look-ahead bias.

SEC EDGAR's XBRL `companyfacts` API solves this for US issuers, FOR
FREE, and reuses the EDGAR access we already have for 13F filings.
Every reported financial fact carries a `filed` date — the day it
became public. That `filed` field is the point-in-time (PIT) marker:
at any historical date t we can reconstruct exactly which numbers were
known by then, with no look-ahead.

Endpoint: https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json
Ticker→CIK: https://www.sec.gov/files/company_tickers.json

SCOPE / LIMITS
══════════════
- US issuers only (SEC). Our universe is US-heavy after the SSE50
  retirement; non-US names simply return no history (graceful).
- XBRL is reliable from ~2009; our OHLCV starts 2016, so 2016-2026 is
  fully covered for the backtest.
- XBRL tag heterogeneity: companies tag the same economic concept
  differently across eras (Apple: `Revenues` in old filings,
  `RevenueFromContractWithCustomerExcludingAssessedTax` in new). The
  CONCEPT_TAGS map lists fallback tags per canonical concept; we merge
  all matching tags into one chronological series.
- The analyst/sentiment pillar is NOT reconstructable here (no filed
  record of historical estimates/targets) — that stays a known gap.

This module is the DATA FOUNDATION (phase 1). The pillar-input
computation (PIT P/E, margins, growth) and backtest wiring build on
top of `facts_as_of` / `ttm_flow` / `latest_instant`.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import date

import requests
from loguru import logger
from sqlalchemy.orm import Session

# Reuse the SEC-compliant User-Agent + timeout already vetted for 13F.
from app.services.sec_13f_scraper import _REQUEST_TIMEOUT, _USER_AGENT

_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# fetch_cache `kind` for the parsed, compact per-ticker fact history.
_CACHE_KIND = "sec_facts_history"
# Companyfacts changes only when a new 10-Q/10-K is filed (quarterly).
# A 7-day freshness window is plenty and keeps SEC traffic minimal.
_CACHE_MAX_AGE_SEC = 7 * 24 * 3600


# ── Canonical concept → ordered XBRL tag fallbacks ───────────────────
# Order matters: the FIRST tag with data for a given period wins, but
# we merge across tags to maximise history coverage. Grouped by the
# pillar that consumes them.
CONCEPT_TAGS: dict[str, list[str]] = {
    # Value + Growth
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "eps_diluted": ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"],
    # Profitability
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    # Balance sheet (instant)
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "assets": ["Assets"],
    "shares_outstanding": [
        "CommonStockSharesOutstanding",
        "EntityCommonStockSharesOutstanding",
        "WeightedAverageNumberOfDilutedSharesOutstanding",
    ],
    "long_term_debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    # Cash flow + sustainability
    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsForCapitalImprovements",
    ],
    "dividends_paid": ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"],
}

# Concepts that are point-in-time balances (no period duration) vs
# period flows (have start+end, can be TTM-summed).
_INSTANT_CONCEPTS = {"equity", "assets", "shares_outstanding", "long_term_debt"}


@dataclass(frozen=True)
class FactPoint:
    """One reported value for a concept, with its PIT `filed` date."""
    end: str          # period-end ISO date
    val: float
    filed: str        # ISO date the value became public (the PIT marker)
    form: str         # "10-K" | "10-Q" | ...
    start: str | None  # period-start ISO (None for instant balances)
    duration_days: int | None  # ~91 quarterly, ~365 annual; None instant


# In-process ticker→CIK map (the file is ~1MB; fetched once per boot).
_TICKER_CIK: dict[str, int] | None = None
_TICKER_CIK_LOCK = threading.Lock()


def _http_get_json(url: str) -> dict | list | None:
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
            timeout=_REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning(f"[sec_fund] GET {url} -> {resp.status_code}")
            return None
        return resp.json()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[sec_fund] GET {url} failed: {e}")
        return None


def ticker_to_cik(ticker: str) -> int | None:
    """Resolve a ticker to its SEC CIK via company_tickers.json.
    Cached in-process after first fetch. The SEC file keys by ticker
    in upper case without exchange suffix, so we strip any `.XX`."""
    global _TICKER_CIK
    base = ticker.split(".")[0].strip().upper()
    with _TICKER_CIK_LOCK:
        if _TICKER_CIK is None:
            data = _http_get_json(_TICKERS_URL)
            mapping: dict[str, int] = {}
            if isinstance(data, dict):
                # Shape: {"0": {"cik_str": 320193, "ticker": "AAPL", ...}, ...}
                for row in data.values():
                    t = str(row.get("ticker", "")).upper()
                    cik = row.get("cik_str")
                    if t and isinstance(cik, int):
                        mapping[t] = cik
            _TICKER_CIK = mapping
            logger.info(f"[sec_fund] loaded {len(mapping)} ticker→CIK mappings")
    return _TICKER_CIK.get(base)


def _parse_companyfacts(raw: dict) -> dict[str, list[FactPoint]]:
    """Extract our canonical concepts from a companyfacts payload.
    Merges across the fallback tags and across `dei`/`us-gaap`
    taxonomies. De-duplicates (end, val, form) keeping the EARLIEST
    `filed` (the first time the number was reported — the honest PIT
    date; later amendments would otherwise inflate look-back)."""
    facts = raw.get("facts", {}) if isinstance(raw, dict) else {}
    # Flatten all taxonomy buckets into one tag→concept-units lookup.
    tag_buckets: dict[str, dict] = {}
    for tax in ("us-gaap", "dei", "ifrs-full"):
        for tag, body in (facts.get(tax) or {}).items():
            tag_buckets[tag] = body

    out: dict[str, list[FactPoint]] = {}
    for concept, tags in CONCEPT_TAGS.items():
        seen: dict[tuple, FactPoint] = {}
        for tag in tags:
            body = tag_buckets.get(tag)
            if not body:
                continue
            for _unit, rows in (body.get("units") or {}).items():
                for r in rows:
                    end = r.get("end")
                    val = r.get("val")
                    filed = r.get("filed")
                    if end is None or val is None or filed is None:
                        continue
                    try:
                        val = float(val)
                    except (TypeError, ValueError):
                        continue
                    start = r.get("start")
                    dur = None
                    if start:
                        try:
                            d0 = date.fromisoformat(start)
                            d1 = date.fromisoformat(end[:10])
                            dur = (d1 - d0).days
                        except ValueError:
                            dur = None
                    key = (end, round(val, 4), start or "")
                    fp = FactPoint(
                        end=end[:10], val=val, filed=filed[:10],
                        form=str(r.get("form") or ""), start=start,
                        duration_days=dur,
                    )
                    prev = seen.get(key)
                    # Keep earliest filed for the same economic fact.
                    if prev is None or fp.filed < prev.filed:
                        seen[key] = fp
        if seen:
            out[concept] = sorted(seen.values(), key=lambda f: (f.end, f.filed))
    return out


def get_fact_history(db: Session, ticker: str) -> dict[str, list[FactPoint]]:
    """Return the parsed PIT fact history for `ticker`, using the
    fetch_cache L2 (7-day freshness). On miss: resolve CIK → fetch
    companyfacts → parse → cache the compact result. Empty dict for
    non-US / unresolved tickers (graceful)."""
    from app.services import fetch_cache_store as fcs

    cached = fcs._read_row(db, ticker, _CACHE_KIND, _CACHE_MAX_AGE_SEC)
    if cached is not None:
        try:
            payload = json.loads(cached[0])
            return {
                concept: [FactPoint(**fp) for fp in pts]
                for concept, pts in payload.items()
            }
        except (json.JSONDecodeError, TypeError, KeyError):
            pass  # corrupt cache → re-fetch

    cik = ticker_to_cik(ticker)
    if cik is None:
        return {}
    # Polite rate-limit on the ACTUAL network fetch (cache hits above
    # never reach here). SEC's documented ceiling is 10 req/s; the
    # 13F scraper uses ~6/s headroom, mirrored here so a bulk backtest
    # fetch of the whole universe stays within SEC's fair-access rule.
    import time as _time
    _time.sleep(0.15)
    raw = _http_get_json(_COMPANYFACTS_URL.format(cik=cik))
    if not isinstance(raw, dict):
        return {}
    parsed = _parse_companyfacts(raw)

    # Cache the compact parsed result (dataclass → dict).
    payload = {
        concept: [fp.__dict__ for fp in pts] for concept, pts in parsed.items()
    }
    try:
        fcs._upsert(db, ticker, _CACHE_KIND, json.dumps(payload))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[sec_fund] cache write failed for {ticker}: {e}")
    return parsed


# ── Point-in-time query helpers ──────────────────────────────────────


def latest_instant(
    history: dict[str, list[FactPoint]], concept: str, as_of: date,
) -> FactPoint | None:
    """Latest balance-sheet value for `concept` that was FILED on or
    before `as_of`. Returns the most-recently-ended such fact."""
    pts = history.get(concept) or []
    eligible = [p for p in pts if _filed_le(p.filed, as_of)]
    if not eligible:
        return None
    # Most recent reporting period among the already-filed facts.
    return max(eligible, key=lambda p: (p.end, p.filed))


def ttm_flow(
    history: dict[str, list[FactPoint]], concept: str, as_of: date,
) -> float | None:
    """Trailing-twelve-month sum for a flow concept (revenue, net
    income, …) using only facts FILED on or before `as_of`.

    Strategy: prefer summing the 4 most-recent NON-OVERLAPPING quarterly
    (~91-day) periods. If quarterly coverage is incomplete (common —
    Q4 is only inside the annual 10-K), fall back to the most recent
    annual (~365-day) value. Returns None if neither is available.
    """
    pts = [p for p in (history.get(concept) or []) if _filed_le(p.filed, as_of)]
    if not pts:
        return None
    quarterly = sorted(
        [p for p in pts if p.duration_days and 80 <= p.duration_days <= 100],
        key=lambda p: p.end, reverse=True,
    )
    # Take 4 most recent quarters with distinct period-ends.
    picked: list[FactPoint] = []
    seen_ends: set[str] = set()
    for p in quarterly:
        if p.end in seen_ends:
            continue
        seen_ends.add(p.end)
        picked.append(p)
        if len(picked) == 4:
            break
    if len(picked) == 4:
        return sum(p.val for p in picked)
    # Fallback: latest annual.
    annual = sorted(
        [p for p in pts if p.duration_days and 350 <= p.duration_days <= 380],
        key=lambda p: p.end, reverse=True,
    )
    if annual:
        return annual[0].val
    return None


def facts_as_of(
    history: dict[str, list[FactPoint]], as_of: date,
) -> dict[str, float | None]:
    """Convenience snapshot: for each concept, the PIT value as of
    `as_of` — TTM for flows, latest balance for instants. The single
    call a backtest needs per (ticker, date) to feed the fundamental
    pillars."""
    out: dict[str, float | None] = {}
    for concept in CONCEPT_TAGS:
        if concept in _INSTANT_CONCEPTS:
            fp = latest_instant(history, concept, as_of)
            out[concept] = fp.val if fp else None
        else:
            out[concept] = ttm_flow(history, concept, as_of)
    return out


def _filed_le(filed_iso: str, as_of: date) -> bool:
    try:
        return date.fromisoformat(filed_iso[:10]) <= as_of
    except (ValueError, TypeError):
        return False


def clear_ticker_cik_cache() -> None:
    """Test/maintenance helper — drop the in-process CIK map."""
    global _TICKER_CIK
    with _TICKER_CIK_LOCK:
        _TICKER_CIK = None
