"""Ogni valore che il codice scrive in `stock_setups` entra nella sua colonna.

⚠️ Il difetto che questo file chiude ha fermato TUTTE le scansioni in
produzione per ~19 ore (dal 2026-09-14 19:53 UTC). FA-061 aveva aggiunto il
tono `undetermined` — 12 caratteri — in una colonna `String(8)`. Postgres
rifiuta il valore; SQLite no, perche' la lunghezza di un VARCHAR su SQLite e'
decorativa. La suite gira su SQLite, quindi era verde.

Questi test NON hanno bisogno di un database: confrontano le costanti con la
lunghezza dichiarata sul modello, e per questo girano nella corsia SQLite, cioe'
su ogni push. La riproduzione su Postgres vero — valore rifiutato prima della
migrazione, accettato dopo — sta in `test_postgres_integration.py`.

⚠️ Si confrontano le COSTANTI importate, non stringhe copiate qui: una copia
resterebbe `"undetermined"` anche se qualcuno allungasse il valore vero, e il
test sarebbe verde su una colonna di nuovo troppo corta.
"""
from __future__ import annotations

from app.models.stock_setup import (
    REASON_AGED,
    REASON_DECAYED,
    REASON_NO_DATA,
    REASON_STALE,
    STATUS_ACTIVE,
    STATUS_CONVERTED,
    STATUS_EXPIRED,
    StockSetup,
)
from app.signals.setups.base import TONE_BEAR, TONE_BULL, TONE_UNDETERMINED


def _lunghezza(colonna: str) -> int:
    lunghezza = StockSetup.__table__.c[colonna].type.length
    # Pavimento: una colonna senza lunghezza (Text) renderebbe None, e il
    # confronto sotto solleverebbe invece di dire che cosa e' cambiato.
    assert lunghezza is not None, f"stock_setups.{colonna} non dichiara una lunghezza"
    return lunghezza


def _entrano(colonna: str, valori: tuple[str, ...]) -> list[str]:
    limite = _lunghezza(colonna)
    return [f"{v!r} ({len(v)} > {limite})" for v in valori if len(v) > limite]


def test_ogni_tono_entra_in_stock_setups_tone() -> None:
    assert _entrano("tone", (TONE_BULL, TONE_BEAR, TONE_UNDETERMINED)) == []


def test_ogni_stato_entra_in_stock_setups_status() -> None:
    assert _entrano("status", (STATUS_ACTIVE, STATUS_CONVERTED, STATUS_EXPIRED)) == []


def test_ogni_ragione_di_chiusura_entra_in_closed_reason() -> None:
    assert _entrano(
        "closed_reason", (REASON_STALE, REASON_AGED, REASON_DECAYED, REASON_NO_DATA)
    ) == []


def test_il_controllo_boccia_davvero_un_valore_troppo_lungo() -> None:
    """Controllo negativo: senza, i tre test sopra sarebbero veri anche di un
    `_entrano` che rende sempre una lista vuota."""
    troppo = "x" * (_lunghezza("tone") + 1)
    assert _entrano("tone", (TONE_BULL, troppo)) == [f"{troppo!r} ({len(troppo)} > {_lunghezza('tone')})"]
