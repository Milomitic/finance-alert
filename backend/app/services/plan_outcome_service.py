"""La gara fra stop e target di un piano, barra per barra.

Risponde a «il piano mostrato a schermo avrebbe pagato?», che e' una domanda
DIVERSA da quella del magazzino `signal_outcomes` («il detector prevede la
deriva a orizzonte fisso?»). Le due convivono e non vanno mescolate: la
calibrazione, il monitor di deriva, il cubo dei detector e la curva di equity
sono tutti costruiti sulla chiusura a orizzonte fisso, e ridefinirla
cambierebbe in silenzio il significato di ogni numero d'efficacia a schermo.

⚠️ E' una GARA, non un «ha mai toccato il target». Una posizione con quelle
caratteristiche ha anche uno stop, e si sarebbe chiusa da sola in PERDITA se
lo stop arrivava prima. Contare i soli tocchi del target produce un tasso di
successo gonfiato per costruzione — quasi tutto tocca un target vicino, prima
o poi — ed e' il modo piu' comune di fabbricare una percentuale lusinghiera
che non corrisponde a nessun guadagno.

Questo modulo e' PURO: prende un piano e delle barre, non tocca il database.
La persistenza e la maturazione stanno altrove, cosi' la regola si prova da
sola e su numeri veri.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import NamedTuple

from app.signals.trade_plan import PianoDiTrade


class Barra(NamedTuple):
    """Una seduta. `alto`/`basso` servono perche' la gara e' sul PERCORSO: una
    chiusura non dice se lo stop e' stato toccato durante la giornata."""
    data: str
    alto: float
    basso: float
    chiusura: float


@dataclass(frozen=True)
class EsitoGara:
    #: "tp1" | "stop" | "ambigua" | "scaduto"
    esito: str
    data: str
    barre: int
    #: Il guadagno in multipli di R. ⚠️ NON e' una costante per detector: i
    #: target sono tagliati a un multiplo di ATR, quindi l'R di un TP1 varia
    #: per segnale (misurato sui vettori: da 0,2 a 4,0).
    r_multiplo: float
    #: Massima escursione avversa e favorevole, in R, fino alla barra che
    #: RISOLVE. Sono gli ingressi per tarare stop e target, e valgono piu' di
    #: un binario per osservazione perche' sono continui.
    mae_r: float
    mfe_r: float
    #: Il secondo target e' stato toccato prima dello stop. Tenuto a parte
    #: dall'esito: mescolarlo renderebbe incomparabili le righe.
    tp2_raggiunto: bool


def corri_la_gara(
    piano: PianoDiTrade, barre: Sequence[Barra], orizzonte: int,
) -> EsitoGara | None:
    """L'esito del piano sulle barre SUCCESSIVE all'ingresso, o None.

    None quando non c'e' ancora un esito: nessuna barra, oppure niente e'
    stato toccato e l'orizzonte non e' ancora trascorso.

    ⚠️ Quel None e' importante quanto gli esiti. Etichettare un trade ancora
    aperto come «scaduto» vorrebbe dire scrivere un numero che il tempo puo'
    ancora smentire — lo stesso difetto che stiamo chiudendo, con il segno
    invertito.
    """
    if piano.r <= 0 or not barre or not piano.targets:
        return None

    lungo = piano.side == "long"
    tp1 = piano.targets[0].price
    tp2 = piano.targets[1].price if len(piano.targets) > 1 else None
    rr1 = piano.targets[0].rr

    # Oltre l'orizzonte non si guarda: un tocco alla trentesima seduta di un
    # detector etichettato a ventuno appartiene a un'altra domanda.
    finestra = list(barre[:orizzonte])

    peggio = migliore = piano.entry
    tp2_visto = False

    for i, b in enumerate(finestra, 1):
        if lungo:
            peggio = min(peggio, b.basso)
            migliore = max(migliore, b.alto)
            colpo_stop = b.basso <= piano.stop
            colpo_tp1 = b.alto >= tp1
            colpo_tp2 = tp2 is not None and b.alto >= tp2
        else:
            peggio = max(peggio, b.alto)
            migliore = min(migliore, b.basso)
            colpo_stop = b.alto >= piano.stop
            colpo_tp1 = b.basso <= tp1
            colpo_tp2 = tp2 is not None and b.basso <= tp2

        if colpo_tp2 and not colpo_stop:
            tp2_visto = True

        if colpo_stop or colpo_tp1:
            # ⚠️ Stop e target nella STESSA barra: il dato giornaliero non dice
            # quale sia venuto prima. Si assegna lo stop (pessimista) ma
            # l'esito resta una categoria a se', cosi' dopo si puo' misurare
            # quanto costa questa convenzione invece di darla per buona.
            if colpo_stop and colpo_tp1:
                esito, r_mult = "ambigua", -1.0
            elif colpo_stop:
                esito, r_mult = "stop", -1.0
            else:
                esito, r_mult = "tp1", rr1
            return _esito(esito, b.data, i, r_mult, piano, peggio, migliore,
                          tp2_visto and not colpo_stop)

    # Nessun tocco. Se l'orizzonte e' trascorso si valorizza alla chiusura;
    # altrimenti il trade e' ancora aperto e non si etichetta.
    if len(barre) < orizzonte:
        return None
    ultima = finestra[-1]
    segno = 1.0 if lungo else -1.0
    r_mult = (ultima.chiusura - piano.entry) * segno / piano.r
    return _esito("scaduto", ultima.data, len(finestra), r_mult, piano,
                  peggio, migliore, tp2_visto)


def _esito(
    esito: str, data: str, barre: int, r_mult: float, piano: PianoDiTrade,
    peggio: float, migliore: float, tp2: bool,
) -> EsitoGara:
    if piano.side == "long":
        mae = (piano.entry - peggio) / piano.r
        mfe = (migliore - piano.entry) / piano.r
    else:
        mae = (peggio - piano.entry) / piano.r
        mfe = (piano.entry - migliore) / piano.r
    # `peggio`/`migliore` partono dall'ingresso, quindi entrambe sono gia' >= 0:
    # un trade mai andato contro ha escursione avversa ZERO, che e' la lettura
    # giusta — «massima escursione avversa» col segno meno sarebbe una
    # contraddizione, e zero dice la cosa vera, cioe' che lo stop non e' mai
    # stato avvicinato.
    return EsitoGara(esito=esito, data=data, barre=barre, r_multiplo=r_mult,
                     mae_r=mae, mfe_r=mfe, tp2_raggiunto=tp2)
