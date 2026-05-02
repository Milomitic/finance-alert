"""Pydantic schemas for /api/.../price-alerts."""
from datetime import datetime

from pydantic import BaseModel, Field


class PriceAlertOut(BaseModel):
    id: int
    stock_id: int
    target_price: float
    direction: str
    enabled: bool
    note: str | None
    triggered_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PriceAlertCreate(BaseModel):
    target_price: float = Field(gt=0)
    direction: str = Field(pattern=r"^(above|below)$")
    note: str | None = Field(default=None, max_length=255)


class PriceAlertUpdate(BaseModel):
    enabled: bool | None = None
    target_price: float | None = Field(default=None, gt=0)
    direction: str | None = Field(default=None, pattern=r"^(above|below)$")
    note: str | None = Field(default=None, max_length=255)
