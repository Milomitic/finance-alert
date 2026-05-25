"""Signal hit-rate / forward-return statistics endpoint.

Reads from `services/rule_performance_service`. Used by the Settings
page (Fase 3E) to render a "signal effectiveness" table.
The `rule_kind` field in the response now carries a "signal:<name>"
string — the field name is kept stable to avoid frontend churn.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import User
from app.services.rule_performance_service import compute_calibration, compute_performance, load_calibration_seed
from pydantic import BaseModel

router = APIRouter(prefix="/api/rule-performance", tags=["rule-performance"])


class WindowStatsOut(BaseModel):
    count: int
    mean_pct: float | None
    median_pct: float | None
    hit_rate: float | None  # 0..1


class RulePerformanceOut(BaseModel):
    rule_kind: str
    tone: str
    total_alerts: int
    # Map window_days (as string for JSON) -> stats. Using string keys
    # keeps the payload introspection-friendly in the UI; the frontend
    # casts back to int when picking a window.
    stats: dict[str, WindowStatsOut]


class RulePerformanceListOut(BaseModel):
    days: int
    items: list[RulePerformanceOut]


@router.get("", response_model=RulePerformanceListOut)
def list_rule_performance(
    days: Annotated[int, Query(ge=7, le=365)] = 90,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> RulePerformanceListOut:
    """Returns one row per signal_name that fired in the last `days`
    days, with forward-return stats over 1d / 5d / 20d windows.
    The `rule_kind` field carries a "signal:<name>" string."""
    perf = compute_performance(db, days=days)
    return RulePerformanceListOut(
        days=days,
        items=[
            RulePerformanceOut(
                rule_kind=p.rule_kind,
                tone=p.tone,
                total_alerts=p.total_alerts,
                stats={
                    str(w): WindowStatsOut(
                        count=s.count,
                        mean_pct=s.mean_pct,
                        median_pct=s.median_pct,
                        hit_rate=s.hit_rate,
                    )
                    for w, s in p.stats.items()
                },
            )
            for p in perf
        ],
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
