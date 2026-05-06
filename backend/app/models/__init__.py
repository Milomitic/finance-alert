"""Aggregate model imports so Alembic sees them."""
from app.models.alert import Alert
from app.models.catalog_log import CatalogRefreshLog
from app.models.fetch_cache import FetchCache
from app.models.index import Index, StockIndex
from app.models.macro import MacroObservation, MacroReleaseDate, MacroSeries
from app.models.market_snapshot import MarketSnapshot
from app.models.ohlcv import OhlcvDaily
from app.models.price_alert import PriceAlert
from app.models.rule import Rule, RuleState
from app.models.scan_run import ScanRun
from app.models.stock import Stock
from app.models.stock_score import StockScore
from app.models.user import User
from app.models.watchlist import Watchlist, WatchlistItem

__all__ = [
    "User",
    "Stock",
    "StockScore",
    "Index",
    "StockIndex",
    "Watchlist",
    "WatchlistItem",
    "CatalogRefreshLog",
    "OhlcvDaily",
    "MarketSnapshot",
    "Rule",
    "RuleState",
    "Alert",
    "PriceAlert",
    "ScanRun",
    "FetchCache",
    "MacroSeries",
    "MacroObservation",
    "MacroReleaseDate",
]
