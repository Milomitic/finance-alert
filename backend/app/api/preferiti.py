"""I titoli preferiti (FA-112): la stella sulla pagina titolo, la striscia in home."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_json
from app.models import Stock, User
from app.services import preferiti_service

router = APIRouter(prefix="/api/preferiti", tags=["preferiti"])


class PreferitoOut(BaseModel):
    stock_id: int
    ticker: str
    name: str
    exchange: str
    currency: str | None = None
    instrument_type: str | None = None
    aggiunto_il: datetime
    #: "manuale" | "etoro" (da una watchlist eToro, FA-125).
    origine: str = "manuale"


def _out(stock: Stock, aggiunto_il: datetime, origine: str) -> PreferitoOut:
    return PreferitoOut(
        stock_id=stock.id, ticker=stock.ticker, name=stock.name, exchange=stock.exchange,
        currency=stock.currency, instrument_type=stock.instrument_type,
        aggiunto_il=aggiunto_il, origine=origine,
    )


@router.get("", response_model=list[PreferitoOut])
def elenco(
    db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> list[PreferitoOut]:
    return [_out(s, a, o) for s, a, o in preferiti_service.elenco(db)]


@router.put("/{ticker}", response_model=PreferitoOut, dependencies=[Depends(require_json)])
def aggiungi(
    ticker: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> PreferitoOut:
    esito = preferiti_service.aggiungi(db, ticker)
    if esito is None:
        raise HTTPException(status_code=404, detail=f"{ticker} non e' nel catalogo")
    return _out(*esito)


@router.delete("/{ticker}", status_code=204, dependencies=[Depends(require_json)])
def togli(
    ticker: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> Response:
    preferiti_service.togli(db, ticker)
    return Response(status_code=204)
