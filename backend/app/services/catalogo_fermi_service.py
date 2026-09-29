"""I titoli fermi del catalogo, a schermo nella Diagnostica (2026-09-29).

FA-071 ha fatto si' che la scansione salti un titolo la cui serie non avanza
(`ohlcv_service.series_stalled_clause`), ma nessuna schermata diceva QUALI:
per saperlo serviva una query nel pod. Qui l'elenco, con cio' che l'app sa di
ciascuno, e una verifica sulla fonte a richiesta.

⚠️ Nessuna «causa probabile» scritta a tavolino. Misurato il 2026-09-29 sui 12
titoli fermi: nessuno sta piu' in un indice, e fra loro ci sono nomi grossi
(BK, EA, AVB, EQR) — dal solo catalogo non si distingue un cambio di simbolo
da una fusione o da un'uscita dal listino. La verifica mostra cio' che Yahoo
risponde (barre recenti del simbolo, simboli con lo stesso nome) e lascia la
lettura a chi guarda: «BNY Mellon» rende solo fondi, «Electronic Arts» solo
quotazioni tedesche secondarie, e sono due risposte diverse.

La verifica va in rete solo su richiesta, un titolo alla volta.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from loguru import logger
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Index, OhlcvDaily, Position, Stock, StockIndex
from app.models.preferito import Preferito
from app.services.ohlcv_service import series_stalled_clause


@dataclass
class TitoloFermo:
    ticker: str
    nome: str | None
    borsa: str | None
    ultima_barra: date | None
    tentativi: int
    ultimo_tentativo: date | None
    indici: list[str]
    in_posizione: bool
    preferito: bool


@dataclass
class Catalogo:
    totale: int
    senza_settore: int
    senza_capitalizzazione: int
    fermi: list[TitoloFermo] = field(default_factory=list)


def _giorno(v) -> date | None:
    """Un giorno da un datetime, da un date, o dal TESTO che SQLite rende."""
    if v is None:
        return None
    if isinstance(v, str):
        return date.fromisoformat(v[:10])
    return v.date() if hasattr(v, "date") and callable(v.date) else v


def catalogo(db: Session) -> Catalogo:
    ultima = (
        select(func.max(OhlcvDaily.date))
        .where(OhlcvDaily.stock_id == Stock.id)
        .correlate(Stock)
        .scalar_subquery()
    )
    righe = db.execute(
        select(Stock, ultima).where(series_stalled_clause()).order_by(ultima.asc().nullsfirst())
    ).all()
    ids = [s.id for s, _ in righe]
    indici: dict[int, list[str]] = {}
    for sid, codice in db.execute(
        select(StockIndex.stock_id, Index.code)
        .join(Index, Index.id == StockIndex.index_id)
        .where(StockIndex.stock_id.in_(ids))
    ).all():
        indici.setdefault(sid, []).append(codice)
    aperte = set(db.execute(
        select(Position.stock_id).where(Position.stock_id.in_(ids), Position.closed_at.is_(None))
    ).scalars())
    preferiti = set(db.execute(select(Preferito.stock_id).where(Preferito.stock_id.in_(ids))).scalars())

    return Catalogo(
        totale=db.execute(select(func.count()).select_from(Stock)).scalar_one(),
        senza_settore=db.execute(
            select(func.count()).select_from(Stock).where(or_(Stock.sector.is_(None), Stock.sector == ""))
        ).scalar_one(),
        senza_capitalizzazione=db.execute(
            select(func.count()).select_from(Stock).where(Stock.market_cap.is_(None))
        ).scalar_one(),
        fermi=[
            TitoloFermo(
                ticker=s.ticker, nome=s.name, borsa=s.exchange, ultima_barra=_giorno(u),
                tentativi=s.ohlcv_nodata_streak or 0,
                ultimo_tentativo=_giorno(s.ohlcv_last_nodata_at),
                indici=sorted(indici.get(s.id, [])),
                in_posizione=s.id in aperte, preferito=s.id in preferiti,
            )
            for s, u in righe
        ],
    )


@dataclass
class Candidato:
    simbolo: str
    borsa: str | None
    tipo: str | None
    nome: str | None


@dataclass
class Verifica:
    ticker: str
    #: Barre che Yahoo da' OGGI per il simbolo, sull'ultimo mese.
    barre_recenti: int | None
    ultima_barra_fonte: date | None
    #: Simboli che la ricerca per NOME restituisce, diversi da questo.
    candidati: list[Candidato]
    errore: str | None = None


def verifica(ticker: str, nome: str | None) -> Verifica:
    """Che cosa risponde Yahoo adesso. Va in rete: solo su richiesta."""
    import yfinance as yf

    barre: int | None = None
    ultima: date | None = None
    candidati: list[Candidato] = []
    errori: list[str] = []
    try:
        storia = yf.Ticker(ticker).history(period="1mo", auto_adjust=False)
        barre = len(storia)
        if barre:
            ultima = storia.index[-1].date()
    except Exception as exc:  # noqa: BLE001 — si dice, non si solleva
        errori.append(f"storia: {exc}")
    if nome:
        try:
            for q in yf.Search(nome, max_results=8, news_count=0).quotes or []:
                simbolo = q.get("symbol")
                if simbolo and simbolo != ticker:
                    candidati.append(Candidato(
                        simbolo=simbolo, borsa=q.get("exchDisp") or q.get("exchange"),
                        tipo=q.get("quoteType"), nome=q.get("shortname") or q.get("longname"),
                    ))
        except Exception as exc:  # noqa: BLE001
            errori.append(f"ricerca: {exc}")
    if errori:
        logger.warning(f"[catalogo_fermi] verifica {ticker}: {'; '.join(errori)}")
    return Verifica(ticker=ticker, barre_recenti=barre, ultima_barra_fonte=ultima,
                    candidati=candidati, errore="; ".join(errori) or None)
