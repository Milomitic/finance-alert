"""La scansione delle 18:30 non ricalcola gli score, e non scrive lo storico.

FA-079 #2 (2026-09-15). Il ricalcolo della lente Qualita' costava ~6 minuti in
ENTRAMBE le scansioni feriali, mentre i fondamentali da cui dipende hanno TTL 7
giorni: le due passate davano lo stesso numero. La scansione delle 18:30 lo
salta; la rifa' quella delle 23:30, che la segue sempre.

⚠️ Il test che conta di piu' e' quello sullo storico. `score_history_service.
capture` scrive UNA volta al giorno e vince la prima: se la 18:30 saltasse il
ricalcolo ma catturasse lo storico, quel giorno resterebbe con la Qualita' della
sera prima e la cattura fresca delle 23:30 verrebbe scartata — in silenzio.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.services import scan_runner
from app.services.scan_service import ScanResult


def _chiamate(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    from app.services import score_history_service, score_service

    conta = {"recompute_all": 0, "capture": 0}

    def _recompute_all(db, **kw):
        conta["recompute_all"] += 1
        return 0, 0

    def _capture(db, **kw):
        conta["capture"] += 1
        return 0

    monkeypatch.setattr(score_service, "recompute_all", _recompute_all)
    monkeypatch.setattr(score_history_service, "capture", _capture)
    monkeypatch.setattr(
        scan_runner, "scan_universe",
        lambda db2, on_progress=None, progress_every=5, cancel_check=None: ScanResult(
            stocks_scanned=0, stocks_skipped=0, alerts_fired=0, states_updated=0
        ),
    )
    return conta


def test_senza_ricalcolo_non_ricalcola_e_non_cattura_lo_storico(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    conta = _chiamate(monkeypatch)
    run = scan_runner.run_tracked_scan(db, trigger="cron", recompute_scores=False)
    assert run.status == "success"
    assert conta == {"recompute_all": 0, "capture": 0}


def test_di_default_ricalcola_e_cattura(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Controllo negativo del test sopra: senza, «zero chiamate» sarebbe vero
    anche di un finto che non intercetta niente. E fissa che la scansione
    notturna, quella manuale e il recupero all'avvio non hanno perso nulla."""
    conta = _chiamate(monkeypatch)
    run = scan_runner.run_tracked_scan(db, trigger="cron")
    assert run.status == "success"
    assert conta == {"recompute_all": 1, "capture": 1}


def test_il_job_inoltra_il_parametro(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.scheduler.jobs import scan_alerts as job

    visto: list[bool] = []
    monkeypatch.setattr(
        job, "_run_scan_alerts_locked",
        lambda trigger, recompute_scores=True: visto.append(recompute_scores),
    )
    job.run_scan_alerts(trigger="cron", recompute_scores=False)
    job.run_scan_alerts(trigger="cron")
    assert visto == [False, True]


def test_solo_la_scansione_delle_18_30_salta_il_ricalcolo(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module, "_scheduler", None)
    s = scheduler_module.get_scheduler()
    assert s.get_job("scan_alerts_eu_close").kwargs == {"recompute_scores": False}
    # La notturna non passa niente, cioe' ricalcola.
    assert s.get_job("scan_alerts").kwargs.get("recompute_scores", True) is True
