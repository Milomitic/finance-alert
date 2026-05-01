"""Alerts request/response schemas."""
from datetime import date, datetime
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
