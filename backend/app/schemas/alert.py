"""Alerts request/response schemas."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_VALID_KINDS = {"rsi_oversold", "rsi_overbought", "golden_cross", "death_cross"}


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_id: int
    rule_kind: str | None = None  # joined for convenience
    stock_id: int
    ticker: str | None = None  # joined
    name: str | None = None  # joined company name
    triggered_at: datetime
    trigger_price: float
    snapshot: dict[str, Any]
    read_at: datetime | None
    archived_at: datetime | None

    @field_validator("snapshot", mode="before")
    @classmethod
    def parse_snapshot(cls, v: Any) -> dict[str, Any]:
        if isinstance(v, str):
            import json
            return json.loads(v) if v else {}
        return v or {}


class AlertListOut(BaseModel):
    items: list[AlertOut]
    total: int
    has_more: bool


class AlertPatch(BaseModel):
    read: bool | None = None
    archived: bool | None = None


class BulkAction(BaseModel):
    ids: list[int] = Field(min_length=1)
    action: Literal["mark_read", "mark_unread", "archive", "unarchive"]


class BulkResult(BaseModel):
    affected: int


class UnreadCountOut(BaseModel):
    count: int


class ScanRequest(BaseModel):
    stock_ids: list[int] | None = None


class ScanAccepted(BaseModel):
    accepted: bool = True


class DigestResultOut(BaseModel):
    sent: bool
    alerts_count: int
    reason: str | None


class ScanStatusOut(BaseModel):
    """Live status of the most recent scan run.

    `is_running=False, last_run=None` means no scan has ever been triggered.
    """

    is_running: bool
    last_run_id: int | None = None
    trigger: str | None = None  # "cron" | "manual"
    status: str | None = None   # "running" | "success" | "failed"
    phase: str | None = None    # "fetching" | "evaluating" | None when finished
    started_at: datetime | None = None
    completed_at: datetime | None = None
    progress_done: int = 0
    progress_total: int = 0
    stocks_scanned: int | None = None
    stocks_skipped: int | None = None
    alerts_fired: int | None = None
    error_message: str | None = None

