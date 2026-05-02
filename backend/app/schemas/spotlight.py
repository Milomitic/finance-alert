"""Pydantic schemas for /api/dashboard/spotlight."""
from typing import Literal

from pydantic import BaseModel


class SpotlightCardOut(BaseModel):
    type: Literal["top_gainer", "most_alerted_7d", "vol_spike"]
    ticker: str
    last_close: float | None = None
    sparkline: list[float] = []
    change_pct: float | None = None
    vol_ratio: float | None = None
    alerts_count: int | None = None


class SpotlightOut(BaseModel):
    cards: list[SpotlightCardOut]
