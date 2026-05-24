"""Schemas for the confluence (multi-signal agreement) endpoint."""
from pydantic import BaseModel, ConfigDict


class ConfluenceComponentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    alert_id: int
    rule_kind: str
    signal_name: str
    confidence: float
    tone: str
    signal_date: str | None = None


class ConfluenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ticker: str
    name: str | None = None
    direction: str
    strength: float
    n_signals: int
    bull_strength: float
    bear_strength: float
    contested: bool
    components: list[ConfluenceComponentOut]
