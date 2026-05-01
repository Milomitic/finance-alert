"""Aggregate model imports so Alembic sees them."""
from app.models.alert import Alert
from app.models.catalog_log import CatalogRefreshLog
from app.models.index import Index, StockIndex
from app.models.ohlcv import OhlcvDaily
from app.models.rule import Rule, RuleState
from app.models.scan_run import ScanRun
from app.models.stock import Stock
from app.models.user import User
from app.models.watchlist import Watchlist, WatchlistItem

__all__ = [
    "User",
    "Stock",
    "Index",
    "StockIndex",
    "Watchlist",
    "WatchlistItem",
    "CatalogRefreshLog",
    "OhlcvDaily",
    "Rule",
    "RuleState",
    "Alert",
    "ScanRun",
]
