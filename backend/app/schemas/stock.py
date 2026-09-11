"""Stock response schemas."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, computed_field


class IndexOptionOut(BaseModel):
    code: str
    name: str


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
    #: Nella valuta di QUOTAZIONE — yfinance restituisce `marketCap` denominato
    #: nella valuta di scambio. La cifra resta nativa a schermo, coerente con il
    #: prezzo accanto; a ordinare ci pensa `market_cap_usd`.
    market_cap: int | None
    # "equity" | "etf" — lets the UI badge ETF/ETN rows (they carry no
    # fundamental Qualità score by design). Defaulted for back-compat with
    # constructors that predate the column.
    instrument_type: str = "equity"
    # Funds carrying this stock among their LARGEST positions — not full
    # membership. The cache behind it keeps 25 holdings per fund, so SPY's
    # 200th constituent correctly gets nothing here, and the UI must say
    # "top holding of" rather than "in". Empty for ETFs and for anything the
    # cache has not seen. See etf_holdings_service.etfs_containing.
    in_etfs: list[str] = []
    # Index membership, and unlike `in_etfs` this one is COMPLETE: the
    # catalogue tracks every constituent it ingests, so an absent code means
    # "not in that index" and the UI may say "in" without hedging.
    in_indices: list[IndexOptionOut] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def market_cap_usd(self) -> float | None:
        """La stessa capitalizzazione in dollari, per confrontare e ordinare.

        ⚠️ CAMPO CALCOLATO e non colonna, cosi ogni percorso che serve uno
        `StockOut` lo porta con lo stesso significato. Valorizzarlo solo nello
        screener avrebbe dato al `null` due letture diverse — «valuta ignota»
        di la, «non calcolato» altrove — che e la forma di difetto che questo
        repo ha gia pagato con le due tavolozze.

        Senza rete: `to_usd_cached` legge la cache piu la tabella di riserva,
        perche `_get_rate` farebbe una chiamata yfinance per valuta su cache
        fredda. L'import e pigro per non legare gli schemi ai servizi.

        None = valuta mancante o non riconosciuta. Mai parita: assumere USD
        perche il campo e vuoto e un'ipotesi presentata come un fatto.
        """
        from app.services.fx_service import to_usd_cached

        return to_usd_cached(self.market_cap, self.currency)


class StockScoreRefOut(BaseModel):
    """Compact score data joined into the screener row. Either both fields
    are populated (stock has a computed score) or both are None (unscored).
    Mirrors `StockScoreRef` in the service layer."""
    composite: float | None = None
    risk_tier: Literal["conservative", "moderate", "aggressive"] | None = None
    profitability: float | None = None
    sustainability: float | None = None
    growth: float | None = None
    value: float | None = None
    # No momentum: the fundamental Momentum pillar was removed from the
    # composite — the DB column is always NULL, so it was dead payload here.
    sentiment: float | None = None
    # Trend: delta del composite vs lo snapshot score_history (lens qualita)
    # più recente di almeno 7 giorni fa. None con storia insufficiente.
    composite_delta_7d: float | None = None


class TechnicalScoreRefOut(BaseModel):
    """Continuous technical score on the screener row. All None when the stock
    has no technical score yet. Mirrors StockTechRef in the service layer."""
    composite: float | None = None
    trend: float | None = None
    momentum: float | None = None
    structure: float | None = None
    volume: float | None = None
    rel_strength: float | None = None
    signals: float | None = None
    posture: str | None = None


class StockMetricsRefOut(BaseModel):
    """EOD price/volume metrics on the screener row (from stock_metrics). All
    None when the stock has no metrics row yet. Mirrors StockMetricsRef."""
    last_close: float | None = None
    change_pct: float | None = None
    ema50: float | None = None
    ema200: float | None = None
    rsi14: float | None = None
    high_252: float | None = None
    low_252: float | None = None
    vol_ratio: float | None = None
    # Raw volume pair behind vol_ratio: today's share count + 20-bar average.
    vol_today: float | None = None
    vol_avg_20: float | None = None


class StockSearchItemOut(BaseModel):
    """A row in the screener result. Carries the Stock anagrafica + the
    optional score join. Splitting score into a sub-object (vs flattening
    onto StockOut) keeps the bare `StockOut` lean for endpoints that don't
    need scoring data (`GET /api/stocks/{ticker}` etc.)."""
    stock: StockOut
    score: StockScoreRefOut
    technical: TechnicalScoreRefOut = TechnicalScoreRefOut()
    metrics: StockMetricsRefOut = StockMetricsRefOut()


class StockSearchOut(BaseModel):
    items: list[StockSearchItemOut]
    total: int
    has_more: bool
    # As-of of the last stock_metrics refresh (one value for the whole
    # table — every row of a refresh shares a computed_at). None when no
    # scan has persisted metrics yet. UTC, ISO-serialized.
    metrics_computed_at: datetime | None = None


class FilterOptionsOut(BaseModel):
    exchanges: list[str]
    sectors: list[str]
    industries: list[str]
    countries: list[str]
    indices: list[IndexOptionOut]
