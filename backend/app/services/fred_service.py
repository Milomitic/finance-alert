"""FRED (Federal Reserve Economic Data) API client.

Wraps the public FRED REST API to drive the macro calendar with live
release-schedule data + historical observations:

  - **Release dates** for each tracked series (when the next CPI /
    NFP / FOMC etc. drops). Replaces the hardcoded
    `services/calendar_macros._MACRO_EVENTS` tuple.
  - **Historical observations** for the same series, so the calendar
    detail panel can show the previous value, the change vs prior,
    and a small sparkline of recent prints.

Auth
----
Free API key, configurable via `FRED_API_KEY` env var. When empty, the
service short-circuits and the calendar falls back to the hardcoded
schedule. This keeps the app fully functional offline / before a key
is provisioned.

Rate limit
----------
FRED's published cap is 120 req/min. We don't approach that — the
calendar refresh job runs once per day and the per-series fetch is
~1 call (releases) + ~1 call (observations). Even with 30 tracked
series that's <1 req/sec.

Caching
-------
This module is a thin HTTP adapter; persistence happens upstream in
`MacroSeries` / `MacroObservation` tables (see
`scripts/refresh_fred.py`). No in-process cache needed — the daily
job reads from FRED and the API endpoints read from DB.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import httpx
from loguru import logger

from app.core.config import settings

_FRED_BASE = "https://api.stlouisfed.org/fred"


def _is_enabled() -> bool:
    """True when an API key is configured. Callers should check this
    before invoking the fetch functions; when False, fall back to
    the hardcoded macro list."""
    return bool(settings.fred_api_key.strip())


def _params(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Common query params: api_key + JSON file_type."""
    p: dict[str, Any] = {
        "api_key": settings.fred_api_key,
        "file_type": "json",
    }
    if extra:
        p.update(extra)
    return p


@dataclass(frozen=True)
class FredObservation:
    date: date
    value: float | None  # FRED uses "." for missing; we map to None


@dataclass(frozen=True)
class FredReleaseDate:
    release_id: int
    date: date


def fetch_observations(
    series_id: str,
    *,
    observation_start: date | None = None,
    observation_end: date | None = None,
) -> list[FredObservation]:
    """Fetch the time series of `series_id`. Each observation is
    `(date, value)` where date is the *reference period start* (e.g.
    2026-04-01 for April 2026 CPI).

    `observation_start` / `observation_end` bound the result; both
    inclusive. Defaults: full series.

    Returns sorted ascending by date.
    """
    if not _is_enabled():
        logger.warning("[fred] API key not configured — skipping observations")
        return []
    extra: dict[str, Any] = {"series_id": series_id, "sort_order": "asc"}
    if observation_start:
        extra["observation_start"] = observation_start.isoformat()
    if observation_end:
        extra["observation_end"] = observation_end.isoformat()
    from app.services import data_source_metrics
    try:
        with httpx.Client(timeout=15.0) as c:
            resp = c.get(f"{_FRED_BASE}/series/observations", params=_params(extra))
            resp.raise_for_status()
            data = resp.json()
        data_source_metrics.record_success("fred", "macro")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[fred] observations fetch failed for {series_id}: {e}")
        data_source_metrics.record_failure(
            "fred", "macro", reason=str(e)[:200]
        )
        return []
    out: list[FredObservation] = []
    for row in data.get("observations", []):
        d = _parse_iso_date(row.get("date"))
        v_raw = row.get("value", "")
        v: float | None
        if v_raw in ("", "."):
            v = None
        else:
            try:
                v = float(v_raw)
            except (TypeError, ValueError):
                v = None
        if d is not None:
            out.append(FredObservation(date=d, value=v))
    return out


def fetch_release_dates(
    release_id: int,
    *,
    realtime_start: date | None = None,
    realtime_end: date | None = None,
    include_release_dates_with_no_data: bool = True,
) -> list[FredReleaseDate]:
    """Fetch the schedule of release publication dates for a FRED
    `release_id` (each release has a stable integer id — 10 = US CPI,
    50 = Employment Situation/NFP, 101 = Federal Open Market
    Committee, etc.).

    `include_release_dates_with_no_data=True` lets us see scheduled
    future dates that haven't been published yet (the whole point —
    the calendar is forward-looking).
    """
    if not _is_enabled():
        return []
    extra: dict[str, Any] = {
        "release_id": release_id,
        "include_release_dates_with_no_data": str(
            include_release_dates_with_no_data
        ).lower(),
        "sort_order": "asc",
    }
    if realtime_start:
        extra["realtime_start"] = realtime_start.isoformat()
    if realtime_end:
        extra["realtime_end"] = realtime_end.isoformat()
    try:
        with httpx.Client(timeout=15.0) as c:
            resp = c.get(f"{_FRED_BASE}/release/dates", params=_params(extra))
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[fred] release/dates fetch failed for {release_id}: {e}")
        return []
    out: list[FredReleaseDate] = []
    for row in data.get("release_dates", []):
        d = _parse_iso_date(row.get("date"))
        if d is not None:
            out.append(FredReleaseDate(release_id=release_id, date=d))
    return out


def _parse_iso_date(s: Any) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(str(s), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
