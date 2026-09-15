"""«Quando si e' chiusa l'ultima scansione riuscita» — una domanda, una risposta.

⚠️ Il difetto: due punti chiedevano `ORDER BY completed_at DESC LIMIT 1`. Su
Postgres i NULL vengono PRIMI in un ordinamento decrescente, e in produzione ci
sono 18 esecuzioni `success` di maggio senza `completed_at`. Risultato misurato:
una scansione completa a ogni ricreazione del pod (83 in 7 giorni) e la finestra
di recenza dei segnali che non si allargava mai.

⚠️ Su SQLite i NULL vengono ULTIMI, quindi i test di COMPORTAMENTO qui sotto sono
veri anche della forma vecchia: servono a fissare la funzione nuova, non a
riprodurre il difetto. Due cose lo riproducono davvero:

1. il censimento del sorgente qui sotto, che fallisce sul codice vecchio anche
   su SQLite (controllo negativo eseguito);
2. il test nella corsia Postgres (`test_postgres_integration.py`), che esegue
   la forma vecchia e pretende che restituisca la riga senza data.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.models import ScanRun
from app.models.scan_run import (
    KIND_ALERTS_SCAN,
    KIND_SCORE_RECOMPUTE,
    last_successful_completed_at,
)


def _run(db, *, status="success", kind=KIND_ALERTS_SCAN, completed_at=None):
    db.add(ScanRun(trigger="cron", status=status, kind=kind, completed_at=completed_at))
    db.commit()


def _as_utc(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def test_nessuna_esecuzione_riuscita_rende_none(db) -> None:
    assert last_successful_completed_at(db) is None


def test_ignora_le_riuscite_senza_data_e_prende_la_piu_recente(db) -> None:
    ieri = datetime.now(UTC) - timedelta(days=1)
    _run(db, completed_at=None)                     # la forma delle 18 righe di maggio
    _run(db, completed_at=ieri - timedelta(days=5))
    _run(db, completed_at=ieri)
    assert _as_utc(last_successful_completed_at(db)) == ieri


def test_ignora_le_fallite_e_gli_altri_tipi(db) -> None:
    vecchia = datetime.now(UTC) - timedelta(days=9)
    _run(db, completed_at=vecchia)
    _run(db, status="failed", completed_at=datetime.now(UTC))
    _run(db, kind=KIND_SCORE_RECOMPUTE, completed_at=datetime.now(UTC))
    assert _as_utc(last_successful_completed_at(db)) == vecchia


_APP = Path(__file__).resolve().parents[1] / "app"
_TRAPPOLA = re.compile(
    r"desc\(\s*ScanRun\.completed_at\s*\)|ScanRun\.completed_at\s*\.\s*desc\(\s*\)"
)


def test_nessuno_ordina_completed_at_in_modo_decrescente() -> None:
    """Il censimento che fallisce sul codice vecchio anche su SQLite.

    ⚠️ Si guarda la SORGENTE perche' il comportamento su SQLite non distingue le
    due forme. `nulls_last()` sarebbe corretto, ma una seconda forma giusta
    accanto a quella della funzione e' l'inizio di due copie che divergono:
    chi ha bisogno della data chiama `last_successful_completed_at`.
    """
    siti = [
        f"{p.relative_to(_APP.parent)}:{n}"
        for p in sorted(_APP.rglob("*.py"))
        for n, riga in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if _TRAPPOLA.search(riga)
    ]
    assert siti == []


def test_il_censimento_riconosce_la_trappola() -> None:
    """Controllo negativo: senza, il censimento sarebbe vero anche di una regex
    che non trova niente."""
    assert _TRAPPOLA.search(".order_by(desc(ScanRun.completed_at))")
    assert _TRAPPOLA.search(".order_by(ScanRun.completed_at.desc())")
    assert not _TRAPPOLA.search("func.max(ScanRun.completed_at)")
