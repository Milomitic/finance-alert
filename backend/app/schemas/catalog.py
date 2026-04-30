"""Catalog refresh schemas."""
from datetime import datetime

from pydantic import BaseModel


class RefreshRequest(BaseModel):
    index_code: str | None = None


class RefreshAccepted(BaseModel):
    accepted: bool = True


class IndexStatusOut(BaseModel):
    index_code: str
    last_started_at: datetime | None
    last_completed_at: datetime | None
    last_status: str | None
    stocks_added: int | None
    stocks_updated: int | None
    stocks_removed: int | None
    error_message: str | None


class CatalogStatusOut(BaseModel):
    indices: list[IndexStatusOut]
