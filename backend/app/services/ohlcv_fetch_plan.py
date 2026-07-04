"""Shared incremental/backfill fetch PLANNING for the OHLCV scan paths.

The manual scan endpoint (app/api/alerts.py) and the cron/boot job
(app/scheduler/jobs/scan_alerts.py) used to duplicate the same planning
logic — staleness sort, dead-ticker quarantine, cutoff split, overlap
start, smart-skip, chunking — with only the ScanRun UI plumbing differing.
This module owns the SHARED part; each caller keeps its own progress/
heartbeat/cancel/commit wiring inline (deliberately NOT abstracted here —
that UI plumbing is caller-specific and past refactors that tried to
absorb it died of it).

Planning invariants (both callers rely on these):

- PER-STOCK split, not per-chunk: one stale stock must never drag a whole
  chunk down the period="10y" path (~2520 bars re-downloaded + re-upserted
  for every fresh member — the old cron path's boot-catch-up tax).
- QUARANTINE only for ZERO-BAR stocks: delisted/renamed symbols never get
  data, so they'd re-attempt a 10y download at every scan forever. A stock
  WITH stored bars is never quarantined (a few transient yfinance misses
  can't knock a live symbol out of the scan). Rule + weekly re-probe live
  in ohlcv_service.split_quarantined.
- STALENESS SORT (oldest latest-bar first): chunks become homogeneous in
  staleness, so each incremental chunk's start=min(latest) window is tight
  for every member — a lone 29-day-stale stock no longer drags ~20
  one-day-stale stocks into a month-wide fetch window.
- OVERLAP BY ONE SESSION: incremental chunks start AT min(latest), not +1,
  so each stock's newest stored bar is re-requested and corrected by the
  idempotent upsert. Self-heals a wrongly-persisted last bar (e.g. an
  in-flight close that slipped past the market-open guard), keeps weekend
  windows non-empty (Friday's bar included → no false "no data" on Sat/Sun
  scans), and lets the split guard (PriceBasisMismatch) see the overlap bar.
- SMART-SKIP: a chunk whose every member already has TODAY's (settled) bar
  has nothing new AND nothing to revalidate — yielded as KIND_SKIP so the
  caller can advance its progress bar honestly without a network call.
"""
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import Stock
from app.services.ohlcv_service import latest_ohlcv_dates_bulk, split_quarantined

# Chunk kinds yielded by iter_fetch_chunks. The caller maps them onto its own
# phase labels ("fetching:incremental" / "fetching:backfill") and fetch call
# (start= vs period=); KIND_SKIP means "advance progress, no fetch".
KIND_INCREMENTAL = "incremental"
KIND_BACKFILL = "backfill"
KIND_SKIP = "skip"


@dataclass
class FetchPlan:
    """Partition of a stock universe into fetch groups, plus the latest-bar
    map that drove the decision (callers reuse it for their UI messages)."""

    incremental: list[Stock]      # fresh (latest bar >= cutoff), staleness-sorted
    backfill: list[Stock]         # empty or stale — pay the 10y download
    quarantined: list[Stock]      # zero-bar dead tickers skipped this scan
    latest_dates: dict[int, date]  # stock_id -> most recent stored bar date

    @property
    def total(self) -> int:
        """Stocks the fetch loop will actually walk (quarantined excluded)."""
        return len(self.incremental) + len(self.backfill)


def build_fetch_plan(
    db: Session, stocks: list[Stock], *, cutoff_days: int = 30
) -> FetchPlan:
    """Build the incremental/backfill/quarantine partition for `stocks`.

    One bulk GROUP BY replaces per-stock point lookups (B2): for ~1100
    stocks × 100-per-chunk that used to be ~13k indexed queries.
    """
    latest_dates = latest_ohlcv_dates_bulk(db, [s.id for s in stocks])
    cutoff = date.today() - timedelta(days=cutoff_days)
    incremental = [
        s for s in stocks
        if latest_dates.get(s.id) is not None and latest_dates[s.id] >= cutoff
    ]
    backfill = [
        s for s in stocks
        if latest_dates.get(s.id) is None or latest_dates[s.id] < cutoff
    ]
    # Dead-ticker quarantine — ONLY stocks with zero stored bars (nothing to
    # evaluate anyway); see module docstring.
    _, quarantined = split_quarantined(
        [s for s in backfill if latest_dates.get(s.id) is None]
    )
    if quarantined:
        qids = {s.id for s in quarantined}
        backfill = [s for s in backfill if s.id not in qids]
    # Staleness sort — oldest latest-bar first (see module docstring). The
    # backfill group is sorted too (no-data first via date.min) so its chunk
    # composition is deterministic regardless of catalog order.
    incremental.sort(key=lambda s: latest_dates[s.id])
    backfill.sort(key=lambda s: latest_dates.get(s.id) or date.min)
    return FetchPlan(
        incremental=incremental,
        backfill=backfill,
        quarantined=quarantined,
        latest_dates=latest_dates,
    )


def iter_fetch_chunks(
    plan: FetchPlan,
    chunk_size: int,
    *,
    backfill_period: str = "10y",
    today: date | None = None,
) -> Iterator[tuple[list[Stock], str, date | None, str | None]]:
    """Yield (chunk, kind, start, period) fetch units for the plan.

    Incremental chunks first (faster — immediate progress feedback for the
    user), then backfill. Per chunk:

    - KIND_INCREMENTAL → (chunk, kind, start=min(latest of members), None):
      the overlap-by-one-session start for a `fetch_and_upsert(start=...)`.
    - KIND_SKIP        → (chunk, kind, None, None): every member already has
      today's settled bar — advance progress, no fetch (smart-skip).
    - KIND_BACKFILL    → (chunk, kind, None, backfill_period): for a
      `fetch_and_upsert(period=...)` deep download.
    """
    today = today or date.today()
    for i in range(0, len(plan.incremental), chunk_size):
        chunk = plan.incremental[i : i + chunk_size]
        start = min(plan.latest_dates[s.id] for s in chunk)
        if start >= today:
            yield chunk, KIND_SKIP, None, None
        else:
            yield chunk, KIND_INCREMENTAL, start, None
    for i in range(0, len(plan.backfill), chunk_size):
        yield plan.backfill[i : i + chunk_size], KIND_BACKFILL, None, backfill_period
