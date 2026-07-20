"""Pydantic schemas for /api/stocks/{ticker}/drawings."""
from pydantic import BaseModel, Field, model_validator


class HorizontalOut(BaseModel):
    id: int
    price: float


class TrendOut(BaseModel):
    id: int
    x1: int
    y1: float
    x2: int
    y2: float


class StockDrawingsOut(BaseModel):
    """Grouped by kind — matches the frontend `StockDrawings` shape so the
    chart can render the two series directly."""
    horizontal: list[HorizontalOut]
    trend: list[TrendOut]


class DrawingCreate(BaseModel):
    """One create body for both kinds; the coordinate fields required depend
    on `kind` (validated below)."""
    kind: str = Field(pattern=r"^(horizontal|trend)$")
    price: float | None = None
    x1: int | None = None
    y1: float | None = None
    x2: int | None = None
    y2: float | None = None

    @model_validator(mode="after")
    def _check_fields(self) -> "DrawingCreate":
        if self.kind == "horizontal":
            if self.price is None:
                raise ValueError("horizontal drawing requires `price`")
        else:  # trend
            if None in (self.x1, self.y1, self.x2, self.y2):
                raise ValueError("trend drawing requires x1, y1, x2, y2")
            if self.x1 == self.x2:
                raise ValueError("trend drawing needs two distinct x coordinates")
        return self


class DrawingCreated(BaseModel):
    id: int
    kind: str
