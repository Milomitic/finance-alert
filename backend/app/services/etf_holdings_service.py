"""ETF holdings — top components of an ETF/fund via yfinance funds_data.

Powers the stock-detail "Componenti ETF" view: for an ETF, the trend +
day variation of each underlying holding. `funds_data.top_holdings`
exists only for ETFs/funds (a regular equity raises / returns empty), so
we use it as the ETF detector itself.

Cached in fetch_cache (L2, kind="etf_holdings") with a long TTL — holdings
drift slowly. The NON-ETF result (empty list) is cached too, so a regular
stock isn't re-probed against yfinance on every visit.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from loguru import logger
from sqlalchemy.orm import Session

_KIND = "etf_holdings"
_TTL_SECONDS = 7 * 24 * 3600  # 7 days — holdings move slowly
_MAX_HOLDINGS = 25


@dataclass(frozen=True)
class EtfHolding:
    symbol: str
    name: str
    weight: float  # fraction 0..1 of the fund


def get_holdings(db: Session, ticker: str) -> list[EtfHolding]:
    """Top holdings of `ticker` when it's an ETF/fund; [] otherwise.

    L2-cached (including the empty/non-ETF result) so a regular equity is
    probed against yfinance at most once per TTL window.
    """
    from app.services import fetch_cache_store as fcs

    cached = fcs._read_row(db, ticker, _KIND, _TTL_SECONDS)
    if cached is not None:
        try:
            payload = json.loads(cached[0])
            return [EtfHolding(**h) for h in payload.get("holdings", [])]
        except Exception as e:  # noqa: BLE001 — corrupt row → refetch
            logger.debug(f"[etf_holdings] cache parse failed for {ticker}: {e}")

    holdings = _fetch_from_yf(ticker)
    try:
        fcs._upsert(
            db, ticker, _KIND,
            json.dumps({"holdings": [asdict(h) for h in holdings]}),
        )
    except Exception as e:  # noqa: BLE001 — caching is best-effort
        logger.debug(f"[etf_holdings] cache write failed for {ticker}: {e}")
    return holdings


def _fetch_from_yf(ticker: str) -> list[EtfHolding]:
    """Pull top_holdings from yfinance. Returns [] for non-funds, on the
    yfinance breaker being open, or any error (never raises)."""
    from app.services import yfinance_health

    if yfinance_health.is_open():
        return []
    try:
        import yfinance as yf

        t = yf.Ticker(ticker)
        fd = t.funds_data
        th = fd.top_holdings  # DataFrame: index=Symbol, cols [Name, Holding Percent]
        if th is None or getattr(th, "empty", True):
            return []
        out: list[EtfHolding] = []
        for sym, row in th.head(_MAX_HOLDINGS).iterrows():
            symbol = str(sym).strip().upper()
            if not symbol or symbol in {"NAN", "NONE"}:
                continue
            name = str(row.get("Name") or "").strip()
            try:
                weight = float(row.get("Holding Percent") or 0.0)
            except (TypeError, ValueError):
                weight = 0.0
            out.append(EtfHolding(symbol=symbol, name=name, weight=weight))
        yfinance_health.record_success()
        return out
    except Exception as e:  # noqa: BLE001 — non-ETF / schema drift / network
        logger.debug(f"[etf_holdings] {ticker}: not a fund or fetch failed: {e}")
        return []
