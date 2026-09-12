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
