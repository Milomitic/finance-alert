"""Stock response schemas."""
from pydantic import BaseModel, ConfigDict


class StockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ticker: str
    exchange: str
    name: str
    sector: str | None
    industry: str | None
    country: str | None
    currency: str | None
    market_cap: int | None


class StockSearchOut(BaseModel):
    items: list[StockOut]
    total: int
    has_more: bool


class IndexOptionOut(BaseModel):
    code: str
    name: str


class FilterOptionsOut(BaseModel):
    exchanges: list[str]
    sectors: list[str]
    countries: list[str]
    indices: list[IndexOptionOut]
