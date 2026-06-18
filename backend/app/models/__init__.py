"""Aggregate model imports so Alembic sees them."""
from app.models.alert import Alert
from app.models.catalog_log import CatalogRefreshLog
from app.models.fetch_cache import FetchCache
from app.models.index import Index, StockIndex
from app.models.kpi_snapshot import KpiSnapshot
from app.models.institutional import (
    Institutional,
    InstitutionalFiling,
    InstitutionalHolding,
)
from app.models.macro import MacroObservation, MacroReleaseDate, MacroSeries
from app.models.market_snapshot import MarketSnapshot
from app.models.ohlcv import OhlcvDaily
from app.models.price_alert import PriceAlert
from app.models.scan_run import ScanRun
from app.models.score_history import ScoreHistory
from app.models.signal_outcome import SignalOutcome
from app.models.stock import Stock
from app.models.stock_metrics import StockMetrics
from app.models.stock_score import StockScore
from app.models.technical_score import TechnicalScore
from app.models.user import User

__all__ = [
    "User",
    "Stock",
    "StockMetrics",
    "StockScore",
    "TechnicalScore",
    "Index",
    "StockIndex",
    "CatalogRefreshLog",
    "OhlcvDaily",
    "MarketSnapshot",
    "Alert",
    "PriceAlert",
    "ScanRun",
    "SignalOutcome",
    "ScoreHistory",
    "KpiSnapshot",
    "FetchCache",
    "MacroSeries",
    "MacroObservation",
    "MacroReleaseDate",
    "Institutional",
    "InstitutionalFiling",
    "InstitutionalHolding",
]
