"""Watchlist request/response schemas."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.stock import StockOut


class WatchlistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    stock_ids: list[int] | None = None


class WatchlistUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None


class WatchlistSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str | None
    item_count: int
    created_at: datetime
    updated_at: datetime


class WatchlistDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str | None
    stocks: list[StockOut]
    created_at: datetime
    updated_at: datetime


class AddItemsRequest(BaseModel):
    stock_ids: list[int] = Field(min_length=1)


class BulkDeleteRequest(BaseModel):
    stock_ids: list[int] = Field(min_length=1)


class AddItemsResponse(BaseModel):
    added: int


class BulkDeleteResponse(BaseModel):
    removed: int
