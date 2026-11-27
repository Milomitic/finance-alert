"""Market detail endpoint — `/api/markets/{symbol}/detail`.

Serves OHLCV history + summary fields for non-stock instruments
(indices, commodities, crypto) that are listed in the dashboard's
LiveAssetsPanel. Used by the frontend MarketDetailPage.

Why a separate router from `/api/stocks/...`
- Catalog membership: those endpoints filter via the catalog +
  `visible_country_clause`. The symbols here (^GSPC, BTC-USD, GC=F,
  ...) intentionally aren't in the catalog.
- Different fetch path: `services/market_detail_service` goes
  straight to yfinance with a 15-min cache, no DB roundtrip for
  the OHLCV.
"""
import json
from datetime import date as date_t
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.api.indicatori_compatti import Formato, serie_compatte
from app.api.market import CACHE_ESTESI, TUTTI_I_MERCATI, LiveAssetsOut, quotazione_da_mostrare
from app.models import User
from app.services import live_quote_service, market_detail_service, mercati_service

router = APIRouter(prefix="/api/markets", tags=["markets"])


# Build a quick lookup of the curated symbols + their UI metadata so
# the detail endpoint can return name/category/flag without the
# frontend hard-coding it. Tuple in LIVE_ASSET_DEFINITIONS is now
# (symbol, name, category, flag, futures_symbol) — the 5th element
# is unused here so we discard it with `_`.
_LIVE_META: dict[str, tuple[str, str, str | None]] = {
    symbol: (name, category, flag)
    for (symbol, name, category, flag, _) in TUTTI_I_MERCATI
}
# Also accept the index E-mini FUTURES symbols (ES=F, NQ=F, …) as valid
# detail targets: the dashboard's "Mercati live" card links the row to the
# futures contract when it's showing the after-hours futures price, so the
# detail must resolve the same instrument (otherwise the card's ~30.5k
# Nasdaq futures price would open a ~25k cash-index detail — the mismatch
# the user reported). Labeled "(futures)" + the index's category/flag.
for _sym, _name, _cat, _flag, _fut in TUTTI_I_MERCATI:
    if _fut and _fut not in _LIVE_META:
        _LIVE_META[_fut] = (f"{_name} (futures)", _cat, _flag)

#: L'indice cash -> il suo future, per mostrare in pagina la STESSA quotazione
#: della home a cash chiuso (FA-180).
_FUTURE_DI: dict[str, str] = {s: f for (s, _n, _c, _fl, f) in TUTTI_I_MERCATI if f}


class OhlcvBarOut(BaseModel):
    # `date | datetime` so intraday (30m/1h) bars keep their wall-clock
    # time and don't collide on the chart. Daily+ stays as YYYY-MM-DD.
    date: date_t | datetime
    open: float
    high: float
    low: float
    close: float
    volume: int | None


class LiveQuoteOut(BaseModel):
    """Subset of live_quote_service.LiveQuote relevant to non-stocks."""
    price: float | None
    prev_close: float | None
    change_abs: float | None
    change_pct: float | None
    market_state: str | None
    currency: str | None
    error: str | None


class IndicatorPointOut(BaseModel):
    """One (date, value) pair for an indicator series."""
    date: date_t | datetime
    value: float | None


class IndicatorBundleOut(BaseModel):
    """All indicator overlays for the chart - same shape as the stock
    detail response so the frontend can reuse the rendering primitives.
    May 2026: SMA → EMA. Lists empty when the bar series is too short
    for the indicator (e.g. EMA200 is only emitted at >=200 bars to
    avoid drawing a near-flat line on short histories — EMA itself
    has no warmup NaN since it initialises to the first close)."""
    ema20: list[IndicatorPointOut] = []
    ema50: list[IndicatorPointOut] = []
    ema200: list[IndicatorPointOut] = []
    bb_upper: list[IndicatorPointOut] = []
    bb_middle: list[IndicatorPointOut] = []
    bb_lower: list[IndicatorPointOut] = []
    rsi14: list[IndicatorPointOut] = []
    macd_line: list[IndicatorPointOut] = []
    macd_signal: list[IndicatorPointOut] = []
    macd_hist: list[IndicatorPointOut] = []


class MarketDetailOut(BaseModel):
    symbol: str
    name: str
    category: str  # "index" | "commodity" | "crypto"
    flag: str | None
    range_key: str

    last_close: float | None
    prev_close: float | None
    change_pct: float | None
    high_window: float | None
    low_window: float | None
    high_52w: float | None
    low_52w: float | None

    bars: list[OhlcvBarOut]
    indicators: IndicatorBundleOut
    quote: LiveQuoteOut | None
    # FA-180: a cash chiuso la quotazione e' quella del future accoppiato,
    # come nella home; `quote_symbol` dice quale. Il grafico resta il cash.
    using_futures: bool = False
    quote_symbol: str | None = None


# ─── FA-184 / FA-185: rendimenti, statistiche e calendario ─────────────────


class EstremoOut(BaseModel):
    valore: float
    data: str
    distanza: float
    sedute_da: int


class RigaPanoramicaOut(BaseModel):
    symbol: str
    name: str
    category: str
    flag: str | None
    ultima_chiusura: float
    data_chiusura: str
    #: chiavi 1s, 1m, 3m, 6m, ytd, 1a, 3a, 5a, 3a_ann, 5a_ann; None = la
    #: storia non copre il periodo.
    rendimenti: dict[str, float | None]
    massimo_52s: EstremoOut | None
    minimo_52s: EstremoOut | None
    posizione_52s: float | None
    dal_massimo_storico: EstremoOut | None
    vol_20g: float | None
    vol_1a: float | None
    distanza_ema200: float | None


class PanoramicaOut(BaseModel):
    alla_chiusura_del: str | None
    strumenti: list[RigaPanoramicaOut]


class CaloOut(BaseModel):
    profondita: float
    picco: str | None = None
    minimo: str | None = None
    recupero: str | None = None


class CaloCorrenteOut(BaseModel):
    profondita: float
    picco: str
    sedute_dal_picco: int


class AnnoCalendarioOut(BaseModel):
    anno: int
    mesi: list[float | None]
    anno_totale: float | None
    parziale: bool


class CalendarioOut(BaseModel):
    anni: list[AnnoCalendarioOut]
    media_mesi: list[float | None]
    positivi_mesi: list[float | None]
    casi_mesi: list[int]
    ultimo_mese: str | None


class StatisticheOut(BaseModel):
    symbol: str
    data_chiusura: str
    dal: str
    rendimenti: dict[str, float | None]
    vol_20g: float | None
    vol_1a: float | None
    massimo_52s: EstremoOut | None
    minimo_52s: EstremoOut | None
    dal_massimo_storico: EstremoOut | None
    calo_corrente: CaloCorrenteOut | None
    calo_massimo_1a: CaloOut | None
    calo_massimo_5a: CaloOut | None
    calo_massimo_storico: CaloOut | None
    calendario: CalendarioOut


class IndiceComposizioneOut(BaseModel):
    code: str
    nome: str
    titoli_nel_catalogo: int
    nota: str | None
    pesato_sul_prezzo: bool


class AmpiezzaIndiceOut(BaseModel):
    avanzano: int
    scendono: int
    sopra_ema50_pct: float | None
    sopra_ema200_pct: float | None
    nuovi_massimi_52s: int
    nuovi_minimi_52s: int
    rsi_sopra_70: int
    rsi_sotto_30: int
    var_media_pct: float | None


class SettoreIndiceOut(BaseModel):
    settore: str
    titoli: int
    var_media_pct: float | None
    peso_pct: float | None


class CostituenteOut(BaseModel):
    ticker: str
    nome: str
    settore: str
    #: ⚠️ In PUNTI percentuali (1,5 = +1,5%), come `stock_metrics.change_pct`;
    #: il resto delle API dei mercati usa frazioni.
    var_pct: float | None
    peso_pct: float | None
    #: Peso di capitalizzazione nel catalogo x variazione, in punti
    #: percentuali; None per gli indici pesati sul prezzo.
    contributo_pp: float | None


class ComposizioneOut(BaseModel):
    indice: IndiceComposizioneOut
    ampiezza: AmpiezzaIndiceOut
    settori: list[SettoreIndiceOut]
    migliori: list[CostituenteOut]
    peggiori: list[CostituenteOut]
    alla_scansione_del: str | None


@router.get("/{symbol}/composizione", response_model=ComposizioneOut)
def get_composizione(
    symbol: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user),
) -> ComposizioneOut:
    """FA-186: ampiezza, settori, migliori e peggiori dei costituenti di un
    indice, dalla scansione piu' recente. 404 se il catalogo non ne ha."""
    c = mercati_service.composizione(db, symbol)
    if c is None:
        raise HTTPException(status_code=404, detail="Nessun costituente nel catalogo")
    return ComposizioneOut(**c)


class RiepilogoConfrontoMercatiOut(BaseModel):
    rendimento: float
    peggior_calo: float


class ConfrontoMercatiOut(BaseModel):
    date: list[str]
    #: simbolo -> valori in base 100, allineati a `date`.
    serie: dict[str, list[float]]
    riepilogo: dict[str, RiepilogoConfrontoMercatiOut]
    dal: str | None
    al: str | None


@router.get("/confronto", response_model=ConfrontoMercatiOut)
def get_confronto(
    simboli: Annotated[str, Query(description="fino a 6, separati da virgola: mercati o titoli del catalogo")],
    periodo: Annotated[Literal["1m", "3m", "6m", "ytd", "1a", "3a", "5a", "10a"], Query()] = "ytd",
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> ConfrontoMercatiOut:
    """FA-187: mercati e titoli in base 100 dalla stessa data."""
    elenco = list(dict.fromkeys(s.strip() for s in simboli.split(",") if s.strip()))
    if not elenco or len(elenco) > mercati_service.MAX_SIMBOLI:
        raise HTTPException(status_code=422, detail=f"da 1 a {mercati_service.MAX_SIMBOLI} simboli")
    try:
        return ConfrontoMercatiOut(**mercati_service.confronto(db, elenco, periodo))
    except mercati_service.SimboloSconosciuto as e:
        raise HTTPException(status_code=404, detail=f"Nessuna storia per {e.simbolo}") from e


class BorsaOut(BaseModel):
    regione: str
    nome: str
    #: «pre» | «seduta» | «after» | «chiusa»
    fase: str
    fino_alle: str | None
    prossima_fase: str | None
    dalle: str | None
    #: False: per questa borsa le festivita' non sono nel calendario dell'app.
    festivita_note: bool


class SessioniOut(BaseModel):
    adesso: str
    borse: list[BorsaOut]


@router.get("/sessioni", response_model=SessioniOut)
def get_sessioni(_user: User = Depends(get_current_user)) -> SessioniOut:
    """FA-191: lo stato delle borse e il prossimo cambio."""
    from app.services import sessioni_borsa  # noqa: PLC0415

    return SessioniOut(**sessioni_borsa.sessioni())


@router.get("/estesi", response_model=LiveAssetsOut)
def get_estesi(_user: User = Depends(get_current_user)) -> LiveAssetsOut:
    """FA-190: prezzo e variazione di oggi dei mercati che la home non mostra
    (Russell, DAX, CAC, FTSE 100, KOSPI, rame, dollaro, euro, yen)."""
    return CACHE_ESTESI.leggi()


class TesseraContestoOut(BaseModel):
    chiave: str
    nome: str
    valore: float
    #: «%» per tassi e ampiezza (il valore e' gia' una percentuale), «» per i livelli.
    unita: str
    #: il valore di un mese prima, per dire «da X a Y».
    prima: float | None
    #: solo per i livelli di mercato (VIX, dollaro): variazione relativa a un mese.
    variazione_relativa: float | None
    percentile: float | None
    percentile_dal: str | None
    serie: list[float]
    data: str | None
    nota: str | None
    simbolo: str | None


class ContestoOut(BaseModel):
    tessere: list[TesseraContestoOut]


@router.get("/contesto", response_model=ContestoOut)
def get_contesto(db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> ContestoOut:
    """FA-188: VIX, curva dei tassi, Fed e BCE, ampiezza, dollaro."""
    return ContestoOut(**mercati_service.contesto(db))


class SimboloCorrelazioneOut(BaseModel):
    symbol: str
    name: str
    category: str


class CorrelazioniOut(BaseModel):
    simboli: list[SimboloCorrelazioneOut]
    #: matrice[i][j]: correlazione dei rendimenti giornalieri; None con meno di
    #: 40 date comuni alla coppia.
    matrice: list[list[float | None]]
    un_anno_fa: list[list[float | None]]
    sedute: int
    al: str | None


@router.get("/correlazioni", response_model=CorrelazioniOut)
def get_correlazioni(
    sedute: Annotated[int, Query(description="60 o 250")] = 60,
    _user: User = Depends(get_current_user),
) -> CorrelazioniOut:
    """FA-189: correlazioni fra i mercati, adesso e un anno prima."""
    # Un intero controllato a mano: un Literal[60, 250] rifiuta la stringa
    # «60» che arriva dall'indirizzo.
    if sedute not in mercati_service.CACHE_CORRELAZIONI:
        raise HTTPException(status_code=422, detail="sedute: 60 o 250")
    return CorrelazioniOut(**mercati_service.CACHE_CORRELAZIONI[sedute].leggi())


@router.get("/panoramica", response_model=PanoramicaOut)
def get_panoramica(_user: User = Depends(get_current_user)) -> PanoramicaOut:
    """I rendimenti per periodo del paniere, alla chiusura giornaliera
    (FA-184). Dalla cache: il job dei dettagli la tiene calda."""
    return PanoramicaOut(**mercati_service.CACHE_PANORAMICA.leggi())


@router.get("/{symbol}/statistiche", response_model=StatisticheOut)
def get_statistiche(symbol: str, _user: User = Depends(get_current_user)) -> StatisticheOut:
    """Rendimenti, volatilita', distanza dai massimi, cali e calendario
    mensile di uno strumento (FA-185)."""
    meta = _LIVE_META.get(symbol)
    if meta is None:
        raise HTTPException(status_code=404, detail="Unknown market symbol")
    s = mercati_service.statistiche(symbol, meta[1])
    if s is None:
        raise HTTPException(status_code=404, detail="No market data available")
    return StatisticheOut(**s)


@router.get("/{symbol}/detail", response_model=MarketDetailOut)
def get_market_detail(
    symbol: str,
    range: Annotated[str, Query()] = "1d",
    storia: Annotated[Literal["recente", "completa"], Query()] = "recente",
    formato: Formato = "esteso",
    _user: User = Depends(get_current_user),
) -> MarketDetailOut | Response:
    """`storia=completa` rende tutte le barre giornaliere (dal 1927 per
    l'S&P 500): serve al server MCP per le domande sul passato. Il grafico
    chiede la recente, gli ultimi dieci anni."""
    if range not in (
        "5m", "30m", "1h", "1d", "1w", "1m",
        # legacy compat for old URLs/bookmarks ("all" removed from the
        # selector but still resolves → monthly; 4h dropped — see
        # services/timeframe_service.py for rationale)
        "all", "1y", "3m", "6m", "5y", "4h",
    ):
        raise HTTPException(status_code=422, detail="invalid timeframe")
    # Legacy 4h URL → fall through to "1h" inside market_detail_service
    # (its _RANGE_TO_YF doesn't have 4h anymore but the service maps
    # unknown keys to 1y; remap explicitly to keep intent).
    if range == "4h":
        range = "1h"

    meta = _LIVE_META.get(symbol)
    if meta is None:
        # Not one of the curated symbols. We could still try yfinance
        # blindly, but exposing arbitrary symbol fetch invites abuse —
        # the only consumer is the LiveAssetsPanel, so refusing
        # uncurated symbols is safer.
        raise HTTPException(status_code=404, detail="Unknown market symbol")
    name, category, flag = meta

    detail = market_detail_service.get_detail(symbol, range)
    if detail is None:
        raise HTTPException(status_code=404, detail="No market data available")
    if storia == "recente" and detail.range_key in market_detail_service.GIORNALIERI:
        detail = market_detail_service.taglia_agli_ultimi_anni(detail)

    quote_out: LiveQuoteOut | None = None
    using_futures = False
    quote_symbol: str | None = symbol
    try:
        q = live_quote_service.get_quote(symbol)
        future = _FUTURE_DI.get(symbol)
        if future and q is not None and q.market_state != "OPEN":
            q, using_futures = quotazione_da_mostrare(q, live_quote_service.get_quote(future))
            if using_futures:
                quote_symbol = future
        if q is not None:
            quote_out = LiveQuoteOut(
                price=q.price,
                prev_close=q.prev_close,
                change_abs=q.change_abs,
                change_pct=q.change_pct,
                market_state=q.market_state,
                currency=q.currency,
                error=q.error,
            )
    # There was an `except UpstreamError` here, unreachable:
    # live_quote_service does not raise the typed errors — it reports an
    # upstream problem on the RETURNED object, as `q.error`, which is read
    # into the response two lines above. The handler below stays as the
    # genuine last resort.
    except Exception as e:  # noqa: BLE001 — defensive last-resort
        logger.exception(f"[market_detail] unexpected error fetching quote for {symbol}: {e}")
        # Quote is best-effort; the chart still renders without it.
        quote_out = None

    ind = detail.indicators

    compatto = formato == "compatto"

    def _pts(series):
        # Nella forma compatta (FA-182) le serie si scrivono dopo, come valori.
        if compatto:
            return []
        return [IndicatorPointOut(date=p.date, value=p.value) for p in series]

    indicators_out = IndicatorBundleOut(
        ema20=_pts(ind.ema20),
        ema50=_pts(ind.ema50),
        ema200=_pts(ind.ema200),
        bb_upper=_pts(ind.bb_upper),
        bb_middle=_pts(ind.bb_middle),
        bb_lower=_pts(ind.bb_lower),
        rsi14=_pts(ind.rsi14),
        macd_line=_pts(ind.macd_line),
        macd_signal=_pts(ind.macd_signal),
        macd_hist=_pts(ind.macd_hist),
    )

    uscita = MarketDetailOut(
        symbol=symbol,
        name=name,
        category=category,
        flag=flag,
        range_key=detail.range_key,
        last_close=detail.last_close,
        prev_close=detail.prev_close,
        change_pct=detail.change_pct,
        high_window=detail.high_window,
        low_window=detail.low_window,
        high_52w=detail.high_52w,
        low_52w=detail.low_52w,
        indicators=indicators_out,
        bars=[
            OhlcvBarOut(
                date=b.date,
                open=b.open,
                high=b.high,
                low=b.low,
                close=b.close,
                volume=b.volume,
            )
            for b in detail.bars
        ],
        quote=quote_out,
        using_futures=using_futures,
        quote_symbol=quote_symbol,
    )
    if not compatto:
        return uscita
    corpo = json.loads(uscita.model_dump_json())
    corpo["indicators"].update(serie_compatte(ind, [b.date for b in detail.bars]))
    corpo["indicators_formato"] = "compatto"
    return Response(
        content=json.dumps(corpo, separators=(",", ":"), allow_nan=False),
        media_type="application/json",
    )
