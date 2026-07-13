"""Batch recompute: the recompute_all entry point wired to ScanRun progress
(heartbeats, phase changes, cooperative cancel). Includes the ETF skip +
stale-score purge (Lane F, B4-7).
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Stock, StockScore
from app.services.score_service.build import compute_score
from app.services.score_service.common import RecomputeCancelled
from app.services.score_service.loaders import _bulk_load_recent_bars
from app.services.score_service.sector_stats import _build_sector_stats
from app.services.score_service.xs_engine import _apply_cross_sectional_engine
from app.services.sectors_overview_cache import clear_overview_cache


def recompute_all(
    db: Session,
    *,
    on_progress=None,
    on_phase_change=None,
    progress_every: int = 10,
    cancel_check=None,
) -> tuple[int, int]:
    """Batch UPSERT scores for every stock. Returns (ok, failed).

    Earlier versions (yesterday, May 2026 morning) carried an
    incremental-skip optimisation that compared `score.computed_at`
    against `fundamentals.fetched_at` + `max(ohlcv.date)` and skipped
    stocks whose inputs hadn't moved. We removed it because:

      1. Manual user trigger ("Ricalcola score" on the homepage) was
         the painful case — consecutive clicks reported "1097 saltati,
         0 processati" because the inputs hadn't budged since the
         previous run. Felt broken even though it was technically
         correct.
      2. The automatic post-scan path didn't actually benefit much:
         every scan adds new OHLCV bars before triggering this, so on
         a fresh scan the skip-decision returns False for ~everyone
         anyway. The savings only materialised on consecutive same-
         day re-scans with no new bars — a real but narrow case.
      3. The supporting code (3 aggregate SQL queries + a 35-line
         decision function + a class to thread the state) was ~100
         LOC of cognitive overhead for the ~3s saving in the narrow
         case.

    Going forward every call re-scores every stock. The sector_stats
    pre-pass + per-stock compute_score remain unchanged.

    Two-phase to use *real* sector medians instead of static V1 values:
      1. Pre-pass: collect fundamentals (cache hit on the fast path) →
         compute sector_stats bundle (medians of P/E, P/B, ROE, growth,
         margins per sector + universe fallback).
      2. Score loop: pass the bundle to each compute_score so the
         value/quality/growth pillars benchmark each stock against its
         peer median rather than the hardcoded baseline.

    Persists incrementally (commit after each successful score) and uses
    `db.merge()` for true UPSERT semantics.

    Does NOT raise on per-stock failure — logs and continues.

    Progress + cancel hooks (added so the user-triggered "Ricalcola score"
    flow can drive the same persistent-toast UX as a scan):
      - `on_progress(done, total)` fires per heartbeat with the appropriate
        denominator for the active phase. During the sector_stats pre-pass
        `total` is the unique-sectors count and `done` advances from 0→N
        proportional to the per-stock aggregation progress (so the bar
        actually moves during the pre-pass — pre-May-2026 it sat at 0/N
        which was confusing). During the scoring loop `total` is the
        stock count and `done` is stocks scored.
      - `on_phase_change(phase)` fires once per phase transition with
        either "sector_stats" or "scoring". Runners use this to drive
        the toast's phase label + reset its per-phase ETA timer. Without
        this callback the runner used to flip phase based on `done > 0`,
        but that conflicts with the new "done moves during pre-pass too"
        behaviour.
      - `cancel_check()` is polled every stock during pre-pass + every
        `progress_every` stocks during scoring; returning True raises
        `RecomputeCancelled` from inside the loop.
    All three default to no-op when omitted — keeps the cron call-sites
    untouched.
    """
    all_stocks = db.execute(select(Stock)).scalars().all()

    # ETF/ETN rows carry no meaningful fundamentals — a composite computed
    # from a near-empty micro payload is noise (the TZA 66.8 case), so the
    # Qualità lens skips instrument_type='etf' entirely. Besides not writing
    # a new StockScore row, we DELETE any stale row a pre-flag recompute
    # left behind: stock_scores is the substrate of the sector/universe
    # composite percentiles (scores._composite_percentiles) and of the
    # xs-engine cross-section, so purging here makes ETFs drop out of both
    # automatically. The Tecnico lens (technical_score_service) still runs
    # for ETFs — price-action posture is meaningful for them.
    etf_ids = [s.id for s in all_stocks if s.instrument_type == "etf"]
    stocks = [s for s in all_stocks if s.instrument_type != "etf"]
    if etf_ids:
        purged = db.execute(
            delete(StockScore).where(StockScore.stock_id.in_(etf_ids))
        ).rowcount
        db.commit()
        if purged:
            logger.info(
                f"[score] purged {purged} stale ETF score rows "
                f"({len(etf_ids)} ETFs skipped by recompute)"
            )
    total = len(stocks)

    # Count unique sectors so the pre-pass progress bar can render
    # "K/N sectors" with N = real-world denominator the user expects
    # (~12 GICS top-level sectors). Without this the bar would either
    # sit at 0/total_stocks (pre-2026) or 0/0 (no useful denominator).
    sector_count = len({s.sector for s in stocks if s.sector}) or 1

    # Phase transition: pre-pass begins.
    if on_phase_change is not None:
        on_phase_change("sector_stats")
    # Seed total = sector_count so the toast immediately renders the
    # right denominator. `done=0` at start; the pre-pass heartbeat
    # below interpolates the stock-level progress onto sector units.
    if on_progress is not None:
        on_progress(0, sector_count)

    # Pre-pass: build sector_stats. Cost is usually negligible (L1/L2
    # cache for ~889 tickers, ~50ms) BUT can spike to 30s+ when delisted
    # tickers force yfinance retries. Thread `on_heartbeat` + `cancel_check`
    # through so the runner can keep its ScanRun row's heartbeat fresh
    # during the slow loop — without it the stale detector (>120s)
    # force-closes the row before the score loop ever starts.
    def _prepass_heartbeat(done_stocks: int, total_stocks: int) -> None:
        if on_progress is None:
            return
        # Linear interpolate the per-stock progress onto the sector
        # denominator. The actual sector_stats compute() runs all-at-
        # once at the very end of the pre-pass, but the user reads
        # "calcolo mediane settoriali" as "N sectors being processed"
        # — the interpolation matches that mental model and lets the
        # bar actually move during the ~5-30s pre-pass wall time.
        denom = max(1, total_stocks)
        sectors_done = min(sector_count, int(done_stocks / denom * sector_count))
        on_progress(sectors_done, sector_count)

    sector_stats = _build_sector_stats(
        list(stocks),
        on_heartbeat=_prepass_heartbeat,
        cancel_check=cancel_check,
    )

    # Phase transition: scoring begins. Total flips from sector_count
    # to total_stocks (the bar visually resets from 100% pre-pass to
    # 0% of scoring — same UX as a multi-step installer).
    if on_phase_change is not None:
        on_phase_change("scoring")
    if on_progress is not None:
        on_progress(0, total)

    # Bulk-load all recent OHLCV bars in ONE SELECT instead of the
    # per-stock pair (`_load_closes` + `_load_ohlcv_df`). Empirical: on
    # ~1100 stocks the old path spent ~13-33s of cumulative SELECT time;
    # the bulk version is ~80-150ms total. The 400-day window covers
    # the 260 trading days that compute_score's indicators need.
    bars_by_stock = _bulk_load_recent_bars(db, days_back=400)

    seen_ids: set[int] = set()
    ok = 0
    failed = 0
    # Commit batching: one fsync per N stocks instead of per-stock saves
    # ~3-10ms × N. We keep N small enough that a Stop click only loses
    # the in-flight batch (~50 stocks of work, <1s on the fast path).
    BATCH_COMMIT_EVERY = 50
    pending_in_batch = 0

    for i, stock in enumerate(stocks):
        # Cooperative cancel: polled EVERY stock (cheap set lookup) so
        # Stop reacts within one stock of the user click — even when
        # individual compute_score calls are slow (e.g. fundamentals
        # cache miss triggering a yfinance retry chain). The cost of
        # the check itself is negligible vs the per-stock work.
        if cancel_check is not None and cancel_check():
            # Flush any pending batch before raising so partial progress
            # is persisted (not strictly necessary — the runner marks
            # the run failed anyway — but cheap and helpful for debug).
            if pending_in_batch > 0:
                try:
                    db.commit()
                except Exception:  # noqa: BLE001
                    db.rollback()
            raise RecomputeCancelled()
        if stock.id in seen_ids:
            continue
        seen_ids.add(stock.id)

        try:
            new_score = compute_score(
                db,
                stock,
                sector_stats=sector_stats,
                bars=bars_by_stock.get(stock.id),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[score] compute_score failed for {stock.ticker}: {exc}")
            failed += 1
            continue
        try:
            db.merge(new_score)
            ok += 1
            pending_in_batch += 1
            # Commit batch when the threshold hits — eliminates ~95% of
            # the fsync overhead on the recompute loop.
            if pending_in_batch >= BATCH_COMMIT_EVERY:
                db.commit()
                pending_in_batch = 0
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[score] persist failed for {stock.ticker}: {exc}")
            db.rollback()
            pending_in_batch = 0
            failed += 1
        # Heartbeat every `progress_every` stocks (and once at the end).
        if on_progress is not None and (i % progress_every == 0 or i == total - 1):
            on_progress(i + 1, total)

    # Final flush — the tail < BATCH_COMMIT_EVERY won't trigger a commit
    # inside the loop, so make sure those rows land before we return.
    if pending_in_batch > 0:
        try:
            db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[score] final batch commit failed: {exc}")
            db.rollback()

    # M4+M5 — cross-sectional sector-neutral re-ranking + coverage
    # shrinkage. Runs once over the just-persisted cross-section.
    # Non-fatal: v1 scores are already committed; a failure here only
    # skips the (flag-gated) xs annotation.
    try:
        _apply_cross_sectional_engine(db, list(stocks))
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[score] xs-engine skipped (non-fatal): {exc}")
        db.rollback()

    # Post-recompute hook: drop the memoized /sectors overview payload so
    # the hub page reflects the fresh composites immediately instead of
    # serving pre-recompute averages for up to a TTL. The cache lives in
    # `services.sectors_overview_cache` (not the API router) precisely so
    # this call doesn't create a service→API import cycle.
    clear_overview_cache()

    logger.info(
        f"[score] recompute_all: ok={ok} failed={failed} (of {total} stocks)"
    )
    return ok, failed
