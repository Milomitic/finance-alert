"""Le fonti delle variabili di mercato del contesto d'emissione (FA-150).

Si costruisce UNA volta per scansione, prima del giro sui titoli: il rendimento
giornaliero mediano del catalogo (per la beta) e la mediana del rendimento a 63
sedute di ogni settore (per la forza relativa). Il calcolo per titolo sta in
`app.signals.contesto_emissione`, che resta puro; qui c'e' solo cio' che
richiede il database.

⚠️ Best-effort per costruzione: se questo fallisce la scansione deve
continuare, con le chiavi della versione 2 assenti (= non note). Un contesto
incompleto e' un dato; una scansione ferma no.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Stock
from app.services import stock_fundamentals_service
from app.services.signal_outcome_service import _MIN_UNIVERSE_PER_DATE, _load_universe_closes

#: Giorni di calendario caricati: coprono le 260 barre della finestra dello
#: scan (`scan_service._load_ohlcv`), che sono quelle su cui si calcola la beta.
_GIORNI = 400

#: Un settore con meno titoli di cosi' non ha una mediana che valga la pena.
MIN_SETTORE = 5

#: Un titolo la cui ultima barra e' piu' vecchia di cosi' rispetto al catalogo
#: non entra nella mediana di settore: porterebbe un rendimento di mesi fa.
_FRESCHEZZA = timedelta(days=10)


@dataclass(frozen=True)
class Mercato:
    #: {giorno: rendimento giornaliero mediano del catalogo, solo societa'}
    rendimenti: dict[date, float] = field(default_factory=dict)
    #: {settore: mediana del rendimento a 63 sedute}
    rs63_settore: dict[str, float] = field(default_factory=dict)

    def per_titolo(self, stock: Stock) -> dict:
        """Gli argomenti per `contesto_emissione.contesto` di questo titolo."""
        return {
            "rendimenti_mercato": self.rendimenti or None,
            "rs63_settore": self.rs63_settore.get(stock.sector) if stock.sector else None,
            "trimestrali": stock_fundamentals_service.trimestrali_cached(stock.ticker),
        }


def rendimenti_mediani(serie: dict[int, tuple[np.ndarray, np.ndarray]]) -> dict[date, float]:
    """{giorno: mediana dei rendimenti giornalieri}, con la stessa soglia di
    titoli per data del riferimento degli esiti."""
    per_giorno: dict[date, list[float]] = defaultdict(list)
    for ds, cs in serie.values():
        for i in range(1, len(cs)):
            if cs[i - 1] > 0:
                per_giorno[ds[i]].append(float(cs[i] / cs[i - 1] - 1.0))
    return {
        g: float(np.median(v)) for g, v in per_giorno.items() if len(v) >= _MIN_UNIVERSE_PER_DATE
    }


def mediane_di_settore(
    serie: dict[int, tuple[np.ndarray, np.ndarray]], settori: dict[int, str],
) -> dict[str, float]:
    """{settore: mediana del rendimento a 63 sedute all'ultima barra}, sui soli
    titoli aggiornati."""
    ultime = [ds[-1] for ds, _ in serie.values() if len(ds)]
    if not ultime:
        return {}
    soglia = max(ultime) - _FRESCHEZZA
    per_settore: dict[str, list[float]] = defaultdict(list)
    for sid, (ds, cs) in serie.items():
        settore = settori.get(sid)
        if not settore or len(cs) <= 63 or ds[-1] < soglia or cs[-64] <= 0:
            continue
        per_settore[settore].append(float(cs[-1] / cs[-64] - 1.0))
    return {s: float(np.median(v)) for s, v in per_settore.items() if len(v) >= MIN_SETTORE}


def costruisci(db: Session, *, oggi: date | None = None) -> Mercato:
    oggi = oggi or datetime.now(UTC).date()
    serie = _load_universe_closes(db, since=oggi - timedelta(days=_GIORNI), exclude_etf=True)
    settori = dict(db.execute(select(Stock.id, Stock.sector)).all())
    return Mercato(rendimenti_mediani(serie), mediane_di_settore(serie, settori))
