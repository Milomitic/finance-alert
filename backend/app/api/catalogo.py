"""La verifica sulla fonte di un titolo fermo (2026-09-29).

L'elenco dei fermi viaggia nello snapshot di `/api/platform/health`; qui c'e'
solo l'azione che va in rete, un titolo alla volta e solo su richiesta. Vedi
`catalogo_fermi_service`.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_json
from app.models import Stock, User
from app.services import catalogo_fermi_service

router = APIRouter(prefix="/api/catalogo", tags=["catalogo"])


class CandidatoOut(BaseModel):
    simbolo: str
    borsa: str | None = None
    tipo: str | None = None
    nome: str | None = None


class VerificaFonteOut(BaseModel):
    ticker: str
    barre_recenti: int | None
    ultima_barra_fonte: date | None
    candidati: list[CandidatoOut]
    errore: str | None = None


@router.post(
    "/fermi/{ticker}/verifica",
    response_model=VerificaFonteOut,
    dependencies=[Depends(require_json)],
)
def verifica_fonte(
    ticker: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> VerificaFonteOut:
    stock = db.execute(select(Stock).where(Stock.ticker == ticker).limit(1)).scalars().first()
    if stock is None:
        raise HTTPException(status_code=404, detail=f"{ticker} non e' nel catalogo")
    v = catalogo_fermi_service.verifica(stock.ticker, stock.name)
    return VerificaFonteOut(
        ticker=v.ticker, barre_recenti=v.barre_recenti, ultima_barra_fonte=v.ultima_barra_fonte,
        candidati=[CandidatoOut(**c.__dict__) for c in v.candidati], errore=v.errore,
    )
