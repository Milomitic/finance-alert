"""I titoli con la serie ferma (delistati) escono dagli ELENCHI, non dall'app.

Su richiesta, 2026-10-06: CTRA, APLS, TERN, SATS, VSCO e CPRX non quotano piu'
da mesi e comparivano nello screener coi prezzi di allora. I loro dati restano
per le statistiche, e la pagina del titolo resta raggiungibile dai vecchi alert.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.visibility import negli_elenchi_clause, visible_country_clause
from app.models import Stock
from app.models.ohlcv import OhlcvDaily
from app.services import stock_detail_service, stock_service
from app.services.ohlcv_service import QUARANTINE_STREAK


def _titolo(db: Session, ticker: str, streak: int) -> Stock:
    s = Stock(ticker=ticker, exchange="NYSE", country="US", name=f"Prova {ticker}",
              ohlcv_nodata_streak=streak)
    db.add(s)
    db.flush()
    oggi = date.today()
    for i in range(5):
        p = 10.0 + i
        db.add(OhlcvDaily(stock_id=s.id, date=oggi - timedelta(days=10 - i),
                          open=p, high=p, low=p, close=p, volume=1000))
    db.commit()
    return s


def test_il_predicato_toglie_le_serie_ferme_e_basta(db: Session) -> None:
    _titolo(db, "VIVO", 0)
    _titolo(db, "MORTO", QUARANTINE_STREAK + 5)
    # Controllo negativo: appena sotto la soglia della serie ferma resta.
    _titolo(db, "INCERTO", QUARANTINE_STREAK - 1)
    elenco = set(db.scalars(select(Stock.ticker).where(negli_elenchi_clause())))
    assert elenco == {"VIVO", "INCERTO"}
    # Il predicato per paese da solo li vede tutti: la differenza e' la serie.
    assert set(db.scalars(select(Stock.ticker).where(visible_country_clause()))) == {"VIVO", "MORTO", "INCERTO"}


def test_lo_screener_non_li_mostra(db: Session) -> None:
    _titolo(db, "VIVO", 0)
    _titolo(db, "MORTO", 400)
    pagina = stock_service.search_stocks(db, stock_service.StockFilter())
    assert {r.stock.ticker for r in pagina.items} == {"VIVO"}
    # Nemmeno cercandolo per nome.
    cercato = stock_service.search_stocks(db, stock_service.StockFilter(q="MORTO"))
    assert cercato.items == []


def test_la_pagina_del_titolo_resta_raggiungibile(db: Session) -> None:
    """I suoi vecchi alert ci portano: un 404 li romperebbe."""
    _titolo(db, "MORTO", 400)
    assert stock_detail_service.get_detail(db, "MORTO") is not None
