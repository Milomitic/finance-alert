"""C'e' qualcuno davanti all'app? L'istante dell'ultima richiesta autenticata.

Serve a un solo scopo: fermare il lavoro che esiste SOLO per chi guarda — il
giro dell'universo per la classifica dei movers — quando non guarda nessuno.
Vive in memoria di processo, di proposito: a un riavvio riparte da «nessuno»,
che e' la risposta giusta (il primo giro dopo il ritorno dell'utente parte al
tick successivo, entro ~75 s), e una scrittura sul database a ogni richiesta
pagherebbe una domanda che interessa a un job solo.

⚠️ Non e' un controllo di sicurezza e non va usato come tale: dice solo se
qualcuno ha fatto una richiesta di recente.
"""
from __future__ import annotations

import time

_ultima: float | None = None


def segna_attivita(adesso: float | None = None) -> None:
    """Chiamata da `get_current_user` dopo un'autenticazione riuscita."""
    global _ultima
    _ultima = time.monotonic() if adesso is None else adesso


def qualcuno_connesso(finestra_s: float, adesso: float | None = None) -> bool:
    """Vero se l'ultima richiesta autenticata e' entro `finestra_s` secondi.

    `finestra_s <= 0` spegne la guardia: risponde sempre vero.
    """
    if finestra_s <= 0:
        return True
    if _ultima is None:
        return False
    ora = time.monotonic() if adesso is None else adesso
    return (ora - _ultima) <= finestra_s


def _azzera() -> None:
    """Solo per i test."""
    global _ultima
    _ultima = None
