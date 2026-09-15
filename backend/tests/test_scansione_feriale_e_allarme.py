"""La scansione salta il weekend, e l'allarme sulle scansioni ferme lo sa.

FA-079 (2026-09-15): la scansione delle 23:30 gira solo lun-ven, perche' nel
weekend non arriva nessuna barra nuova. Le due cose sono ACCOPPIATE e vanno
cambiate insieme:

- scansione feriale SENZA la guardia nella regola → `FinanceAlertNotScanning`
  (26 h) scatta ogni sabato sera, e un allarme che suona sempre si impara a
  ignorarlo;
- guardia SENZA scansione feriale → l'allarme tace tre giorni su sette per
  niente, e un guasto del venerdi' si vedrebbe lunedi' sera.

Si guarda la sorgente della regola perche' la regola non gira in pytest: la
valutazione vera dei confini e' stata fatta su Prometheus, a istanti scelti.
"""
from __future__ import annotations

import re
from pathlib import Path

REGOLE = Path(__file__).resolve().parents[2] / "infra" / "observability" / "app-alert-rules.yaml"


def _giorni_della_scansione_notturna() -> str:
    import app.scheduler as scheduler_module

    scheduler_module._scheduler = None
    try:
        job = scheduler_module.get_scheduler().get_job("scan_alerts")
        assert job is not None, "il job scan_alerts non e' registrato"
        campi = {f.name: str(f) for f in job.trigger.fields}
        return campi["day_of_week"]
    finally:
        scheduler_module._scheduler = None


def _regola_not_scanning() -> str:
    testo = REGOLE.read_text(encoding="utf-8")
    m = re.search(r"- alert: FinanceAlertNotScanning\n(.*?)\n\s*for:", testo, re.S)
    assert m, "FinanceAlertNotScanning non trovata nel file delle regole"
    return m.group(1)


def test_la_scansione_notturna_gira_solo_nei_giorni_feriali() -> None:
    assert _giorni_della_scansione_notturna() == "mon-fri"


def test_l_allarme_tace_da_sabato_a_lunedi_sera() -> None:
    espr = _regola_not_scanning()
    # La soglia non si e' allargata: nei feriali un giorno perso si vede
    # la mattina dopo, come prima.
    assert "> 26 * 3600" in espr
    for pezzo in ("day_of_week() == 6", "day_of_week() == 0",
                  "day_of_week() == 1 and hour() < 20", "unless on()"):
        assert pezzo in espr, f"manca {pezzo!r} nella guardia del weekend"


def test_il_controllo_della_regola_non_e_vero_di_niente() -> None:
    """Controllo negativo: la regex deve catturare l'espressione e non una
    stringa vuota, altrimenti il test sopra non potrebbe mai fallire per il
    motivo giusto."""
    assert "finance_alert_last_successful_run_timestamp_seconds" in _regola_not_scanning()
