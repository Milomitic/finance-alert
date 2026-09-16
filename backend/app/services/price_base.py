"""L'ultima chiusura memorizzata: la base di ogni upside mostrato a schermo.

Proprietario unico. La scheda Stock Score e la scheda Analyst calcolavano lo
stesso upside da due prezzi diversi — l'ultima barra di `ohlcv_daily` e
`price_target.current` di yfinance, vecchio quanto la cache dei fondamentali —
e mostravano due percentuali dello stesso target a pochi centimetri
(`tests/test_base_prezzo_unica_fra_schede.py`).

La chiusura memorizzata e' la base giusta per entrambe perche' non dipende da
niente di remoto: nessun breaker, nessuno stato STALE. La DATA viaggia col
prezzo, perche' un upside su una chiusura di quattro giorni fa e' un numero
diverso da uno su quella di ieri.
"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OhlcvDaily


def last_close(db: Session, stock_id: int) -> tuple[float, date] | None:
    """(chiusura, data) dell'ultima barra giornaliera, o None senza barre."""
    row = db.execute(
        select(OhlcvDaily.close, OhlcvDaily.date)
        .where(OhlcvDaily.stock_id == stock_id)
        .order_by(OhlcvDaily.date.desc())
        .limit(1)
    ).first()
    if row is None or row[0] is None:
        return None
    return float(row[0]), row[1]
