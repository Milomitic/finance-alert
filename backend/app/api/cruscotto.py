"""«Dall'ultima visita» sul cruscotto (2026-09-29): vedi `ultima_visita_service`."""
from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_json
from app.models import User
from app.services import ultima_visita_service

router = APIRouter(prefix="/api/cruscotto", tags=["cruscotto"])


class NovitaTitoloOut(BaseModel):
    ticker: str
    rilevanza: str
    data: date
    tipo: str
    testo: str


class DallUltimaVisitaOut(BaseModel):
    #: None alla prima visita di sempre.
    dal: datetime | None
    segnali: int
    segnali_miei: int
    target_raggiunti: int
    posizioni_chiuse: int
    novita: list[NovitaTitoloOut]


@router.post("/visita", response_model=DallUltimaVisitaOut, dependencies=[Depends(require_json)])
def registra_visita(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> DallUltimaVisitaOut:
    """Segna un'apertura del cruscotto e rende cio' che e' cambiato dal
    riferimento. POST e non GET: scrive. Due chiamate ravvicinate — il doppio
    montaggio di React, una ricarica — rendono la stessa risposta."""
    dal = ultima_visita_service.registra_apertura(db, datetime.now(UTC))
    r = ultima_visita_service.riepilogo(db, dal)
    return DallUltimaVisitaOut(
        dal=r.dal,
        segnali=r.segnali,
        segnali_miei=r.segnali_miei,
        target_raggiunti=r.target_raggiunti,
        posizioni_chiuse=r.posizioni_chiuse,
        novita=[
            NovitaTitoloOut(ticker=n.ticker, rilevanza=n.rilevanza, data=n.data, tipo=n.tipo, testo=n.testo)
            for n in r.novita
        ],
    )
