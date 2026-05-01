"""Rules request/response schemas."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


_VALID_KINDS = {"rsi_oversold", "rsi_overbought", "golden_cross", "death_cross"}


class RuleBase(BaseModel):
    kind: str
    params: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

    @field_validator("kind")
    @classmethod
    def kind_must_be_known(cls, v: str) -> str:
        if v not in _VALID_KINDS:
            raise ValueError(f"unknown rule kind: {v}")
        return v


class RuleCreate(RuleBase):
    watchlist_id: int | None = None  # None for Tier 1


class RuleUpdate(BaseModel):
    enabled: bool | None = None
    params: dict[str, Any] | None = None


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    watchlist_id: int | None
    kind: str
    params: dict[str, Any]
    enabled: bool
    created_at: datetime
    updated_at: datetime

    @field_validator("params", mode="before")
    @classmethod
    def parse_params(cls, v: Any) -> dict[str, Any]:
        # Backend stores params as JSON string in TEXT column
        if isinstance(v, str):
            import json
            return json.loads(v) if v else {}
        return v or {}
