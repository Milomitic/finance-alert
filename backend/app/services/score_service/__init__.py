"""Composite stock-scoring service (V2 — comprehensive + missing-data neutral).

Per-stock 0-100 score from the 5 PURE-FUNDAMENTAL pillars: Profitability,
Sustainability, Growth, Value, Sentiment (the Momentum pillar was removed in
the 2026-05 3-lens cleanup — price-action lives in TechnicalScore). The DB
row schema (StockScore.composite/quality/growth/value/momentum/sentiment/
risk_tier/breakdown) is unchanged from V1; `momentum` persists as NULL.

What's different from V1
------------------------

1. **Comprehensive coverage.** Each pillar now consumes a much richer set of
   inputs from MicroData / Fundamentals / OHLCV / cached news, instead of
   the 3-5 inputs V1 used. See per-pillar docstrings for the full list.

2. **Missing-data neutralization.** V1 awarded zero points for any missing
   component but kept its weight in the denominator — so a stock with no
   PEG ratio (a data gap, not a quality issue) lost 30% of its Value
   pillar. V2 changes this: a component whose input is missing/None is
   excluded from BOTH numerator and denominator. The pillar score is the
   weighted average of only the components we actually have data for.

   Algorithm (per pillar):
       pillar_score = sum(score_i * weight_i for i in present)
                    / sum(weight_i           for i in present)
   where score_i ∈ [0, 100] and weight_i is a relative weight.
   If no components are present → pillar = None (excluded from composite,
   composite-level renormalisation handles the rest, same as V1).

3. **Pillar-level renormalisation kept.** When a pillar is fully absent
   (all components missing), it's dropped from the composite and the other
   pillars' weights are renormalised to sum to 1.0 — exactly as V1.

The recompute_all batch is called at the end of every successful scan run
(see scan_runner.run_tracked_scan) and after warmup_fundamentals — both
non-fatal so a score crash doesn't take down the upstream pipeline.

Package layout (B4-9 split of the former 2,700-line module — mechanical
decomposition, zero behavior change):

    common.py         pillar weights, static sector benchmarks, ramp/blend
                      curves, _Component/_aggregate machinery,
                      RecomputeCancelled
    pillars.py        the 5 pillar computations + lane helpers + the
                      _quality back-compat shim + news-sentiment helpers
    risk.py           _classify_risk + the M2 risk-overlay factor
    loaders.py        OHLCV loaders (per-stock + bulk), 90d vol, news count
    build.py          _renormalize_weights, _build_score, M3 turnover
                      control, compute_score
    sector_stats.py   fingerprint-cached sector-medians pre-pass
    xs_engine.py      M4/M5 cross-sectional sector-neutral re-ranking
    recompute.py      recompute_all (progress/cancel wiring + ETF purge)
    quality_extras.py read-time governance/analyst enrichment

This __init__ re-exports the historical public surface so `from app.services
import score_service` consumers (routers, runners, scripts, tests — including
`monkeypatch.setattr("...score_service.compute_score", ...)` targets, which
patch attributes ON this module object) keep working unchanged.
"""
from __future__ import annotations

from app.services.score_service.build import (
    _EWMA_ALPHA,
    _apply_turnover_control,
    _build_score,
    _ComputedScore,
    _renormalize_weights,
    compute_score,
)
from app.services.score_service.common import (
    PILLAR_WEIGHTS,
    RISK_TIERS,
    RecomputeCancelled,
    _aggregate,
    _blended_hib,
    _blended_lib,
    _blended_lib_multiple,
    _Component,
    _is_finite,
    _ramp,
    _ramp3,
    _resolve_med,
    _safe_round,
)
from app.services.score_service.loaders import (
    _bulk_load_recent_bars,
    _compute_volatility_90d,
    _last_30d_news_count,
    _load_closes,
    _load_ohlcv_df,
)
from app.services.score_service.pillars import (
    _aggregate_news_sentiment,
    _dividend_coverage,
    _earnings_stability_5y,
    _fcf_to_ni_ratio,
    _growth,
    _margin_trend_3y,
    _net_upgrades_90d,
    _profitability,
    _quality,
    _sentiment,
    _sustainability,
    _value,
)
from app.services.score_service.quality_extras import quality_extras
from app.services.score_service.recompute import recompute_all
from app.services.score_service.risk import _classify_risk, _risk_overlay_factor
from app.services.score_service.sector_stats import (
    _SECTOR_STATS_CACHE,
    _build_sector_stats,
    _sector_stats_cache_key,
    clear_sector_stats_cache,
)
from app.services.score_service.xs_engine import (
    _apply_cross_sectional_engine,
    _avg_rank_pct,
)

__all__ = [
    # public surface
    "PILLAR_WEIGHTS",
    "RISK_TIERS",
    "RecomputeCancelled",
    "clear_sector_stats_cache",
    "compute_score",
    "quality_extras",
    "recompute_all",
    # internals kept importable for tests/diagnostics (historical surface)
    "_EWMA_ALPHA",
    "_SECTOR_STATS_CACHE",
    "_Component",
    "_ComputedScore",
    "_aggregate",
    "_aggregate_news_sentiment",
    "_apply_cross_sectional_engine",
    "_apply_turnover_control",
    "_avg_rank_pct",
    "_blended_hib",
    "_blended_lib",
    "_blended_lib_multiple",
    "_build_score",
    "_build_sector_stats",
    "_bulk_load_recent_bars",
    "_classify_risk",
    "_compute_volatility_90d",
    "_dividend_coverage",
    "_earnings_stability_5y",
    "_fcf_to_ni_ratio",
    "_growth",
    "_is_finite",
    "_last_30d_news_count",
    "_load_closes",
    "_load_ohlcv_df",
    "_margin_trend_3y",
    "_net_upgrades_90d",
    "_profitability",
    "_quality",
    "_ramp",
    "_ramp3",
    "_renormalize_weights",
    "_resolve_med",
    "_risk_overlay_factor",
    "_safe_round",
    "_sector_stats_cache_key",
    "_sentiment",
    "_sustainability",
    "_value",
]
