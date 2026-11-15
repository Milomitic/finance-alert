"""Il dettaglio titolo a confronto: pari, reazioni alle trimestrali, variazione
del punteggio e la nota personale (FA-156).

Router a parte con lo stesso prefisso di `stocks.py`, che e' gia' il file piu'
lungo dell'API. Le letture sono GET; la nota si scrive con PUT, quindi il
token MCP (sola lettura per costruzione, `deps._utente_da_token`) non la
puo' toccare.
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_json
from app.models import NotaTitolo, Stock, User
from app.models.nota_titolo import NOTA_MAX
from app.services import titolo_confronti_service as tc

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


class PariRigaOut(BaseModel):
    ticker: str
    nome: str | None = None
    cap_usd: float | None = None
    qualita: float | None = None
    tecnico: float | None = None
    pe: float | None = None
    crescita_ricavi: float | None = None
    rendimento_3m: float | None = None


class PariOut(BaseModel):
    #: «industria», o «settore» se l'industria ha meno di tre titoli.
    base: str
    gruppo: str | None = None
    #: La prima riga e' il titolo stesso.
    righe: list[PariRigaOut]


class ReazioneOut(BaseModel):
    data: str
    #: pre | after | None (ora ignota)
    quando: str | None = None
    sorpresa_pct: float | None = None
    reazione_pct: float
    cinque_sedute_pct: float | None = None
    #: Ora ignota: la reazione copre due sedute invece di una.
    due_sedute: bool = False


class ReazioniOut(BaseModel):
    righe: list[ReazioneOut]
    mediana_assoluta_pct: float | None = None


class ContributoOut(BaseModel):
    pilastro: str
    da: float
    a: float
    contributo: float


class FinestraPunteggioOut(BaseModel):
    giorni: int
    dal: str
    al: str
    da: float
    a: float
    delta: float
    contributi: list[ContributoOut]
    #: Cio' che i pilastri comuni non spiegano: un pilastro comparso o sparito.
    altro: float


class VariazionePunteggioOut(BaseModel):
    finestre: list[FinestraPunteggioOut]


class NotaOut(BaseModel):
    testo: str = ""
    aggiornata_il: datetime | None = None


class NotaIn(BaseModel):
    testo: str = Field(max_length=NOTA_MAX)


def _o_404(valore, ticker: str):
    if valore is None:
        raise HTTPException(status_code=404, detail=f"Ticker not found: {ticker}")
    return valore


@router.get("/{ticker}/pari", response_model=PariOut)
def get_pari(ticker: str, db: Session = Depends(get_db),
             _user: User = Depends(get_current_user)) -> PariOut:
    return PariOut(**_o_404(tc.pari(db, ticker), ticker))


@router.get("/{ticker}/reazioni-trimestrali", response_model=ReazioniOut)
def get_reazioni(ticker: str, db: Session = Depends(get_db),
                 _user: User = Depends(get_current_user)) -> ReazioniOut:
    return ReazioniOut(**_o_404(tc.reazioni_trimestrali(db, ticker), ticker))


@router.get("/{ticker}/variazione-punteggio", response_model=VariazionePunteggioOut)
def get_variazione(ticker: str, db: Session = Depends(get_db),
                   _user: User = Depends(get_current_user)) -> VariazionePunteggioOut:
    return VariazionePunteggioOut(**_o_404(tc.variazione_punteggio(db, ticker), ticker))


def _titolo(db: Session, ticker: str) -> Stock:
    return _o_404(db.execute(select(Stock).where(Stock.ticker == ticker).limit(1))
                  .scalars().first(), ticker)


@router.get("/{ticker}/nota", response_model=NotaOut)
def get_nota(ticker: str, db: Session = Depends(get_db),
             _user: User = Depends(get_current_user)) -> NotaOut:
    n = db.get(NotaTitolo, _titolo(db, ticker).id)
    return NotaOut(testo=n.testo, aggiornata_il=n.aggiornata_il) if n else NotaOut()


@router.put("/{ticker}/nota", response_model=NotaOut, dependencies=[Depends(require_json)])
def put_nota(ticker: str, corpo: NotaIn, db: Session = Depends(get_db),
             _user: User = Depends(get_current_user)) -> NotaOut:
    """Scrive la nota; un testo vuoto la toglie."""
    s = _titolo(db, ticker)
    n = db.get(NotaTitolo, s.id)
    testo = corpo.testo.strip()
    adesso = datetime.now(UTC)
    if not testo:
        if n is not None:
            db.delete(n)
            db.commit()
        return NotaOut()
    if n is None:
        n = NotaTitolo(stock_id=s.id, testo=testo, creata_il=adesso, aggiornata_il=adesso)
        db.add(n)
    else:
        n.testo, n.aggiornata_il = testo, adesso
    db.commit()
    return NotaOut(testo=n.testo, aggiornata_il=n.aggiornata_il)
