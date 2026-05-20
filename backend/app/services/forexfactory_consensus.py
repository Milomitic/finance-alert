"""Forexfactory weekly XML calendar — public consensus feed.

Why this exists: FRED has the actual published values for macro
indicators but doesn't publish CONSENSUS forecasts ("Atteso").
Forexfactory's free weekly calendar XML
(`https://nfs.faireconomy.media/ff_calendar_thisweek.xml`) is the
canonical free source and ships the median analyst forecast for
every covered event, plus the prior reading and the actual when it
hits the wire.

Cache: 30-minute in-memory TTL. Forexfactory updates the consensus
a few times before each release (analyst polls converge as the date
approaches), so 30 minutes is short enough to catch the final
consensus without spamming the host.

Mapping: event titles in Forexfactory don't 1:1 match the FRED
labels we use. `_FF_LABEL_MAP` translates our internal label →
Forexfactory event-title regex. Stays conservative: only the
indicators we surface on the calendar are mapped, so noise from
~118 weekly events gets filtered out.

Failure mode: any HTTP / parse error returns an empty index. The
consumer (`MacroEventDC` builder) sees `None` for expected and
falls back to "n/d" in the UI. Forexfactory is a courtesy data
source — the rest of the calendar still works without it.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import requests
from loguru import logger


_FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
_USER_AGENT = "FinanceAlert milomitic@gmail.com"
_TIMEOUT = 15.0
_TTL_SEC = 30 * 60  # 30 minutes

# ─── Persistent fallback (resilience layer) ──────────────────────────
# ForexFactory is a single point of failure for macro CONSENSUS values
# (FRED has actuals, FF has the consensus median). The XML host
# (`nfs.faireconomy.media`) is unaffiliated with any of our other
# sources, so when it's down (or rate-limits / changes format) we
# silently lose every "Atteso" column on the calendar.
#
# Finding a real second SOURCE for free macro consensus is hard (the
# alternatives are paid Bloomberg-style feeds). The pragmatic fix is
# a **resilience cache**: persist the most recent successful XML to
# disk and fall back to it on fetch failure. The consensus for an
# event is set days before the release and updated only a handful of
# times — so serving a 6-12h stale "Atteso" value is far better than
# losing the data entirely.
#
# Behavior:
#   • Every successful fetch overwrites `data/ff_calendar.xml`.
#   • Every failed fetch (HTTP error / parse error / empty response)
#     falls back to the on-disk copy if it's < `_DISK_MAX_AGE_SEC` old.
#   • A log line distinguishes "live" vs "stale-disk" service so the
#     operator sees when we're in degraded mode.
_DISK_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_DISK_FILE = _DISK_DIR / "ff_calendar.xml"
_DISK_MAX_AGE_SEC = 6 * 3600  # 6h — consensus doesn't move faster than this in practice


# ---------------------------------------------------------------------------
# Label mapping — our internal label → Forexfactory event title pattern.
#
# Format: (country_code_from_xml, regex_against_title). Country gates the
# match so e.g. "Eurozone CPI" doesn't catch "USD CPI". Patterns are
# case-insensitive. First match wins.
#
# Coverage notes:
# - We deliberately don't try to map Asian central banks here — Forexfactory
#   uses non-standard titles for BoJ/PBoC and the consensus is rarely
#   published. Those events return None for expected and the UI shows
#   "n/d", same as before.
# - When Forexfactory has multiple events that could match (e.g. "CPI m/m"
#   and "Core CPI m/m" both for US CPI release), the regex should match
#   the headline one — usually the non-Core variant.
# ---------------------------------------------------------------------------
_FF_LABEL_MAP: dict[str, tuple[str, str]] = {
    # ── US (FRED-curated; labels match `refresh_fred.CURATED_SERIES`) ──
    "US CPI release":             ("USD", r"^CPI m/m$"),
    "US PPI release":             ("USD", r"^PPI m/m$"),
    "US NFP / Non-Farm Payrolls": ("USD", r"^Non-Farm Employment Change$"),
    "US Unemployment Rate":       ("USD", r"^Unemployment Rate$"),
    "FOMC rate decision":         ("USD", r"^Federal Funds Rate$"),
    "US GDP (real)":              ("USD", r"GDP.*q/q|Advance GDP|GDP m/m"),
    "US GDP (advance, Q1)":       ("USD", r"GDP.*q/q|Advance GDP"),
    "US GDP (final, Q1)":         ("USD", r"GDP.*q/q|Final GDP"),
    "US Retail Sales":            ("USD", r"^(Core )?Retail Sales m/m$"),
    "ISM Manufacturing PMI":      ("USD", r"^ISM Manufacturing PMI$"),
    "ISM Services PMI":           ("USD", r"^ISM Services PMI$"),

    # ── Eurozone / Europe ──
    # Note: the hardcoded `calendar_macros._MACRO_EVENTS` adds month
    # suffixes like "Eurozone HICP flash (April)"; `_normalize_label`
    # below strips those so the lookup hits this base key.
    "Eurozone HICP flash":        ("EUR", r"^CPI Flash Estimate y/y$"),
    "Eurozone PMI flash":         ("EUR", r"Flash (Manufacturing|Services) PMI"),
    "ECB rate decision":          ("EUR", r"^Main Refinancing Rate$"),
    "ECB Deposit Facility Rate":  ("EUR", r"^Main Refinancing Rate$"),  # legacy alias
    "ZEW Economic Sentiment (DE)": ("EUR", r"German ZEW Economic Sentiment"),
    "IFO Business Climate (DE)":  ("EUR", r"German ifo Business Climate"),

    # ── United Kingdom ──
    "UK CPI release":             ("GBP", r"^CPI y/y$"),
    "UK GDP (Q1, prelim)":        ("GBP", r"^Prelim GDP q/q$"),
    "UK GDP (final)":             ("GBP", r"^Final GDP q/q$"),
    "BoE rate decision":          ("GBP", r"^Official Bank Rate$"),
    "BoE Bank Rate":              ("GBP", r"^Official Bank Rate$"),  # legacy alias

    # ── Japan ──
    "Japan CPI release":          ("JPY", r"^(National )?Core CPI y/y$"),
    "BoJ rate decision":          ("JPY", r"^BOJ Policy Rate$"),
}


@dataclass
class FFEvent:
    """One event from Forexfactory's weekly XML.

    `forecast` and `previous` are the strings as they appear in the XML
    (e.g. "3.75%", "0.5%", "212K", "<3.75%"); the consumer parses to
    float as needed. `actual` is populated post-release.
    """
    title: str
    country: str          # 3-letter currency-style code: USD/EUR/GBP/JPY/...
    date: date
    impact: str           # "High" | "Medium" | "Low" | "Holiday"
    forecast: str | None
    previous: str | None
    actual: str | None


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_CACHE: tuple[float, list[FFEvent]] | None = None  # (fetched_at, events)


def _read_disk_fallback() -> str | None:
    """Return the on-disk XML if it exists and is < `_DISK_MAX_AGE_SEC`
    old. None otherwise. Used as a secondary source when the live
    upstream fetch fails — better to serve a 1-6h stale consensus
    than to drop the column entirely."""
    try:
        if not _DISK_FILE.exists():
            return None
        age = time.time() - _DISK_FILE.stat().st_mtime
        if age > _DISK_MAX_AGE_SEC:
            return None
        return _DISK_FILE.read_text(encoding="utf-8")
    except OSError as e:
        logger.debug(f"[forexfactory] disk fallback read failed: {e}")
        return None


def _write_disk_fallback(xml: str) -> None:
    """Persist the latest successful XML. Atomic write (tmp + rename)
    so a crash mid-write can't leave a half-truncated file that
    `_read_disk_fallback()` would happily serve as garbage."""
    try:
        _DISK_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _DISK_FILE.with_suffix(_DISK_FILE.suffix + ".tmp")
        tmp.write_text(xml, encoding="utf-8")
        tmp.replace(_DISK_FILE)
    except OSError as e:
        # Persistence failure is non-fatal — live serving still works,
        # the next fetch will retry persistence.
        logger.warning(f"[forexfactory] disk fallback write failed: {e}")


def _fetch_xml() -> tuple[str | None, str]:
    """Fetch the FF weekly XML, with a persistent-cache fallback on
    failure. Returns `(xml_or_None, source_tag)` where `source_tag`
    is one of:
        "live"        — live HTTP fetch succeeded
        "stale-disk"  — live failed, served from on-disk persistence
        "none"        — live failed AND disk fallback unavailable/stale
    The tag is exposed for log differentiation; the caller doesn't
    branch on it (treats empty xml as failure either way)."""
    try:
        resp = requests.get(
            _FF_URL,
            headers={"User-Agent": _USER_AGENT, "Accept": "text/xml"},
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200 and resp.text:
            _write_disk_fallback(resp.text)
            return resp.text, "live"
        logger.warning(f"[forexfactory] GET -> {resp.status_code}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[forexfactory] fetch failed: {e}")

    # Live fetch failed — try the disk fallback.
    fallback_xml = _read_disk_fallback()
    if fallback_xml:
        logger.info(
            "[forexfactory] live fetch failed, serving on-disk fallback "
            f"(age <{_DISK_MAX_AGE_SEC // 3600}h)"
        )
        return fallback_xml, "stale-disk"
    return None, "none"


def _parse_xml(text: str) -> list[FFEvent]:
    """Cheap regex parse. Forexfactory's XML is flat & predictable so
    we don't pay for a full ElementTree pass — a regex sweep over
    `<event>...</event>` blocks is enough."""
    events: list[FFEvent] = []
    for block in re.findall(r"<event>(.*?)</event>", text, re.DOTALL):
        title = _cdata_or_text(block, "title")
        country = _cdata_or_text(block, "country")
        date_s = _cdata_or_text(block, "date")
        impact = _cdata_or_text(block, "impact")
        forecast = _cdata_or_text(block, "forecast")
        previous = _cdata_or_text(block, "previous")
        actual = _cdata_or_text(block, "actual")
        if not title or not country or not date_s:
            continue
        try:
            # Forexfactory dates are MM-DD-YYYY (US format).
            d = datetime.strptime(date_s, "%m-%d-%Y").date()
        except ValueError:
            continue
        events.append(FFEvent(
            title=title.strip(),
            country=country.strip(),
            date=d,
            impact=impact.strip() if impact else "",
            forecast=forecast.strip() or None if forecast else None,
            previous=previous.strip() or None if previous else None,
            actual=actual.strip() or None if actual else None,
        ))
    return events


def _cdata_or_text(block: str, tag: str) -> str | None:
    """Pull the inner content of <tag>CDATA[...]</tag> (with or without CDATA)."""
    cdata = re.search(rf"<{tag}><!\[CDATA\[(.*?)\]\]></{tag}>", block, re.DOTALL)
    if cdata:
        return cdata.group(1)
    plain = re.search(rf"<{tag}>(.*?)</{tag}>", block, re.DOTALL)
    if plain:
        return plain.group(1)
    return None


def _get_events() -> list[FFEvent]:
    """Cached events for the current week. Returns [] only when both
    the live HTTP fetch AND the on-disk fallback are unavailable."""
    global _CACHE
    now = time.time()
    if _CACHE is not None and (now - _CACHE[0]) < _TTL_SEC:
        return _CACHE[1]
    xml, _source = _fetch_xml()
    if xml is None:
        # Both live and disk fallback failed → cache empty briefly to
        # avoid hammering on outage. Memory-cache TTL is shorter than
        # the disk fallback's 6h so we keep probing the live source.
        _CACHE = (now, [])
        return []
    events = _parse_xml(xml)
    _CACHE = (now, events)
    return events


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _normalize_label(label: str) -> str:
    """Strip a trailing `( ... )` annotation so labels like
    "Eurozone HICP flash (April)" and "ZEW Economic Sentiment (DE)" hit
    the same key as their base form. `calendar_macros._MACRO_EVENTS`
    sometimes appends the period or country in parens — without this
    helper the dict lookup misses every parenthesized variant."""
    import re as _re
    return _re.sub(r"\s*\([^)]*\)\s*$", "", label).strip()


def consensus_for_label(label: str, on_date: date) -> FFEvent | None:
    """Look up the Forexfactory consensus event matching our internal
    `label` for `on_date`. Returns None when:
      - The label isn't in `_FF_LABEL_MAP` (we don't track its consensus)
      - No matching event is in the current weekly XML for that date
      - The XML failed to load entirely (network issue)
    Date matching is exact (same day); ±1-day tolerance isn't worth it
    because Forexfactory uses the local-of-event date, same as ours.

    The lookup first tries the exact label, then strips any trailing
    "(...)" annotation (`_normalize_label`) so e.g. "Eurozone HICP
    flash (April)" resolves to the "Eurozone HICP flash" entry."""
    mapping = _FF_LABEL_MAP.get(label) or _FF_LABEL_MAP.get(_normalize_label(label))
    if mapping is None:
        return None
    expected_country, title_pattern = mapping
    title_re = re.compile(title_pattern, re.IGNORECASE)
    for ev in _get_events():
        if ev.country != expected_country:
            continue
        if ev.date != on_date:
            continue
        if title_re.search(ev.title):
            return ev
    return None


def parse_numeric(value: str | None) -> float | None:
    """Parse a Forexfactory numeric string to float.

    Examples that should succeed:
        "3.75%"       → 3.75
        "212K"        → 212000
        "0.5%"        → 0.5
        "-2.4B"       → -2_400_000_000
        "<3.75%"      → 3.75   (the operators ` <`, `>`, `≤`, `≥` are stripped)
        "1,234"       → 1234

    Returns None for empty / unparseable strings.
    """
    if not value:
        return None
    s = value.strip().lstrip("<>≤≥").strip()
    # Strip trailing unit. K=1e3, M=1e6, B=1e9, T=1e12.
    multiplier = 1.0
    if s and s[-1].upper() in ("K", "M", "B", "T"):
        unit = s[-1].upper()
        multiplier = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}[unit]
        s = s[:-1]
    # Strip percent sign.
    s = s.rstrip("%").rstrip()
    s = s.replace(",", "")
    try:
        return float(s) * multiplier
    except ValueError:
        return None


def consensus_value_for_label(label: str, on_date: date) -> float | None:
    """Convenience wrapper: look up + parse the forecast value.
    Returns None when no event matches or the forecast parses-fail."""
    ev = consensus_for_label(label, on_date)
    if ev is None or not ev.forecast:
        return None
    return parse_numeric(ev.forecast)


def consensus_actual_for_label(label: str, on_date: date) -> float | None:
    """Companion to `consensus_value_for_label`: returns the ACTUAL
    value Forexfactory reports for the event after release. Useful
    when we want a same-day "what happened" before FRED catches up."""
    ev = consensus_for_label(label, on_date)
    if ev is None or not ev.actual:
        return None
    return parse_numeric(ev.actual)


def clear_cache() -> None:
    """Test hook — invalidates the in-memory cache."""
    global _CACHE
    _CACHE = None
