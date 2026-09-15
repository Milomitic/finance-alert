"""Una scansione che crolla lasciando la sessione ABORTITA viene registrata con l'errore vero.

⚠️ Il difetto, com'e' andato in produzione il 2026-09-14/15. Una scrittura
rifiutata da Postgres (il tono `undetermined` in una colonna da 8 caratteri)
lascia la sessione in stato di rollback pendente. Il ramo `except` di
`run_tracked_scan` faceva `logger.exception(f"... {run.id} ...")` PRIMA di
`db.rollback()`: `run.id` era scaduto dall'ultimo commit, rileggerlo richiede
una query, e la query su una sessione abortita solleva `PendingRollbackError`.

Quindi il gestore d'errore crollava a sua volta, la riga NON veniva segnata
`failed`, e cinque minuti dopo la pulizia periodica la chiudeva con «heartbeat
fermo da ~5min». Undici scansioni fallite portavano tutte quel messaggio, e la
causa vera stava solo nei log del container.

⚠️ Il tick di avanzamento prima del crollo NON e' decorativo: e' il commit che
fa scadere gli attributi di `run`. Senza, `run.id` e' ancora in memoria, il
ramo `except` non tocca il database, e il test sarebbe verde anche col difetto
dentro.
"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ScanRun, Stock
from app.services import notifier_service, scan_runner
from app.services.scan_service import ScanCancelled, ScanResult


def _vuoto() -> ScanResult:
    return ScanResult(stocks_scanned=0, stocks_skipped=0, alerts_fired=0, states_updated=0)


def _avvelena(db2: Session) -> None:
    """Una scrittura rifiutata dal database, lasciata senza rollback — la forma
    del `StringDataRightTruncation` di produzione, riprodotta con un vincolo
    che SQLite fa rispettare."""
    db2.add(Stock(ticker="DUP", exchange="NYSE", name="Doppione"))
    db2.flush()


def _ultima_riga() -> ScanRun:
    from app.core.db import SessionLocal

    with SessionLocal() as check:
        return check.query(ScanRun).order_by(ScanRun.id.desc()).first()


@pytest.fixture
def doppione(db: Session) -> None:
    db.add(Stock(ticker="DUP", exchange="NYSE", name="Originale"))
    db.commit()


def test_il_crollo_con_sessione_abortita_esce_con_l_errore_vero(
    db: Session, doppione, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _scan(db2, on_progress=None, progress_every=5, cancel_check=None):
        on_progress(0, 1, _vuoto(), None)   # commit: gli attributi di `run` scadono
        _avvelena(db2)

    monkeypatch.setattr(scan_runner, "scan_universe", _scan)
    notifiche: list[tuple[int, str]] = []
    monkeypatch.setattr(
        notifier_service, "notify_scan_failed",
        lambda run_id, msg: notifiche.append((run_id, msg)),
    )

    # L'errore che esce e' quello del database, non il PendingRollbackError
    # del gestore che crolla.
    with pytest.raises(IntegrityError):
        scan_runner.run_tracked_scan(db, trigger="cron")

    riga = _ultima_riga()
    assert riga.status == "failed", "la riga e' rimasta 'running': la chiudera' la pulizia, senza causa"
    assert "UNIQUE" in (riga.error_message or "").upper()
    assert "heartbeat" not in (riga.error_message or "")
    # E la notifica parte con l'id giusto e lo stesso errore.
    assert notifiche and notifiche[0][0] == riga.id
    assert "UNIQUE" in notifiche[0][1].upper()


def test_l_annullamento_con_sessione_abortita_chiude_comunque_la_riga(
    db: Session, doppione, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Il ramo `ScanCancelled` aveva la stessa forma: `run.id` letto prima del
    rollback."""
    def _scan(db2, on_progress=None, progress_every=5, cancel_check=None):
        on_progress(0, 1, _vuoto(), None)
        try:
            _avvelena(db2)
        except IntegrityError:
            # Lo stop arriva mentre la sessione e' ancora da ripristinare.
            raise ScanCancelled("Cancellato dall'utente") from None

    monkeypatch.setattr(scan_runner, "scan_universe", _scan)
    monkeypatch.setattr(notifier_service, "notify_scan_failed", lambda run_id, msg: None)

    scan_runner.run_tracked_scan(db, trigger="manual")

    riga = _ultima_riga()
    assert riga.status == "failed"
    assert riga.error_message == "Cancellato dall'utente"
