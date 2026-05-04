"""Build the 3 spotlight cards for the HomePage dashboard:
- 1x top_gainer (from market snapshot movers.gainers[0])
- 1x most_alerted_7d (from stats_service helper)
- 1x vol_spike (from market snapshot movers.volume_spikes[0])
Each card includes a sparkline (last 30 close)."""
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OhlcvDaily, Stock
from app.services import market_stats_service, stats_service


SPARKLINE_LEN = 30


def _sparkline(db: Session, stock_id: int) -> list[float]:
    bars = list(
        db.execute(
            select(OhlcvDaily)
            .where(OhlcvDaily.stock_id == stock_id)
            .order_by(OhlcvDaily.date.desc())
            .limit(SPARKLINE_LEN)
        ).scalars()
    )
    return [float(b.close) for b in reversed(bars)]


def _stock_id_by_ticker(db: Session, ticker: str) -> int | None:
    # `ticker` è univoco — vedi nota in `services.stock_detail_service.get_detail`.
    s = db.execute(
        select(Stock).where(Stock.ticker == ticker)
    ).scalar_one_or_none()
    return s.id if s else None


def build(db: Session) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    snap = market_stats_service.get_latest_snapshot(db)
    payload: dict[str, Any] = {}
    if snap is not None:
        try:
            payload = json.loads(snap.payload)
        except Exception:
            payload = {}

    movers = payload.get("movers", {}) if payload else {}
    gainers = movers.get("gainers", [])
    if gainers:
        top = gainers[0]
        sid = _stock_id_by_ticker(db, top["ticker"])
        cards.append({
            "type": "top_gainer",
            "ticker": top["ticker"],
            "change_pct": top.get("change_pct"),
            "last_close": top.get("last_close"),
            "sparkline": _sparkline(db, sid) if sid else [],
        })

    losers = movers.get("losers", [])
    if losers:
        top = losers[0]
        sid = _stock_id_by_ticker(db, top["ticker"])
        cards.append({
            "type": "top_loser",
            "ticker": top["ticker"],
            "change_pct": top.get("change_pct"),
            "last_close": top.get("last_close"),
            "sparkline": _sparkline(db, sid) if sid else [],
        })

    most_alerted = stats_service.get_top_alerted_stock_7d(db)
    if most_alerted is not None:
        stock, count = most_alerted
        bars = _sparkline(db, stock.id)
        cards.append({
            "type": "most_alerted_7d",
            "ticker": stock.ticker,
            "alerts_count": count,
            "last_close": bars[-1] if bars else None,
            "sparkline": bars,
        })

    vol_spikes = movers.get("volume_spikes", [])
    if vol_spikes:
        v = vol_spikes[0]
        sid = _stock_id_by_ticker(db, v["ticker"])
        cards.append({
            "type": "vol_spike",
            "ticker": v["ticker"],
            "vol_ratio": v.get("vol_ratio"),
            "last_close": v.get("last_close"),
            "sparkline": _sparkline(db, sid) if sid else [],
        })

    return cards
