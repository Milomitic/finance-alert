"""La pagina Studio: statistica storica di un simbolo (FA-157).

Una rotta per modello, tutte GET e quindi leggibili anche dal server MCP. La
risposta e' un dizionario libero (`dict`) perche' i tre modelli hanno forme
diverse; il proprietario della forma e' `studio_service`, e il frontend la
tipizza per modello.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import User
from app.services import studio_service as ss

router = APIRouter(prefix="/api/studio", tags=["studio"])


def _serie(db: Session, simbolo: str) -> ss.Serie:
    s = ss.serie_di(db, simbolo)
    if s is None or len(s.chiusure) < 30:
        raise HTTPException(status_code=404, detail=f"Nessuna storia per {simbolo}")
    return s


def _al_netto(db: Session, s: ss.Serie, netto: str | None) -> tuple[ss.Serie, list[float] | None]:
    """FA-197: la serie ristretta alle date comuni e il rapporto col
    riferimento, o la serie com'e' se non si chiede il netto."""
    if not netto:
        return s, None
    rif = ss.serie_di(db, netto)
    if rif is None:
        raise HTTPException(status_code=404, detail=f"Nessuna storia per {netto}")
    sub, rapporto = ss.allinea_al_netto(s, rif)
    if len(sub.chiusure) < 30:
        raise HTTPException(status_code=404, detail=f"Troppe poche date in comune con {netto}")
    return sub, rapporto


@router.get("/dopo_movimento")
def dopo_movimento(
    simbolo: str,
    sedute: int = Query(5, ge=1, le=63),
    soglia_pct: float = Query(-10.0, ge=-90, le=500),
    orizzonte: int = Query(21, ge=1, le=252),
    netto: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if soglia_pct == 0:
        raise HTTPException(status_code=422, detail="soglia_pct non puo' essere zero")
    s, esiti = _al_netto(db, _serie(db, simbolo), netto)
    return {"simbolo": simbolo.upper(), "netto": netto.upper() if netto else None, **ss.dopo_movimento(
        s, sedute=sedute, soglia_pct=soglia_pct, orizzonte=orizzonte, esiti=esiti)}


@router.get("/stagionalita")
def stagionalita(
    simbolo: str,
    netto: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    s, rapporto = _al_netto(db, _serie(db, simbolo), netto)
    # Al netto, la stagionalita' e' quella del rapporto: i mesi in cui il
    # simbolo ha fatto meglio o peggio del riferimento.
    if rapporto is not None:
        s = ss.Serie(s.date, rapporto)
    return {"simbolo": simbolo.upper(), "netto": netto.upper() if netto else None, **ss.stagionalita(s)}


@router.get("/evento")
def evento(
    simbolo: str,
    tipo: str = Query("trimestrali", pattern="^(trimestrali|macro)$"),
    serie_macro: str | None = None,
    orizzonte: int = Query(5, ge=1, le=ss.DOPO),
    netto: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """`tipo=trimestrali`: le trimestrali passate del titolo. `tipo=macro` con
    `serie_macro` (id FRED, es. CPIAUCSL): i rilasci di quella serie."""
    if tipo == "macro":
        if not serie_macro:
            raise HTTPException(status_code=422, detail="serve serie_macro")
        date_ = ss.date_macro(db, serie_macro)
    else:
        date_ = ss.date_trimestrali(simbolo)
    s, esiti = _al_netto(db, _serie(db, simbolo), netto)
    return {"simbolo": simbolo.upper(), "tipo": tipo, "serie_macro": serie_macro, "netto": netto.upper() if netto else None,
            "eventi": len(date_), **ss.evento(s, date_, orizzonte=orizzonte, esiti=esiti)}


@router.get("/primo_passaggio")
def primo_passaggio(
    simbolo: str,
    lato: str = Query("long", pattern="^(long|short)$"),
    target_pct: float = Query(8.0, gt=0, le=200),
    stop_pct: float = Query(5.0, gt=0, le=90),
    orizzonte: int = Query(21, ge=1, le=252),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """FA-196: entro `orizzonte` sedute, prima il target o prima lo stop?"""
    return {"simbolo": simbolo.upper(), **ss.primo_passaggio(
        _serie(db, simbolo), lato=lato, target_pct=target_pct, stop_pct=stop_pct, orizzonte=orizzonte)}


@router.get("/cali")
def cali(
    simbolo: str,
    soglia_pct: float = Query(10.0, ge=2, le=90),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """FA-198: i cali oltre la soglia, i tempi di recupero, il calo di oggi."""
    return {"simbolo": simbolo.upper(), **ss.cali_e_recuperi(_serie(db, simbolo), soglia_pct=soglia_pct)}


@router.get("/serie_macro")
def serie_macro(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """FA-199 (D-83): le serie macro con almeno un rilascio, per nome. Prima il
    modulo chiedeva l'ID FRED a memoria («CPIAUCSL»)."""
    from sqlalchemy import func, select  # noqa: PLC0415

    from app.models import MacroReleaseDate, MacroSeries  # noqa: PLC0415

    righe = db.execute(
        select(MacroSeries.fred_series_id, MacroSeries.label, func.count(MacroReleaseDate.id))
        .join(MacroReleaseDate, MacroReleaseDate.series_id == MacroSeries.id)
        .group_by(MacroSeries.fred_series_id, MacroSeries.label)
        .order_by(MacroSeries.label)
    ).all()
    return [{"id": i, "nome": n, "rilasci": c} for i, n, c in righe]

