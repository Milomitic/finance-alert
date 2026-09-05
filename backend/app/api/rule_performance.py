"""Realised-calibration and equity-curve endpoints.

The root route used to serve a per-signal forward-return table replayed from
`ohlcv_daily`, for the Settings "signal effectiveness" panel. That panel now
reads the `signal_outcomes` warehouse via /api/platform/detector-performance,
so the replay had no consumer left and was removed on 2026-09-05 — two
answers to "did the signal work" that disagree by construction is worse than
one. See `rule_performance_service`'s docstring for the reasoning.

What remains: /calibration and /calibration-curve (still read by kpi_service
and the Settings calibration panel) and /equity-curve, which already reads
the warehouse.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import User
from app.services.detector_performance_service import compute_equity_curve
from app.services.rule_performance_service import (
    compute_calibration,
    load_calibration_seed,
)

router = APIRouter(prefix="/api/rule-performance", tags=["rule-performance"])


class EquityPointOut(BaseModel):
    date: str
    equity: float
    equity_mkt_neutral: float


class EquityCurveOut(BaseModel):
    points: list[EquityPointOut]
    n_signals: int
    total_return_pct: float
    mkt_neutral_return_pct: float
    win_rate_pct: float
    avg_return_pct: float
    max_drawdown_pct: float
    horizon_days: int
    detectors: list[str]


@router.get("/equity-curve", response_model=EquityCurveOut)
def get_equity_curve(
    horizon_days: Annotated[int, Query()] = 21,
    detector: str | None = None,
    tone: Annotated[str | None, Query(pattern=r"^(bull|bear)$")] = None,
    regime: Annotated[str | None, Query(pattern=r"^(bull|bear|flat)$")] = None,
    strength_min: Annotated[int | None, Query(ge=0, le=100)] = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> EquityCurveOut:
    """Hypothetical cumulative equity of following every matured signal matching
    the filters. Absolute + market-neutral curves. Growth-of-1 illustration, not
    a tradeable P&L (no overlap/sizing/costs). Reads the signal_outcomes
    warehouse; horizon_days is clamped to a value the warehouse actually holds."""
    if horizon_days not in (5, 21):
        horizon_days = 21
    return EquityCurveOut(
        **compute_equity_curve(
            db,
            horizon_days=horizon_days,
            detector=detector,
            tone=tone,
            regime=regime,
            strength_min=strength_min,
        )
    )


class CalibrationBucketOut(BaseModel):
    label: str
    count: int
    hit_rate: float | None
    mean_pct: float | None
    median_pct: float | None


class CalibrationOut(BaseModel):
    days: int
    window: int
    by_confidence: list[CalibrationBucketOut]
    by_nature: list[CalibrationBucketOut]
    by_horizon: list[CalibrationBucketOut]
    backtest_seed: dict | None = None


@router.get("/calibration", response_model=CalibrationOut)
def get_calibration(
    days: Annotated[int, Query(ge=7, le=730)] = 365,
    window: Annotated[int, Query(ge=1, le=60)] = 20,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> CalibrationOut:
    """Calibration: realized directional hit-rate + forward return by confidence
    bucket and by nature, over `days`, at a `window`-day horizon."""
    c = compute_calibration(db, days=days, window=window)
    return CalibrationOut(
        days=c.days,
        window=c.window,
        by_confidence=[CalibrationBucketOut(**vars(b)) for b in c.by_confidence],
        by_nature=[CalibrationBucketOut(**vars(b)) for b in c.by_nature],
        by_horizon=[CalibrationBucketOut(**vars(b)) for b in c.by_horizon],
        backtest_seed=load_calibration_seed(),
    )


@router.get("/calibration-curve")
def get_calibration_curve(
    _user: User = Depends(get_current_user),
) -> dict:
    """Lightweight: the backtest calibration seed only (hit-rate by confidence x
    horizon), no heavy per-alert recompute. Used to annotate any signal with a
    'calibrated probability'. Empty dict when no seed file is present."""
    return load_calibration_seed() or {}
