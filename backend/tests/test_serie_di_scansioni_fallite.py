"""Una SERIE di scansioni fallite si vede subito, non dopo 26 ore.

FA-079 #7 (2026-09-15). Il 14-15 settembre undici scansioni sono fallite di fila
e nessun allarme e' scattato: `FinanceAlertNotScanning` guarda da quanto tempo
c'e' stata l'ultima RIUSCITA, e aveva bisogno di 26 ore. La metrica
`finance_alert_run_failure_streak` conta i fallimenti dall'ultima riuscita, e
`FinanceAlertScansFailing` scatta a due.

⚠️ Le undici di quel giorno sono state chiuse dalla PULIZIA periodica, non dal
runner. Per questo c'e' un test sulla pulizia: una metrica aggiornata solo nel
ramo d'errore del runner avrebbe letto zero per tutto l'incidente.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.core import app_metrics
from app.models import ScanRun
from app.models.scan_run import KIND_ALERTS_SCAN, KIND_SCORE_RECOMPUTE

_T0 = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)


def _run(db: Session, minuti: int, status: str, messaggio: str | None = None,
         kind: str = KIND_ALERTS_SCAN) -> None:
    db.add(ScanRun(
        kind=kind, trigger="cron", status=status, error_message=messaggio,
        started_at=_T0 + timedelta(minutes=minuti),
        completed_at=_T0 + timedelta(minutes=minuti + 10),
        last_progress_at=_T0 + timedelta(minutes=minuti + 10),
    ))
    db.commit()


def _gauge() -> float:
    return app_metrics.RUN_FAILURE_STREAK.labels(kind=KIND_ALERTS_SCAN)._value.get()


@pytest.fixture(autouse=True)
def _gauge_a_meno_uno():
    # Il gauge e' globale al processo: parte da un valore che nessun conto
    # produce, cosi' un test che non lo aggiorna non passa per caso.
    app_metrics.RUN_FAILURE_STREAK.labels(kind=KIND_ALERTS_SCAN).set(-1)


def test_conta_i_fallimenti_dall_ultima_riuscita(db: Session) -> None:
    _run(db, 0, "failed", "vecchio, prima della riuscita")
    _run(db, 10, "success")
    _run(db, 20, "failed", "StringDataRightTruncation")
    _run(db, 30, "failed", "Scan terminato dal cleanup periodico (heartbeat fermo da ~5min).")
    assert app_metrics.failure_streak(db) == 2


def test_annullamenti_e_riavvii_non_sono_un_guasto(db: Session) -> None:
    _run(db, 10, "success")
    _run(db, 20, "failed", "boom")
    _run(db, 30, "failed", "Cancellato dall'utente")
    _run(db, 40, "failed", "Backend riavviato durante lo scan (ultimo heartbeat ~6min fa).")
    _run(db, 50, "failed", "Interrotta da un riavvio del backend; rilanciata automaticamente.")
    assert app_metrics.failure_streak(db) == 1


def test_zero_se_l_ultima_e_riuscita_o_se_non_c_e_niente(db: Session) -> None:
    assert app_metrics.failure_streak(db) == 0
    _run(db, 10, "failed", "boom")
    _run(db, 20, "success")
    assert app_metrics.failure_streak(db) == 0


def test_gli_altri_tipi_e_le_esecuzioni_in_corso_non_contano(db: Session) -> None:
    _run(db, 10, "success")
    _run(db, 20, "failed", "boom", kind=KIND_SCORE_RECOMPUTE)
    _run(db, 30, "running")
    assert app_metrics.failure_streak(db) == 0


def test_la_pulizia_periodica_aggiorna_la_metrica(db: Session) -> None:
    """Il caso dell'incidente: la scansione muore, la chiude la pulizia."""
    from app.scheduler.jobs.cleanup_orphan_scans_job import run_cleanup_orphan_scans

    _run(db, 0, "success")
    _run(db, 10, "failed", "StringDataRightTruncation")
    vecchio = datetime.now(UTC) - timedelta(minutes=30)
    db.add(ScanRun(kind=KIND_ALERTS_SCAN, trigger="cron", status="running",
                   started_at=vecchio, last_progress_at=vecchio))
    db.commit()

    assert run_cleanup_orphan_scans() == 1
    assert _gauge() == 2


def test_il_ramo_d_errore_del_runner_aggiorna_la_metrica(db: Session, monkeypatch) -> None:
    from app.services import notifier_service, scan_runner

    def _crolla(db2, on_progress=None, progress_every=5, cancel_check=None):
        raise RuntimeError("pipeline rotta")

    monkeypatch.setattr(scan_runner, "scan_universe", _crolla)
    monkeypatch.setattr(notifier_service, "notify_scan_failed", lambda run_id, msg: None)
    with pytest.raises(RuntimeError):
        scan_runner.run_tracked_scan(db, trigger="cron")
    assert _gauge() == 1


def test_una_riuscita_azzera_la_metrica(db: Session, monkeypatch) -> None:
    from app.services import scan_runner, score_service
    from app.services.scan_service import ScanResult

    _run(db, 0, "failed", "boom")
    _run(db, 10, "failed", "boom")
    monkeypatch.setattr(
        scan_runner, "scan_universe",
        lambda db2, on_progress=None, progress_every=5, cancel_check=None: ScanResult(
            stocks_scanned=0, stocks_skipped=0, alerts_fired=0, states_updated=0),
    )
    monkeypatch.setattr(score_service, "recompute_all", lambda db2, **kw: (0, 0))
    run = scan_runner.run_tracked_scan(db, trigger="cron")
    assert run.status == "success"
    assert _gauge() == 0


def test_la_regola_scatta_a_due_fallimenti() -> None:
    regole = (Path(__file__).resolve().parents[2] / "infra" / "observability"
              / "app-alert-rules.yaml").read_text(encoding="utf-8")
    assert "- alert: FinanceAlertScansFailing" in regole
    assert 'finance_alert_run_failure_streak{kind="alerts_scan"} >= 2' in regole
