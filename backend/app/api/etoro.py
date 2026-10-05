"""Il portafoglio eToro nell'app (FA-124): vedi `etoro_portafoglio_service`.

Tutto in lettura tranne due cose che non toccano eToro: confermare a quale
titolo del catalogo corrisponde uno strumento, e chiedere una sincronizzazione
subito invece di aspettare il job dei 10 minuti.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_json
from app.core.errors import UpstreamError
from app.models import Position, Stock, User
from app.models.etoro import EtoroConto, EtoroPosizione, EtoroStrumento
from app.models.preferito import Preferito
from app.services import etoro_catalogo_service as catalogo
from app.services import etoro_client, etoro_watchlist_service, preferiti_service
from app.services import etoro_diario_service as diario_svc
from app.services import etoro_patrimonio_service as patrimonio
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


# ─── Patrimonio e andamento (FA-127) ────────────────────────────────────────


class EtoroStrumentoOggiOut(BaseModel):
    instrument_id: int
    ticker: str | None
    simbolo: str | None
    nome: str | None
    #: Il guadagno di OGGI su questo strumento, calcolato da eToro.
    guadagno_giorno: float | None
    pnl: float | None
    esposizione: float | None
    margine: float | None


class EtoroVivoOut(BaseModel):
    configurato: bool
    aggiornato_il: datetime | None
    #: True quando eToro non ha risposto: i numeri sono dell'ultima sincronizzazione.
    in_ritardo: bool
    valuta: str | None
    valore: float | None
    valore_ieri: float | None
    guadagno_giorno: float | None
    guadagno_giorno_pct: float | None
    pnl_aperto: float | None
    margine_usato: float | None
    cassa: float | None
    esposizione: float | None
    #: esposizione / valore del conto: quanto il conto e' a leva, in tutto.
    leva_effettiva: float | None
    posizioni: int
    strumenti: list[EtoroStrumentoOggiOut]


class EtoroGiornoOut(BaseModel):
    giorno: date
    valore: float
    pnl_aperto: float | None
    fonte: str


class EtoroPuntoOut(BaseModel):
    istante: datetime
    valore: float


class EtoroPeriodoOut(BaseModel):
    chiave: str
    dal: date
    valore_iniziale: float
    valore_finale: float
    variazione: float
    generato: float | None
    realizzato: float
    flussi: float | None
    generato_pct: float | None


class EtoroAndamentoOut(BaseModel):
    configurato: bool
    giorni: list[EtoroGiornoOut]
    oggi: list[EtoroPuntoOut]
    periodi: list[EtoroPeriodoOut]


_VIVO_VUOTO = dict(
    aggiornato_il=None, in_ritardo=False, valuta=None, valore=None, valore_ieri=None,
    guadagno_giorno=None, guadagno_giorno_pct=None, pnl_aperto=None, margine_usato=None,
    cassa=None, esposizione=None, leva_effettiva=None, posizioni=0, strumenti=[],
)


@router.get("/vivo", response_model=EtoroVivoOut)
def vivo(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> EtoroVivoOut:
    """Il conto adesso (cache di 30 s sul server). Non solleva: se eToro non
    risponde rende l'ultima sincronizzazione con `in_ritardo`."""
    if not etoro_client.configurato():
        return EtoroVivoOut(configurato=False, **_VIVO_VUOTO)
    v = patrimonio.vivo(db)
    if v is None:
        return EtoroVivoOut(configurato=True, **_VIVO_VUOTO)
    return EtoroVivoOut(
        configurato=True, aggiornato_il=_aware(v.aggiornato_il), in_ritardo=v.in_ritardo, valuta=v.valuta,
        valore=v.valore, valore_ieri=v.valore_ieri, guadagno_giorno=v.guadagno_giorno,
        guadagno_giorno_pct=v.guadagno_giorno_pct, pnl_aperto=v.pnl_aperto,
        margine_usato=v.margine_usato, cassa=v.cassa, esposizione=v.esposizione,
        leva_effettiva=(v.esposizione / v.valore) if v.esposizione and v.valore else None,
        posizioni=v.posizioni,
        strumenti=[EtoroStrumentoOggiOut(**s.__dict__) for s in v.strumenti],
    )


@router.get("/andamento", response_model=EtoroAndamentoOut)
def andamento(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> EtoroAndamentoOut:
    giorni, punti, per = patrimonio.andamento(db)
    return EtoroAndamentoOut(
        configurato=etoro_client.configurato(),
        giorni=[EtoroGiornoOut(giorno=g.giorno, valore=g.valore, pnl_aperto=g.pnl_aperto, fonte=g.fonte) for g in giorni],
        oggi=[EtoroPuntoOut(istante=_aware(p.istante), valore=p.valore) for p in punti],
        periodi=[EtoroPeriodoOut(**p.__dict__) for p in per],
    )


# ─── Negoziabilita' e costi (FA-126) ────────────────────────────────────────


class EtoroDisponibileOut(BaseModel):
    disponibile: bool
    simbolo: str | None
    tipo: str | None


class EtoroVoceCostoOut(BaseModel):
    tipo: str
    importo: float
    valuta: str
    importo_usd: float | None


class EtoroCostiOut(BaseModel):
    #: False = eToro non collegato: «non disponibile» non vorrebbe dire niente.
    configurato: bool
    disponibile: bool
    simbolo: str | None
    voci: list[EtoroVoceCostoOut]
    apertura_usd: float | None
    notte_usd: float | None
    weekend_usd: float | None
    aggiornato_il: str | None


@router.get("/disponibile/{ticker}", response_model=EtoroDisponibileOut)
def disponibile(
    ticker: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> EtoroDisponibileOut:
    r = catalogo.del_titolo(db, ticker)
    return EtoroDisponibileOut(disponibile=r is not None, simbolo=r.simbolo if r else None, tipo=r.tipo if r else None)


@router.get("/costi", response_model=EtoroCostiOut)
def costi(
    ticker: str,
    lato: str = Query("long", pattern="^(long|short)$"),
    leva: int = Query(5, ge=1, le=30),
    importo: float = Query(500.0, gt=0, le=1_000_000),
    stop: float | None = Query(None, gt=0),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> EtoroCostiOut:
    """Il preventivo eToro di un ingresso CFD: costi d'apertura e overnight a
    notte, in USD. Cache di un'ora per combinazione."""
    if not etoro_client.configurato():
        return EtoroCostiOut(configurato=False, disponibile=False, simbolo=None, voci=[], apertura_usd=None,
                             notte_usd=None, weekend_usd=None, aggiornato_il=None)
    try:
        c = catalogo.costi(db, ticker, lato=lato, leva=leva, importo=importo, stop=stop)
    except UpstreamError as err:
        raise HTTPException(status_code=502, detail=f"eToro: {err}") from err
    if c is None:
        return EtoroCostiOut(configurato=True, disponibile=False, simbolo=None, voci=[], apertura_usd=None,
                             notte_usd=None, weekend_usd=None, aggiornato_il=None)
    return EtoroCostiOut(
        configurato=True, disponibile=True, simbolo=c.simbolo,
        voci=[EtoroVoceCostoOut(**v.__dict__) for v in c.voci],
        apertura_usd=c.apertura_usd, notte_usd=c.notte_usd, weekend_usd=c.weekend_usd,
        aggiornato_il=c.aggiornato_il,
    )


# ─── Il diario delle operazioni chiuse (FA-128) ─────────────────────────────


class EtoroOperazioneOut(BaseModel):
    position_id: int
    instrument_id: int
    ticker: str | None
    simbolo: str | None
    aperta_il: datetime | None
    chiusa_il: datetime
    lato: str
    leva: int
    prezzo_apertura: float | None
    prezzo_chiusura: float | None
    investimento_usd: float | None
    profitto_netto_usd: float
    commissioni_usd: float | None
    pct_investimento: float | None
    giorni: float | None
    #: Il segnale che l'ha PRECEDUTA (stesso titolo e verso, entro 5 giorni):
    #: una coincidenza temporale, non la prova che sia stata aperta per quello.
    alert_id: int | None
    detector: str | None
    segnale_il: datetime | None
    r_reale: float | None
    r_piano: float | None
    esito_piano: str | None


class EtoroGruppoOut(BaseModel):
    n: int
    vincenti: int
    profitto_usd: float
    vincenti_pct: float | None
    profitto_medio_usd: float | None


class EtoroAnnoOut(BaseModel):
    anno: int
    n: int
    profitto_usd: float
    profitto_eur: float | None
    commissioni_usd: float


class EtoroDiarioOut(BaseModel):
    operazioni: list[EtoroOperazioneOut]
    tutte: EtoroGruppoOut | None
    precedute: EtoroGruppoOut | None
    non_precedute: EtoroGruppoOut | None
    r_reale_medio: float | None
    r_piano_medio: float | None
    con_r: int
    anni: list[EtoroAnnoOut]


@router.get("/diario", response_model=EtoroDiarioOut)
def diario(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> EtoroDiarioOut:
    d = diario_svc.diario(db)

    def g(x):
        return EtoroGruppoOut(**x.__dict__) if x is not None else None

    return EtoroDiarioOut(
        operazioni=[EtoroOperazioneOut(**{
            **v.__dict__, "aperta_il": _aware(v.aperta_il), "chiusa_il": _aware(v.chiusa_il),
            "segnale_il": _aware(v.segnale_il),
        }) for v in d.voci],
        tutte=g(d.tutte), precedute=g(d.precedute), non_precedute=g(d.non_precedute),
        r_reale_medio=d.r_reale_medio, r_piano_medio=d.r_piano_medio, con_r=d.con_r,
        anni=[EtoroAnnoOut(**a.__dict__) for a in d.anni],
    )
