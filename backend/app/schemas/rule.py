"""Rules request/response schemas.

The watchlist feature (Tier 2 per-watchlist rule overrides) was
removed in May 2026 — every rule is now global. The `watchlist_id`
field is gone from create/update/out schemas.
"""
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_VALID_KINDS = {
    "rsi_oversold", "rsi_overbought", "golden_cross", "death_cross",
    "volume_spike", "breakout",
    "macd_bullish_cross", "macd_bearish_cross",
    "bollinger_breakout",
    # Desk/trader signals (added when bollinger_squeeze was retired —
    # see Alembic migration 47c2035665bd_drop_bollinger_squeeze_rules):
    "adx_bullish_trend", "adx_bearish_trend",
    "gap_up", "gap_down",
    "mean_reversion_long", "mean_reversion_short",
    "composite",
}


class RuleBase(BaseModel):
    kind: str
    params: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    expression: dict[str, Any] | None = None

    @field_validator("kind")
    @classmethod
    def kind_must_be_known(cls, v: str) -> str:
        if v not in _VALID_KINDS:
            raise ValueError(f"unknown rule kind: {v}")
        return v

    @model_validator(mode="after")
    def expression_structure_valid(self) -> "RuleBase":
        if self.expression is None:
            return self
        from app.rules.composite import validate_expression
        try:
            validate_expression(self.expression)
        except ValueError as e:
            raise ValueError(str(e)) from e
        return self


class RuleCreate(RuleBase):
    pass


class RuleUpdate(BaseModel):
    kind: str | None = None
    enabled: bool | None = None
    params: dict[str, Any] | None = None
    expression: dict[str, Any] | None = None

    @field_validator("kind")
    @classmethod
    def kind_must_be_known(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in _VALID_KINDS:
            raise ValueError(f"unknown rule kind: {v}")
        return v

    @model_validator(mode="after")
    def expression_structure_valid(self) -> "RuleUpdate":
        if self.expression is None:
            return self
        from app.rules.composite import validate_expression
        try:
            validate_expression(self.expression)
        except ValueError as e:
            raise ValueError(str(e)) from e
        return self


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    params: dict[str, Any]
    enabled: bool
    expression: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("params", mode="before")
    @classmethod
    def parse_params(cls, v: Any) -> dict[str, Any]:
        if isinstance(v, str):
            return json.loads(v) if v else {}
        return v or {}

    @field_validator("expression", mode="before")
    @classmethod
    def parse_expression(cls, v: Any) -> dict[str, Any] | None:
        if v is None:
            return None
        if isinstance(v, str):
            return json.loads(v) if v else None
        return v
