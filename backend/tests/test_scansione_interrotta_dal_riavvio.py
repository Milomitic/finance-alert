"""Una scansione uccisa da un rilascio si rilancia da sola.

FA-079 #6 (2026-09-15). Il pod e' stato ricreato 83 volte in una settimana, e un
rilascio ha ucciso la scansione #632 a meta' ricalcolo. Dopo la correzione del
recupero all'avvio (`9301f5d`) il caso e' diventato peggiore: se muore la
scansione delle 23:30, l'«ultima riuscita» e' quella delle 18:30, meno di 16 ore
prima, quindi nessun recupero — e la notte e' persa fino al giorno dopo.

Far aspettare lo spegnimento non e' la risposta: con una replica l'app
resterebbe irraggiungibile per tutta la scansione. Il recupero guarda invece,
all'avvio, se una scansione e' morta col processo precedente.
"""
from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

import app.main as main_module
from app.models import ScanRun
from app.models.scan_run import KIND_ALERTS_SCAN


def _run(db: Session, *, status: str, minuti_fa: int, messaggio: str | None = None) -> ScanRun:
    t = datetime.now(UTC) - timedelta(minutes=minuti_fa)
    r = ScanRun(kind=KIND_ALERTS_SCAN, trigger="cron", status=status, started_at=t,
                last_progress_at=t, error_message=messaggio,
                completed_at=t if status != "running" else None)
    db.add(r)
    db.commit()
    return r


@pytest.fixture
def rilanci(monkeypatch) -> list[str]:
    fatti: list[str] = []
    monkeypatch.setattr(
        "app.scheduler.jobs.scan_alerts.run_scan_alerts", lambda *a, **k: fatti.append("scan")
    )
    monkeypatch.setattr(main_module, "_RECOVERY_WAIT_SECONDS", 0.0)
    return fatti


# ─── il thread del recupero ────────────────────────────────────────────────

def test_una_scansione_ferma_viene_chiusa_e_rilanciata(db: Session, rilanci) -> None:
    morta = _run(db, status="running", minuti_fa=2)
    main_module._recover_interrupted_scans({morta.id: morta.last_progress_at})
    db.expire_all()
    riga = db.get(ScanRun, morta.id)
    assert riga.status == "failed"
    assert riga.error_message == main_module._INTERRUPTED_BY_RESTART
    assert rilanci == ["scan"]


def test_il_messaggio_di_chiusura_non_conta_come_guasto() -> None:
    """Il recupero e la serie di fallimenti (FA-079 #7) devono essere d'accordo:
    un rilascio non e' una pipeline rotta."""
    from app.core import app_metrics

    assert main_module._INTERRUPTED_BY_RESTART.startswith(app_metrics.NOT_A_PIPELINE_FAILURE)
    assert main_module._CLOSED_BY_RESTART.startswith(app_metrics.NOT_A_PIPELINE_FAILURE)


def test_una_scansione_viva_in_un_altro_processo_non_si_tocca(db: Session, rilanci) -> None:
    """L'heartbeat si e' mosso durante l'attesa: era viva altrove."""
    viva = _run(db, status="running", minuti_fa=0)
    fotografia = {viva.id: viva.last_progress_at - timedelta(seconds=30)}
    main_module._recover_interrupted_scans(fotografia)
    db.expire_all()
    assert db.get(ScanRun, viva.id).status == "running"
    assert rilanci == []


def test_una_scansione_finita_da_sola_non_si_rilancia(db: Session, rilanci) -> None:
    finita = _run(db, status="success", minuti_fa=1)
    main_module._recover_interrupted_scans({finita.id: finita.last_progress_at})
    assert rilanci == []


# ─── la decisione all'avvio ────────────────────────────────────────────────

@pytest.fixture
def avvio(monkeypatch):
    # ⚠️ Niente `delenv("PYTEST_CURRENT_TEST")` qui: pytest REIMPOSTA quella
    # variabile all'inizio della fase di esecuzione, dopo le fixture. Tolta qui,
    # `_catch_up_scan_on_boot` usciva alla prima riga e il test «non parte
    # niente» passava per la ragione sbagliata. Va tolta nel corpo del test.
    partiti: list[str] = []
    fatto = threading.Event()

    def _registra(nome):
        def _f(*a, **k):
            partiti.append(nome)
            fatto.set()
        return _f

    monkeypatch.setattr(main_module, "_recover_interrupted_scans", _registra("recupero"))
    monkeypatch.setattr("app.scheduler.jobs.scan_alerts.run_scan_alerts", _registra("scan"))
    return partiti, fatto


def test_all_avvio_una_scansione_running_avvia_il_recupero(db: Session, avvio, monkeypatch) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    partiti, fatto = avvio
    _run(db, status="success", minuti_fa=300)     # ultima riuscita FRESCA
    _run(db, status="running", minuti_fa=1)
    main_module._catch_up_scan_on_boot()
    assert fatto.wait(5)
    assert partiti == ["recupero"]


def test_all_avvio_una_scansione_chiusa_dal_riavvio_si_rilancia_subito(db: Session, avvio, monkeypatch) -> None:
    """Il pod e' rimasto giu' piu' di 5 minuti: la pulizia all'avvio l'ha gia'
    chiusa, quindi di 'running' non resta niente — ma e' morta lo stesso."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    partiti, fatto = avvio
    _run(db, status="success", minuti_fa=300)
    _run(db, status="failed", minuti_fa=20,
         messaggio="Backend riavviato durante lo scan (ultimo heartbeat ~8min fa). Cleanup automatico all'avvio.")
    main_module._catch_up_scan_on_boot()
    assert fatto.wait(5)
    assert partiti == ["scan"]


def test_all_avvio_niente_di_interrotto_e_ultima_riuscita_fresca_non_parte_niente(
    db: Session, avvio, monkeypatch
) -> None:
    """Il controllo negativo dei due sopra: il comportamento di prima resta."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    partiti, fatto = avvio
    # Pavimento: la funzione deve ARRIVARE a guardare le scansioni interrotte.
    # Senza, «non e' partito niente» sarebbe vero anche di un'uscita anticipata
    # — esattamente come la prima versione di questo test.
    consultate: list[bool] = []
    vera = main_module._running_alert_scans
    monkeypatch.setattr(
        main_module, "_running_alert_scans", lambda db2: consultate.append(True) or vera(db2)
    )
    _run(db, status="failed", minuti_fa=400, messaggio="boom")
    _run(db, status="success", minuti_fa=300)
    main_module._catch_up_scan_on_boot()
    assert consultate == [True], "la funzione e' uscita prima di guardare le scansioni interrotte"
    assert not fatto.wait(0.5)
    assert partiti == []
