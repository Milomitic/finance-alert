"""Come si dimensiona un campione di segnali. Fonte unica, e IMPORTABILE.

⚠️ PERCHE' QUESTO MODULO ESISTE, ed e' una lezione sulla collocazione che questo
progetto ha gia' pagato una volta.

`wilson_interval` viveva in `signal_drift_service` e `independent_blocks` /
`sized_interval` in `detector_performance_service`, **che importava il primo dal
secondo**. Quindi il cubo poteva dimensionare correttamente e il monitor di
drift no: importare le finestre indipendenti avrebbe chiuso un ciclo di import.

E infatti il drift dimensionava sulle RIGHE. Sul magazzino vivo questo teneva
acceso un allarme «candle_reversal in decadimento» su n=1372 righe che sono
**12 finestre indipendenti**, mentre il cubo accanto dichiarava lo stesso
detector non concludente. Due numeri diversi per la stessa domanda, ciascuno
coerente col proprio modulo.

E' la stessa forma di `app/indicators/periods.py`: una costante che vive dentro
un servizio non e' importabile da chi ne ha bisogno, quindi nessuno la importa,
quindi ognuno la riscrive — o, qui, fa a meno di importarla e misura peggio. La
domanda da farsi quando si dichiara un proprietario unico non e' «dove sta
bene» ma **«chi deve poterlo importare, e cosa si porta dietro se lo fa»**.

Un modulo FOGLIA, senza una sola dipendenza oltre la libreria standard, e'
importabile da ogni livello. `signal_drift_service` e
`detector_performance_service` ri-esportano i nomi, cosi' i chiamanti esistenti
continuano a funzionare.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date, timedelta

#: Livello di confidenza degli intervalli. 95% -> z ~ 1,96.
#: Scritto per esteso invece che con scipy: `norm.ppf(0.975)`, e scipy non e'
#: una dipendenza di questo progetto.
DEFAULT_Z = 1.959963984540054

#: Da giorni di borsa a giorni di calendario. Cinque sedute per settimana.
_TRADING_TO_CALENDAR = 7.0 / 5.0


def wilson_interval(hits: float, n: int, z: float = DEFAULT_Z) -> tuple[float, float]:
    """Intervallo di Wilson al 95% per una proporzione binomiale, come coppia
    (basso, alto) di PROPORZIONI in [0, 1].

    Wilson e non l'approssimazione normale di Wald perche' e' limitato a [0,1],
    ben calibrato a n piccolo e a p estremo (0% / 100%), e si allarga
    naturalmente quando n cala. n == 0 -> (0, 1), cioe' completamente
    disinformativo, che e' la risposta giusta.
    """
    if n <= 0:
        return 0.0, 1.0
    phat = hits / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (phat + z2 / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(phat * (1.0 - phat) / n + z2 / (4 * n * n))
    return max(0.0, center - margin), min(1.0, center + margin)


def independent_blocks(dates: Sequence[date], horizon_trading_days: int) -> int:
    """Quante finestre NON SOVRAPPOSTE, lunghe un orizzonte, coprono questi scatti.

    Copertura greedy: si scorrono le date ordinate, si apre un blocco al primo
    scatto e si assorbe ogni scatto successivo la cui finestra in avanti lo
    sovrappone ancora.

    E' il denominatore onesto del tasso di un detector. Due scatti a tre giorni
    di distanza, etichettati entrambi a 21 sedute in avanti, condividono 18/21
    della finestra e quasi tutto il mercato: contarli come due estrazioni
    indipendenti e' cio' che fa leggere un solo trimestre buono come prova
    schiacciante. Gli scatti dello stesso giorno su molti titoli collassano piu'
    di tutti — sono un giorno di mercato visto N volte.

    Deliberatamente CONSERVATIVO: ignora che titoli diversi non sono
    perfettamente correlati, quindi SOTTOSTIMA il conteggio indipendente vero.
    Un errore in questa direzione costa un'affermazione che non si puo' ancora
    sostenere; nell'altra ne fabbrica una.
    """
    if not dates:
        return 0
    span = max(1, math.ceil(horizon_trading_days * _TRADING_TO_CALENDAR))
    blocks = 0
    open_until: date | None = None
    for d in sorted(dates):
        if open_until is None or d >= open_until:
            blocks += 1
            open_until = d + timedelta(days=span)
    return blocks


def sized_interval(*, rate_pct: float, effective_n: int) -> tuple[float, float]:
    """Intervallo di Wilson al 95% attorno a `rate_pct`, dimensionato sul
    conteggio INDIPENDENTE.

    La stima puntuale tiene ogni riga — e' la miglior ipotesi disponibile.
    Solo la LARGHEZZA paga la sovrapposizione, che e' esattamente dove la
    sovrapposizione fa danno: 81,8% su 99 righe agglomerate resta la miglior
    stima, semplicemente non si distingue da un lancio di moneta.
    """
    lo, hi = wilson_interval(rate_pct / 100.0 * effective_n, effective_n)
    return round(lo * 100.0, 1), round(hi * 100.0, 1)
