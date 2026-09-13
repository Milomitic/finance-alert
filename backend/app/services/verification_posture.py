"""Quanto e' sorvegliata questa build, letto dall'immagine stessa.

⚠️ Mostra ARRETRATI MISURATI, non obiettivi, e la distinzione e' il punto.

Due numeri viaggiano nell'immagine perche' due cancelli li fanno rispettare:
quante funzioni nessun test esegue, e quante violazioni di accessibilita' sono
note. Entrambi i cancelli sorvegliano il DELTA — non possono crescere — proprio
perche' entrambi gli arretrati contengono voci legittime: script one-off e rami
difensivi da un lato, link di testo dentro tabelle dense dall'altro.

Portarli a schermo serve a una cosa sola: un arretrato che nessuno vede non
cala mai, e un arretrato che si vede senza la sua ragione diventa un obiettivo
da azzerare a forza. Per questo il payload porta anche il perche'.

⚠️ Mai solleva. Un file mancante significa NON SO — `None`, non zero: uno zero
qui si leggerebbe come «nessun arretrato», che e' l'opposto della verita'.
Stessa regola di `image_provenance` e di `fx_service` sulle valute.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DATI = Path(__file__).resolve().parents[1] / "data"


@dataclass(frozen=True)
class Arretrato:
    """Un conteggio, il suo totale quando esiste, e perche' non e' zero."""

    conteggio: int
    totale: int | None
    perche: str


def _leggi(nome: str) -> dict | None:
    try:
        return json.loads((DATI / nome).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        logger.warning(f"linea di base illeggibile ({nome}): {exc}")
        return None


def codice_mai_eseguito() -> Arretrato | None:
    d = _leggi("dead_code_baseline.json")
    if not d:
        return None
    return Arretrato(
        conteggio=len(d.get("morte", [])),
        totale=d.get("totale_funzioni"),
        perche=d.get("_perche", ""),
    )


def mutanti_sopravvissuti() -> Arretrato | None:
    """Righe ESEGUITE dai test la cui correttezza nessuno verifica.

    ⚠️ E' il numero piu' scomodo dei tre, e per questo il piu' utile: la
    copertura dice che una riga e' partita, questo dice se un suo errore
    verrebbe notato. Misurato su quattro moduli a proprietario unico.
    """
    d = _leggi("mutation_baseline.json")
    if not d:
        return None
    return Arretrato(
        conteggio=len(d.get("sopravvissuti", [])),
        # ⚠️ Il denominatore si SOMMA dai conteggi per modulo.
        #
        # Stava in `totale_mutanti`, chiave che non esiste piu': il cricchetto
        # e' diventato per modulo e il lettore e' rimasto indietro. `.get` ha
        # restituito None senza rumore, quindi la scheda ha mostrato «63» con
        # il denominatore a «non dichiarato» — cioe' un arretrato senza la sua
        # scala, che e' il difetto che questa scheda esiste per non avere.
        # Nessun errore, nessun test rosso: la rinomina ha spezzato un lettore
        # in un altro modulo, la stessa forma del «rinominare fa mentire i
        # commenti» registrata in CLAUDE.md.
        totale=_totale_mutanti(d),
        perche=d.get("_perche", ""),
    )


def _totale_mutanti(d: dict) -> int | None:
    """Somma dei mutanti generati, o None se il file non lo dice.

    ⚠️ None e non 0: un denominatore assente e uno pari a zero dicono cose
    opposte, e la scheda rende «non dichiarato» solo per il primo.
    """
    per_modulo = d.get("per_modulo")
    if isinstance(per_modulo, dict) and per_modulo:
        n = sum(
            c.get("mutanti", 0) for c in per_modulo.values() if isinstance(c, dict)
        )
        return n or None
    # File precedente al passaggio ai conteggi per modulo (rollout).
    vecchio = d.get("totale_mutanti")
    return vecchio if isinstance(vecchio, int) else None


def violazioni_a11y() -> Arretrato | None:
    d = _leggi("a11y_baseline.json")
    if not d:
        return None
    rotte = d.get("rotte", {})
    return Arretrato(
        conteggio=sum(sum(r.values()) for r in rotte.values() if isinstance(r, dict)),
        totale=len(rotte) or None,
        perche=d.get("_perche", ""),
    )
