"""Authenticated endpoint for low-cardinality browser Web Vitals RUM."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from prometheus_client import Histogram
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, require_json
from app.models import User

router = APIRouter(prefix="/api/rum", tags=["rum"])

WEB_VITAL = Histogram(
    "finance_alert_web_vital_value",
    "Browser Web Vital measurements reported by authenticated sessions.",
    ["metric", "unit", "route", "device"],
    # LCP/INP are milliseconds; CLS is a 0..1 score. Buckets cover both
    # without high-cardinality labels or unbounded client supplied values.
    buckets=(0.1, 0.25, 0.5, 1, 2, 4, 8, 16, 32, 64, 128, 250, 500, 1000, 2000, 4000, 8000),
)


class WebVitalIn(BaseModel):
    metric: str = Field(pattern=r"^(LCP|INP|CLS)$")
    value: float = Field(ge=0, le=60_000)
    route: str = Field(default="/", min_length=1, max_length=120)
    device: str = Field(pattern=r"^(mobile|desktop)$")


def _route(value: str) -> str:
    # Keep Prometheus cardinality bounded even if a future client sends a
    # dynamic route. Query strings and IDs never belong in a RUM label.
    clean = value.split("?", 1)[0].split("#", 1)[0]
    return clean if clean.startswith("/") else "/"


@router.post("/web-vitals", status_code=202, dependencies=[Depends(require_json)])
def record_web_vital(
    payload: WebVitalIn, _user: User = Depends(get_current_user)
) -> dict[str, str]:
    unit = "score" if payload.metric == "CLS" else "ms"
    WEB_VITAL.labels(
        metric=payload.metric,
        unit=unit,
        route=_route(payload.route),
        device=payload.device,
    ).observe(payload.value)
    return {"status": "accepted"}
