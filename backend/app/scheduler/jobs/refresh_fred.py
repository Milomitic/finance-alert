"""APScheduler job: periodic FRED macro-calendar refresh.

Wraps `scripts.refresh_fred.run()` so it can be triggered by the
in-process scheduler instead of an external cron. The underlying script
is idempotent (UPSERT-only) — running it more often just catches new
observations sooner, never duplicates rows.

Cadence rationale: FRED tends to publish announcement-dependent series
(FOMC rate, CPI, NFP) within minutes-to-an-hour of the official press
release. Polling every 2 hours puts the dashboard's "actual" value
within at most 2h of the live print, which the user has accepted as
"delay accettabile". Aligned to even hours so the cron grid is
predictable in the logs.

The job no-ops when `FRED_API_KEY` is unset — the underlying script
already guards on that and just logs "FRED_API_KEY not configured —
skipping refresh". So enabling the job is risk-free even before the
key is provisioned.
"""
from loguru import logger

from app.scripts import refresh_fred


def run_refresh_fred() -> None:
    logger.info("[refresh_fred] starting")
    try:
        refresh_fred.run()
    except Exception as exc:  # noqa: BLE001
        # FRED 5xx, network blip, etc. Logging suffices — next 2h tick
        # retries, no need to crash the scheduler.
        logger.exception(f"[refresh_fred] aborted: {exc}")
