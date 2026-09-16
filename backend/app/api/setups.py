"""Setups API — what is FORMING, ahead of the signal.

Note what this payload deliberately does NOT contain: a probability. Setups
carry `convenience`, an attention/ordering score, and the response says so in
its field docs so a future consumer can't mistake one for the other.
"""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import Stock, StockSetup, User
from app.models.stock_setup import STATUS_ACTIVE, STATUS_CONVERTED, STATUS_EXPIRED
from app.services import setup_service, stock_fundamentals_service

router = APIRouter(prefix="/api/setups", tags=["setups"])

_NUMERO_DECIMALE = re.compile(r"\d+[.,]\d+")


def condition_key(missing: str) -> str:
    """La chiave di raggruppamento per condizione, gemella di `conditionKey` in
    `frontend/src/lib/setupGrouping.ts`: i numeri decimali diventano «#», poi
    trim e minuscole. Deve restare IDENTICA a quella, altrimenti i conteggi
    per condizione non trovano il loro gruppo a schermo
    (`tests/test_setups_conteggi_popolazione.py` le confronta)."""
    return _NUMERO_DECIMALE.sub("#", missing).strip().lower()


class SetupOut(BaseModel):
    id: int
    ticker: str
    name: str | None = None
    detector: str
    tone: str
    #: 0..1 — share of the detector's gate chain already satisfied. A property
    #: of the DETECTOR: every setup of the same detector at the same stage
    #: carries the same value, so it cannot rank two of them against each other.
    proximity: float
    #: Distance from price to the trigger level, in ATR units — the per-SETUP
    #: counterpart to `proximity`. Near 0 means a normal day's move would fire
    #: it. Null when the trigger is not a price crossing (squeeze_expansion
    #: waits on volatility) or when the row predates the field.
    distance_atr: float | None = None
    #: 0..100 ATTENTION score for ordering. NOT a probability: setups make no
    #: forecast, and nothing in the engine's calibration applies to them.
    convenience: float
    #: What still has to happen for the signal to fire — the actionable part.
    missing: str
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    annotations: dict | None = None
    #: The measured 0..1 factors behind the setup. Stored since day one and
    #: never surfaced — the detail panel shows them so the wait can be read as
    #: evidence rather than as an assertion.
    factors: dict[str, float] | None = None
    #: "active" | "converted" | "expired". Closed setups are kept, never
    #: deleted: an expired one is half of the conversion rate, and dropping
    #: them would leave only the successes on record.
    status: str = "active"
    #: Perche' si e' chiuso senza convertire: "stale" (le condizioni si sono
    #: sfaldate), "aged" (ha toccato il tetto d'attesa restando valido),
    #: "decayed" (e' sceso sotto la soglia di attenzione).
    #:
    #: ⚠️ `decayed` NON entra nel denominatore del tasso di conversione: un
    #: setup ritirato non ha mai avuto l'occasione di convertire. Prima della
    #: migrazione FA-061 quelle righe venivano CANCELLATE, quindi il tasso gia'
    #: non le contava — cio' che cambia e' che ora esistono.
    closed_reason: str | None = None
    resolved_at: str | None = None
    #: Days between first sighting and the signal firing — the warning this
    #: setup actually gave. Only set on converted rows.
    lead_days: int | None = None
    converted_alert_id: int | None = None
    #: L'ultimo giorno in cui il setup puo ancora essere pendente — il TETTO da
    #: `first_seen_at`, non la scadenza scorrevole da `last_seen_at`, che si
    #: sposta a ogni scansione e non direbbe quando il setup si risolve. Il
    #: proprietario della regola e `setup_service.pending_until`.
    pending_until: str | None = None
    #: Prossima trimestrale del ticker, SOLO da cache: questo path non puo
    #: innescare una chiamata yfinance. Null = sconosciuto, che non e «nessuna
    #: trimestrale» — chi rende la riga non deve trasformare l'uno nell'altro.
    #:
    #: ⚠️ Viaggia GREZZA, senza un booleano «dentro la finestra» calcolato qui.
    #: I consumatori hanno finestre diverse — l'orizzonte di un segnale e la
    #: vita residua di un setup — e un booleano precalcolato ne servirebbe uno
    #: solo, obbligando l'altro a ricostruirsi comunque la data.
    next_earnings_date: str | None = None


class SetupListOut(BaseModel):
    setups: list[SetupOut]
    #: Righe che soddisfano i filtri, NON quelle rese. Senza, una lista
    #: troncata e' indistinguibile da una completa: in produzione erano 1.415
    #: setup attivi dietro una risposta da 50, e niente lo diceva.
    total: int = 0
    has_more: bool = False
    #: Quanti setup per detector nella POPOLAZIONE filtrata, e deliberatamente
    #: IGNORANDO il filtro `detector`. I chip contavano le righe ricevute —
    #: un conteggio che cambia con la dimensione della pagina non e' un
    #: conteggio — e devono restare tutti visibili dopo che se ne preme uno:
    #: un chip che sparisce appena lo selezioni e' una trappola.
    counts_by_detector: dict[str, int] = {}
    #: Quanti setup per CONDIZIONE (la chiave di `condition_key`) nella
    #: popolazione filtrata, filtro `detector` compreso: sono i gruppi che la
    #: lista rende. Il gruppo a schermo contava le righe della pagina, cioe'
    #: un numero che cambiava con la paginazione.
    counts_by_condition: dict[str, int] = {}
    #: The feature's own report card: does it convert, and with how much
    #: warning. `conversion_rate`/`avg_lead_days` are null until something
    #: resolves — null means "not known yet", not "zero".
    stats: dict


@router.get("", response_model=SetupListOut)
def list_setups(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    tone: str | None = None,
    ticker: str | None = None,
    detector: str | None = None,
    #: `None` = l'ordine naturale della vista (convenienza sugli attivi, data
    #: di risoluzione sui chiusi). Additivo: chi non lo passa non cambia
    #: comportamento.
    sort: str | None = Query(
        None, pattern="^(convenience|ticker|waiting|distance)$",
        description="convenience | ticker | waiting | distance",
    ),
    status: str = Query(
        STATUS_ACTIVE,
        pattern="^(active|converted|expired|closed|all)$",
        description="active (default), converted, expired, closed (both), or all.",
    ),
) -> SetupListOut:
    q = (
        select(StockSetup, Stock)
        .join(Stock, Stock.id == StockSetup.stock_id)
    )
    # A setup that resolved is the only record of whether the feature works —
    # the conversion rate and the lead time both come from these rows — and
    # until now nothing could ask for them.
    if status == "closed":
        q = q.where(StockSetup.status.in_((STATUS_CONVERTED, STATUS_EXPIRED)))
    elif status != "all":
        q = q.where(StockSetup.status == status)
    if tone in ("bull", "bear"):
        q = q.where(StockSetup.tone == tone)
    if ticker:
        # Per-stock view (the detail page). Deliberately NOT limited to the
        # shortlist: on a page about ONE stock, "this setup exists but ranks
        # 14th market-wide" is still worth seeing. The global list is the one
        # that has to stay short to be usable.
        q = q.where(Stock.ticker == ticker.upper())
    elif status == STATUS_ACTIVE:
        # Rows outside their detector's top N still exist — they keep their
        # history so `lead_days` stays honest — but are not what the user is
        # asked to scan. The shortlist ranks LIVE candidates, so it is not
        # applied to closed rows: there the question is what happened, not
        # what deserves attention now.
        q = q.where(StockSetup.shortlisted.is_(True))

    # ⚠️ I conteggi per detector si prendono PRIMA di applicare il filtro
    # `detector`: descrivono la popolazione fra cui si sceglie, non quella
    # scelta. Applicarlo qui farebbe collassare i chip a uno solo appena se ne
    # preme uno.
    _sub = q.subquery()
    conteggi = dict(db.execute(
        select(_sub.c.detector, func.count()).group_by(_sub.c.detector)
    ).all())

    if detector:
        q = q.where(StockSetup.detector == detector)

    totale = int(db.execute(
        select(func.count()).select_from(q.subquery())
    ).scalar_one())
    _filtrata = q.subquery()
    per_condizione: dict[str, int] = {}
    for (missing,) in db.execute(select(_filtrata.c.missing)).all():
        k = condition_key(missing or "")
        per_condizione[k] = per_condizione.get(k, 0) + 1

    # L'ordinamento vive nella QUERY, non nella pagina: ordinare lato client
    # riordina le righe ricevute, quindi «il primo per ticker» era il minimo
    # dei cinquanta e non dei millequattrocento. Il pareggio si rompe sempre
    # sul ticker, cosi' l'ordine e' stabile fra due richieste.
    if sort == "ticker":
        q = q.order_by(Stock.ticker.asc())
    elif sort == "waiting":
        # Attesa piu' lunga = vista per prima. Nulla in fondo.
        q = q.order_by(StockSetup.first_seen_at.asc().nullslast(), Stock.ticker.asc())
    elif sort == "distance":
        # Distanza dal grilletto in unita' di ATR: piu' VICINO prima, ed e'
        # l'unica chiave dove «meno e' meglio». Chi non ha una distanza
        # misurabile (lo squeeze aspetta la volatilita', non un prezzo) va in
        # fondo invece di ordinarsi a caso.
        q = q.order_by(StockSetup.distance_atr.asc().nullslast(), Stock.ticker.asc())
    elif sort == "convenience" or status == STATUS_ACTIVE:
        # La convenienza e' sia una scelta esplicita sia l'ordine naturale
        # degli attivi: lo stesso ramo serve entrambe.
        q = q.order_by(StockSetup.convenience.desc(), Stock.ticker.asc())
    else:
        # Most recently resolved first: the outcome view is a history.
        q = q.order_by(StockSetup.resolved_at.desc().nullslast(), Stock.ticker.asc())
    q = q.limit(limit).offset(offset)

    rows = db.execute(q).all()
    # Un solo passaggio cache-only sui ticker DISTINTI della pagina: nessuna
    # query, nessuna rete, al piu `limit` letture da un dict. Stessa forma del
    # passaggio che `list_alerts` fa sulla propria pagina.
    earnings_by_ticker = stock_fundamentals_service.next_earnings_dates_cached(
        {stock.ticker for _, stock in rows}
    )

    out: list[SetupOut] = []
    for row, stock in rows:
        try:
            ann = json.loads(row.annotations_json) if row.annotations_json else None
        except (ValueError, TypeError):
            ann = None
        try:
            fac = json.loads(row.factors_json) if row.factors_json else None
        except (ValueError, TypeError):
            fac = None
        out.append(
            SetupOut(
                id=row.id, ticker=stock.ticker, name=stock.name,
                detector=row.detector, tone=row.tone,
                proximity=row.proximity, distance_atr=row.distance_atr,
                convenience=row.convenience,
                missing=row.missing,
                first_seen_at=row.first_seen_at.isoformat() if row.first_seen_at else None,
                last_seen_at=row.last_seen_at.isoformat() if row.last_seen_at else None,
                annotations=ann, factors=fac,
                status=row.status,
                closed_reason=row.closed_reason,
                resolved_at=row.resolved_at.isoformat() if row.resolved_at else None,
                lead_days=row.lead_days,
                converted_alert_id=row.converted_alert_id,
                pending_until=(
                    d.isoformat()
                    if (d := setup_service.pending_until(row.first_seen_at))
                    else None
                ),
                next_earnings_date=(
                    e.isoformat()
                    if (e := earnings_by_ticker.get(stock.ticker))
                    else None
                ),
            )
        )
    return SetupListOut(
        setups=out,
        total=totale,
        has_more=offset + len(out) < totale,
        counts_by_detector=conteggi,
        counts_by_condition=per_condizione,
        stats=setup_service.conversion_stats(db),
    )
