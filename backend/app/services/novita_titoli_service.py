"""Le novita' sui titoli che contano, nel digest del mattino (2026-09-29).

Tre fatti, tutti gia' nella cache dei fondamentali e fino a qui visibili solo
aprendo il titolo:

- **analisti**: un cambio di giudizio, una copertura nuova, un prezzo-obiettivo
  alzato o abbassato. Le conferme senza cambio («Maintains» con lo stesso
  target) no: sono ~25 volte piu' numerose e non dicono niente di nuovo;
- **insider**: gli ACQUISTI. Le vendite no, e non per dimenticanza: su un
  titolo grande sono quotidiane (piani automatici, tasse sulle azioni
  assegnate) e seppellirebbero il resto;
- **trimestrali pubblicate**: utile per azione contro atteso, con la sorpresa;
- **superinvestor**: un fondo che nel suo ultimo 13F apre, aumenta, riduce o
  chiude la posizione. Viene dai depositi (`institutional_*`), non dalla cache,
  e la data e' il giorno in cui l'app ha ricevuto il deposito: i 13F escono
  45 giorni dopo la fine del trimestre, quindi la data del trimestre direbbe
  «sei settimane fa» proprio del fatto appena saputo.

Sono fatti, non previsioni: nessuno di questi numeri entra in un punteggio.

⚠️ Due cose che una finestra sulle date non puo' fare, e il perche' del
registro `novita_notificate`. La cache si rinnova ogni sette giorni, quindi un
fatto del lunedi' puo' affiorare il giovedi': con la finestra «ieri e oggi» si
perderebbe, con una finestra larga si ripeterebbe ogni mattina. Si prendono
invece i fatti degli ultimi `GIORNI` non ancora mandati, e li si segna dopo
un invio riuscito. E per i pochi titoli seguiti la cache si rinfresca se ha
piu' di `MAX_ETA_ORE` ore, cosi' un fatto arriva il giorno dopo e non la
settimana dopo.
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models import (
    Institutional,
    InstitutionalFiling,
    InstitutionalHolding,
    NovitaNotificata,
    Stock,
)
from app.services import rilevanza_service, stock_fundamentals_service
from app.services.analyst_actions_feed import CHANGE_ACTIONS
from app.services.institutional_service import _substantiated_new

#: I fatti piu' vecchi di cosi' non sono piu' «novita'», anche se mai mandati.
GIORNI = 14
#: Oltre quest'eta' la cache di un titolo seguito si riscarica.
MAX_ETA_ORE = 20

ANALISTA = "analista"
INSIDER = "insider"
TRIMESTRALE = "trimestrale"
SUPERINVESTOR = "superinvestor"

#: Le mosse di un fondo che fanno notizia; «hold» e le righe senza azione no.
_MOSSE_13F = {
    "new": "apre una posizione",
    "add": "aumenta la posizione",
    "reduce": "riduce la posizione",
    "sold_out": "esce dal titolo",
}

_ACQUISTO = re.compile(r"\b(purchase|buy)\b", re.I)
_TARGET_MOSSO = {"Raises", "Lowers"}


@dataclass(frozen=True)
class Novita:
    chiave: str
    ticker: str
    nome: str | None
    rilevanza: str
    data: date
    tipo: str
    testo: str


def _chiave(*parti: Any) -> str:
    return hashlib.sha1("|".join(str(p) for p in parti).encode("utf-8")).hexdigest()


def _data(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _num(v: float | None) -> str:
    return f"{v:g}" if isinstance(v, (int, float)) else "?"


def _testo_analista(a: Any) -> str | None:
    azione = getattr(a, "action", "") or ""
    ditta = getattr(a, "firm", "") or "Un analista"
    a_voto = getattr(a, "to_grade", "") or ""
    da_voto = getattr(a, "from_grade", "") or ""
    target_da = getattr(a, "prior_price_target", None)
    target_a = getattr(a, "current_price_target", None)
    mossa_target = getattr(a, "price_target_action", None)

    parti: list[str] = []
    if azione == "init":
        parti.append(f"inizia la copertura: {a_voto}" if a_voto else "inizia la copertura")
    elif azione in ("up", "down"):
        verbo = "alza" if azione == "up" else "abbassa"
        parti.append(f"{verbo} il giudizio a {a_voto}" + (f" (era {da_voto})" if da_voto else ""))
    if mossa_target in _TARGET_MOSSO and target_a is not None:
        verbo = "alza" if mossa_target == "Raises" else "abbassa"
        freccia = f"{_num(target_da)} → {_num(target_a)}" if target_da is not None else _num(target_a)
        parti.append(f"{verbo} il prezzo-obiettivo: {freccia}")
    if not parti:
        return None
    return f"{ditta} {', '.join(parti)}"


def dai_fondamentali(fund: Any, *, ticker: str, nome: str | None, rilevanza: str,
                     dal: date) -> list[Novita]:
    """Le novita' di un titolo dalla sua voce di cache, dal giorno `dal`."""
    out: list[Novita] = []

    def aggiungi(d: date | None, tipo: str, testo: str | None, *identita: Any) -> None:
        if d is None or d < dal or not testo:
            return
        out.append(Novita(_chiave(tipo, ticker, d, *identita), ticker, nome, rilevanza, d, tipo, testo))

    for a in getattr(fund, "analyst_actions", None) or []:
        azione = getattr(a, "action", "") or ""
        cambia = azione in CHANGE_ACTIONS or getattr(a, "price_target_action", None) in _TARGET_MOSSO
        if cambia:
            aggiungi(_data(getattr(a, "date", None)), ANALISTA, _testo_analista(a),
                     getattr(a, "firm", ""), azione, getattr(a, "to_grade", ""),
                     getattr(a, "current_price_target", None))

    for t in getattr(fund, "insiders", None) or []:
        if _ACQUISTO.search(getattr(t, "transaction", "") or ""):
            chi = getattr(t, "insider", "") or "Un insider"
            ruolo = getattr(t, "position", "") or ""
            quanto = getattr(t, "value", None)
            testo = f"{chi}{f' ({ruolo})' if ruolo else ''} compra" + (
                f" per {quanto:,.0f} $".replace(",", ".") if isinstance(quanto, (int, float)) else ""
            )
            aggiungi(_data(getattr(t, "date", None)), INSIDER, testo,
                     chi, getattr(t, "shares", None))

    for e in getattr(fund, "earnings", None) or []:
        riportato = getattr(e, "eps_reported", None)
        if riportato is None:
            continue
        atteso = getattr(e, "eps_estimate", None)
        sorpresa = getattr(e, "surprise_pct", None)
        testo = f"trimestrale pubblicata: utile per azione {_num(riportato)}"
        if atteso is not None:
            testo += f" contro {_num(atteso)} atteso"
        if isinstance(sorpresa, (int, float)):
            testo += f" ({sorpresa:+.1f}%)"
        aggiungi(_data(getattr(e, "date", None)), TRIMESTRALE, testo)

    return out


def _forme(ticker: str) -> set[str]:
    """Il catalogo scrive `BRK-B`, i depositi `BRK.B`: si cercano entrambe."""
    return {ticker, ticker.replace("-", ".")}


def dai_depositi_13f(db: Session, titoli: list[tuple[Stock, str]], dal: date) -> list[Novita]:
    """Le mosse dei fondi sui titoli dati, nei depositi ricevuti dal giorno
    `dal`. Un «apre una posizione» di un fondo con un deposito solo non si
    dice: senza un deposito precedente non e' un'apertura osservata, e'
    «non so» (`_substantiated_new`, la stessa regola del dettaglio titolo)."""
    per_forma = {f: (s, ril) for s, ril in titoli for f in _forme(s.ticker)}
    if not per_forma:
        return []
    righe = db.execute(
        select(
            Institutional.id, Institutional.name, InstitutionalFiling.period_end_date,
            InstitutionalFiling.created_at, InstitutionalHolding.ticker,
            InstitutionalHolding.action, InstitutionalHolding.qoq_change_pct,
            InstitutionalHolding.portfolio_pct,
        )
        .join(InstitutionalFiling, InstitutionalFiling.id == InstitutionalHolding.filing_id)
        .join(Institutional, Institutional.id == InstitutionalFiling.institutional_id)
        .where(
            InstitutionalHolding.ticker.in_(per_forma),
            InstitutionalHolding.action.in_(_MOSSE_13F),
            InstitutionalFiling.created_at >= datetime.combine(dal, datetime.min.time()),
        )
    ).all()
    fidati = _substantiated_new(db, ((r[0], r[2]) for r in righe if r[5] == "new"))
    out: list[Novita] = []
    for fondo_id, fondo, periodo, ricevuto, forma, mossa, variazione, peso in righe:
        if mossa == "new" and fondo_id not in fidati:
            continue
        s, ril = per_forma[forma]
        testo = f"{fondo} {_MOSSE_13F[mossa]}"
        if mossa in ("add", "reduce") and isinstance(variazione, (int, float)):
            testo += f" ({variazione:+.0f}% di azioni)"
        if mossa != "sold_out" and isinstance(peso, (int, float)) and peso >= 0.1:
            testo += f", {peso:.1f}% del portafoglio"
        testo += f" — 13F al {periodo:%d/%m/%Y}"
        out.append(Novita(
            _chiave(SUPERINVESTOR, s.ticker, fondo_id, periodo, mossa),
            s.ticker, s.name, ril, ricevuto.date(), SUPERINVESTOR, testo,
        ))
    return out


def _rinfresca_se_vecchie(tickers: set[str]) -> None:
    adesso = time.time()
    for t in sorted(tickers):
        voce = stock_fundamentals_service._CACHE.get(t)
        if voce is not None and adesso - voce.fetched_at < MAX_ETA_ORE * 3600:
            continue
        try:
            stock_fundamentals_service.get_fundamentals(t, force_refresh=True)
        except Exception as exc:  # noqa: BLE001 — un titolo non ferma gli altri
            logger.warning(f"[novita] {t}: fondamentali non disponibili: {exc}")


def raccogli(db: Session, dal: date, *, rinfresca: bool) -> list[Novita]:
    """Tutte le novita' dal giorno `dal` sui titoli che contano, mandate o no;
    posizioni prima, poi per data dal piu' recente.

    ⚠️ `rinfresca=False` per chi risponde a una pagina: il rinfresco scarica da
    Yahoo, e un'apertura del cruscotto non deve aspettare la rete."""
    rilevanti = rilevanza_service.titoli_rilevanti(db)
    if not rilevanti:
        return []
    titoli = db.execute(select(Stock).where(Stock.id.in_(rilevanti))).scalars().all()
    if rinfresca:
        _rinfresca_se_vecchie({s.ticker for s in titoli})
    tutte: list[Novita] = []
    for s in titoli:
        fund = stock_fundamentals_service._CACHE.get(s.ticker)
        if fund is None or getattr(fund, "error", None):
            continue
        tutte += dai_fondamentali(fund, ticker=s.ticker, nome=s.name,
                                  rilevanza=rilevanti[s.id], dal=dal)
    tutte += dai_depositi_13f(db, [(s, rilevanti[s.id]) for s in titoli], dal)
    # Due voci identiche nello stesso titolo (news e tabella) sono un fatto solo.
    uniche = list({n.chiave: n for n in tutte}.values())
    uniche.sort(key=lambda n: (-rilevanza_service.PESO[n.rilevanza], n.ticker, -n.data.toordinal()))
    return uniche


def da_mandare(db: Session, oggi: date, *, rinfresca: bool = True) -> list[Novita]:
    """Le novita' degli ultimi `GIORNI` sui titoli che contano, non ancora
    mandate."""
    tutte = raccogli(db, oggi - timedelta(days=GIORNI), rinfresca=rinfresca)
    if not tutte:
        return []
    gia = set(db.execute(
        select(NovitaNotificata.chiave).where(NovitaNotificata.chiave.in_({n.chiave for n in tutte}))
    ).scalars())
    return [n for n in tutte if n.chiave not in gia]


def segna_mandate(db: Session, novita: list[Novita]) -> None:
    if not novita:
        return
    righe = [{"chiave": n.chiave} for n in {n.chiave: n for n in novita}.values()]
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    db.execute(insert(NovitaNotificata).values(righe).on_conflict_do_nothing())
    db.commit()
