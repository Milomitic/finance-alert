"""Il portafoglio eToro nell'app (FA-124): vedi `etoro_portafoglio_service`.

Tutto in lettura tranne due cose che non toccano eToro: confermare a quale
titolo del catalogo corrisponde uno strumento, e chiedere una sincronizzazione
subito invece di aspettare il job dei 10 minuti.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_json
from app.core.errors import UpstreamError
from app.models import Position, Stock, User
from app.models.etoro import EtoroConto, EtoroPosizione, EtoroStrumento
from app.models.preferito import Preferito
from app.services import etoro_client, etoro_watchlist_service, preferiti_service
from app.services import etoro_portafoglio_service as svc

router = APIRouter(prefix="/api/etoro", tags=["etoro"])

#: Le chiuse mostrate accanto alle aperte.
GIORNI_CHIUSE = 30


class EtoroPosizioneOut(BaseModel):
    position_id: int
    instrument_id: int
    simbolo: str | None
    nome: str | None
    #: Il ticker del catalogo, solo con un abbinamento automatico o confermato.
    ticker: str | None
    valuta: str | None
    lato: str
    leva: int
    regolamento: str
    copia: bool
    aperta_il: datetime
    prezzo_apertura: float
    prezzo_corrente: float | None
    unita: float
    importo_usd: float
    margine_usd: float | None
    esposizione_usd: float | None
    pnl_usd: float | None
    pnl_pct_margine: float | None
    stop: float | None
    target: float | None
    stop_pct_margine: float | None
    commissioni_usd: float | None
    pnl_il: datetime | None
    chiusa_il: datetime | None
    prezzo_chiusura: float | None
    profitto_netto_usd: float | None
    motivo_chiusura: str | None
    #: Lo stesso titolo e' anche fra le posizioni inserite a mano.
    anche_manuale: bool


class EtoroContoOut(BaseModel):
    aggiornato_il: datetime
    valuta: str | None
    credito_usd: float | None
    valore_totale: float | None
    pnl_aperto: float | None
    guadagno_giorno: float | None
    guadagno_giorno_pct: float | None


class EtoroStrumentoOut(BaseModel):
    instrument_id: int
    simbolo: str | None
    nome: str | None
    tipo: str | None
    abbinamento: str
    ticker: str | None
    candidato_ticker: str | None
    candidato_nome: str | None


class EtoroPortafoglioOut(BaseModel):
    configurato: bool
    conto: EtoroContoOut | None
    aperte: list[EtoroPosizioneOut]
    chiuse: list[EtoroPosizioneOut]
    #: Gli abbinamenti che aspettano l'utente, NELLA STESSA risposta: una
    #: seconda chiamata comparirebbe dopo e sposterebbe la pagina (FA-106).
    da_decidere: list[EtoroStrumentoOut]
    # ── Le watchlist (FA-125) ──
    preferiti_da_etoro: int
    #: Strumenti delle watchlist senza un titolo nel catalogo (crypto, materie
    #: prime, titoli non coperti): si contano, non si elencano.
    watchlist_fuori_catalogo: int
    watchlist_da_confermare: list[EtoroStrumentoOut]


class EtoroAbbinamentoIn(BaseModel):
    #: Un ticker del catalogo, o None per «non e' nel catalogo».
    ticker: str | None


class EtoroSincronizzazioneOut(BaseModel):
    saltata: str | None
    aperte: int
    nuove: int
    chiuse: int
    strumenti_nuovi: int
    da_confermare: int
    conto_aggiornato: bool
    preferiti_aggiunti: int
    preferiti_tolti: int


def _aware(d: datetime | None) -> datetime | None:
    return d if d is None or d.tzinfo else d.replace(tzinfo=UTC)


def _strumento(db: Session, s: EtoroStrumento) -> EtoroStrumentoOut:
    stock = db.get(Stock, s.stock_id) if s.stock_id else None
    cand = db.get(Stock, s.candidato_stock_id) if s.candidato_stock_id else None
    return EtoroStrumentoOut(
        instrument_id=s.instrument_id, simbolo=s.simbolo, nome=s.nome, tipo=s.tipo,
        abbinamento=s.abbinamento, ticker=stock.ticker if stock else None,
        candidato_ticker=cand.ticker if cand else None, candidato_nome=cand.name if cand else None,
    )


def _riga(pos: EtoroPosizione, s: EtoroStrumento, stock: Stock | None, manuali: set[int]) -> EtoroPosizioneOut:
    return EtoroPosizioneOut(
        position_id=pos.position_id, instrument_id=pos.instrument_id,
        simbolo=s.simbolo, nome=s.nome,
        ticker=stock.ticker if stock else None,
        valuta=stock.currency if stock else None,
        lato=pos.lato, leva=pos.leva, regolamento=pos.regolamento, copia=pos.mirror_id is not None,
        aperta_il=_aware(pos.aperta_il), prezzo_apertura=pos.prezzo_apertura,
        prezzo_corrente=pos.prezzo_corrente, unita=pos.unita, importo_usd=pos.importo_usd,
        margine_usd=pos.margine_usd, esposizione_usd=pos.esposizione_usd, pnl_usd=pos.pnl_usd,
        pnl_pct_margine=svc.pct_sul_margine(pos.pnl_usd, pos.margine_usd),
        stop=pos.stop, target=pos.target,
        stop_pct_margine=svc.stop_sul_margine(pos.lato, pos.prezzo_apertura, pos.stop, pos.leva),
        commissioni_usd=pos.commissioni_usd, pnl_il=_aware(pos.pnl_il),
        chiusa_il=_aware(pos.chiusa_il), prezzo_chiusura=pos.prezzo_chiusura,
        profitto_netto_usd=pos.profitto_netto_usd, motivo_chiusura=pos.motivo_chiusura,
        anche_manuale=bool(stock and stock.id in manuali and pos.chiusa_il is None),
    )


@router.get("/portafoglio", response_model=EtoroPortafoglioOut)
def portafoglio(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> EtoroPortafoglioOut:
    manuali = set(db.execute(select(Position.stock_id).where(Position.closed_at.is_(None))).scalars())
    soglia = datetime.now(UTC) - timedelta(days=GIORNI_CHIUSE)
    righe = db.execute(
        select(EtoroPosizione, EtoroStrumento, Stock)
        .join(EtoroStrumento, EtoroStrumento.instrument_id == EtoroPosizione.instrument_id)
        .outerjoin(Stock, Stock.id == EtoroStrumento.stock_id)
        .where((EtoroPosizione.chiusa_il.is_(None)) | (EtoroPosizione.chiusa_il >= soglia))
        .order_by(EtoroPosizione.aperta_il.desc())
    ).all()
    aperte = [_riga(p, s, st, manuali) for p, s, st in righe if p.chiusa_il is None]
    chiuse = sorted(
        (_riga(p, s, st, manuali) for p, s, st in righe if p.chiusa_il is not None),
        key=lambda r: r.chiusa_il, reverse=True,
    )
    conto = db.get(EtoroConto, 1)
    return EtoroPortafoglioOut(
        configurato=etoro_client.configurato(),
        conto=EtoroContoOut(
            aggiornato_il=_aware(conto.aggiornato_il), valuta=conto.valuta, credito_usd=conto.credito_usd,
            valore_totale=conto.valore_totale, pnl_aperto=conto.pnl_aperto,
            guadagno_giorno=conto.guadagno_giorno, guadagno_giorno_pct=conto.guadagno_giorno_pct,
        ) if conto else None,
        aperte=aperte, chiuse=chiuse, da_decidere=[_strumento(db, s) for s in svc.da_decidere(db)],
        preferiti_da_etoro=len(db.execute(
            select(Preferito.stock_id).where(Preferito.origine == preferiti_service.ETORO)
        ).all()),
        watchlist_fuori_catalogo=len(db.execute(
            select(EtoroStrumento.instrument_id).where(
                EtoroStrumento.in_watchlist.is_(True), EtoroStrumento.abbinamento == svc.ASSENTE
            )
        ).all()),
        watchlist_da_confermare=[_strumento(db, s) for s in svc.watchlist_da_confermare(db)],
    )


@router.get("/strumenti", response_model=list[EtoroStrumentoOut])
def strumenti(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[EtoroStrumentoOut]:
    """Gli strumenti in portafoglio con il loro abbinamento: prima quelli da
    confermare, poi gli assenti, poi gli abbinati."""
    ordine = {svc.DA_CONFERMARE: 0, svc.ASSENTE: 1, svc.MANUALE: 2, svc.AUTOMATICO: 3}
    out = [_strumento(db, s) for s in db.execute(select(EtoroStrumento)).scalars()]
    out.sort(key=lambda r: (ordine.get(r.abbinamento, 9), r.simbolo or ""))
    return out


@router.put("/strumenti/{instrument_id}", response_model=EtoroStrumentoOut,
            dependencies=[Depends(require_json)])
def abbina(
    instrument_id: int,
    corpo: EtoroAbbinamentoIn,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> EtoroStrumentoOut:
    try:
        s = svc.conferma_abbinamento(db, instrument_id, corpo.ticker)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    etoro_watchlist_service.preferito_da_conferma(db, s)
    return _strumento(db, s)


@router.post("/sincronizza", response_model=EtoroSincronizzazioneOut,
             dependencies=[Depends(require_json)])
def sincronizza(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> EtoroSincronizzazioneOut:
    """Una sincronizzazione subito, portafoglio e watchlist. Un errore di
    eToro diventa 502 col motivo."""
    try:
        e = svc.sincronizza(db)
        w = etoro_watchlist_service.sincronizza_watchlist(db)
    except UpstreamError as err:
        raise HTTPException(status_code=502, detail=f"eToro: {err}") from err
    return EtoroSincronizzazioneOut(
        saltata=e.saltata, aperte=e.aperte, nuove=e.nuove, chiuse=len(e.chiuse),
        strumenti_nuovi=e.strumenti_nuovi, da_confermare=e.da_confermare,
        conto_aggiornato=e.conto_aggiornato,
        preferiti_aggiunti=w.aggiunti, preferiti_tolti=w.tolti,
    )
