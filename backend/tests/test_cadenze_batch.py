"""Le cadenze dei job batch dopo FA-079 (#3, #4, #5), verificate per COMPORTAMENTO.

⚠️ Nessuno di questi test ricopia l'orario scritto nello scheduler: una copia
cambierebbe insieme all'originale e non proverebbe niente. Si chiede invece al
trigger VERO quando scatta, su una settimana vera, e si controlla la proprieta'
per cui l'orario e' stato scelto.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

ROMA = ZoneInfo("Europe/Rome")


@pytest.fixture
def scheduler(monkeypatch):
    import apscheduler.triggers.cron as cron_module

    import app.scheduler as scheduler_module

    # ⚠️ Una macchina UTC, come il pod e la CI. La prima versione di questi test
    # era verde su Windows a Roma e rossa in CI: un trigger senza fuso prende
    # quello della macchina (vedi `test_scheduler_fuso_orario.py`).
    monkeypatch.setattr(cron_module, "get_localzone", lambda: ZoneInfo("UTC"))
    monkeypatch.setattr(scheduler_module, "_scheduler", None)
    return scheduler_module.get_scheduler()


def _scatti(job, inizio: datetime, giorni: int) -> list[datetime]:
    fine = inizio + timedelta(days=giorni)
    out: list[datetime] = []
    prec, ora = None, inizio
    while True:
        t = job.trigger.get_next_fire_time(prec, ora)
        if t is None or t >= fine:
            return out
        out.append(t)
        prec, ora = t, t + timedelta(seconds=1)


# ─── #3 FRED ────────────────────────────────────────────────────────────────

# Lunedi' 14 settembre 2026: ora legale sia in Europa sia negli USA (ET = Roma - 6h).
_SETTIMANA = datetime(2026, 9, 14, 0, 0, tzinfo=ROMA)


@pytest.mark.parametrize("ora_rilascio", [(14, 30), (13, 30)])
def test_ogni_rilascio_usa_delle_08_30_ET_ha_una_passata_fred_entro_due_ore(scheduler, ora_rilascio) -> None:
    """08:30 ET cade alle 14:30 di Roma, e alle 13:30 nelle settimane di marzo
    e ottobre/novembre in cui l'ora legale USA ed europea non coincidono. Il
    ritardo accettato col vecchio intervallo di 2 ore resta rispettato."""
    scatti = _scatti(scheduler.get_job("refresh_fred"), _SETTIMANA, 7)
    for giorno in range(5):   # lun-ven
        rilascio = (_SETTIMANA + timedelta(days=giorno)).replace(hour=ora_rilascio[0], minute=ora_rilascio[1])
        entro = [t for t in scatti if rilascio < t <= rilascio + timedelta(hours=2)]
        assert entro, f"nessuna passata FRED entro 2 ore dal rilascio delle {rilascio:%a %H:%M}"


def test_i_rendimenti_serali_e_l_fomc_hanno_una_passata_la_sera_stessa(scheduler) -> None:
    """H.15 esce verso le 16:15 ET (22:15 di Roma), l'FOMC alle 14:00 ET."""
    scatti = _scatti(scheduler.get_job("refresh_fred"), _SETTIMANA, 7)
    for giorno in range(5):
        sera = (_SETTIMANA + timedelta(days=giorno)).replace(hour=22, minute=15)
        assert [t for t in scatti if sera < t <= sera + timedelta(hours=2)], f"{sera:%a}"


def test_fred_nel_weekend_non_gira_e_in_settimana_gira_molto_meno(scheduler) -> None:
    scatti = _scatti(scheduler.get_job("refresh_fred"), _SETTIMANA, 7)
    assert all(t.weekday() < 5 for t in scatti)
    # Pavimento e tetto: senza il pavimento «meno di prima» sarebbe vero di un
    # job che non scatta mai.
    assert 5 <= len(scatti) < 84 / 2


# ─── #4 sonde veloci ────────────────────────────────────────────────────────

def test_nessuna_soglia_di_freschezza_scade_fra_due_giri_di_sonde(scheduler) -> None:
    """Una fonte diventa «stantia» dopo `expected_cadence_s × _STALE_GRACE`
    senza conferme. Se quella soglia fosse piu' corta di due intervalli delle
    sonde, un solo giro in ritardo farebbe lampeggiare la pagina Salute."""
    from app.services import source_catalog

    scatti = _scatti(scheduler.get_job("health_probes_fast"), _SETTIMANA, 1)
    assert len(scatti) >= 2
    intervallo = max((b - a) for a, b in zip(scatti, scatti[1:], strict=False)).total_seconds()

    soglie = [
        (f"{spec.source}.{spec.op}", spec.expected_cadence_s * source_catalog._STALE_GRACE)
        for spec in source_catalog.KNOWN_SOURCES
        if spec.expected_cadence_s is not None
    ]
    assert soglie, "il catalogo non dichiara nessuna cadenza: il test sarebbe vero di niente"
    corte = [(k, s) for k, s in soglie if s < 2 * intervallo]
    assert corte == [], f"soglie piu' corte di due giri di sonde ({intervallo:.0f}s): {corte}"


def test_le_sonde_veloci_girano_meno_spesso_di_prima(scheduler) -> None:
    scatti = _scatti(scheduler.get_job("health_probes_fast"), _SETTIMANA, 1)
    assert 24 <= len(scatti) < 288


# ─── #5 db_backup ───────────────────────────────────────────────────────────

def test_db_backup_c_e_su_sqlite(scheduler) -> None:
    from app.core import db as db_module

    assert db_module.engine.dialect.name == "sqlite"   # pavimento: i test girano su SQLite
    assert scheduler.get_job("db_backup") is not None


def test_db_backup_non_si_registra_su_postgres(monkeypatch) -> None:
    import app.scheduler as scheduler_module
    from app.core import db as db_module

    monkeypatch.setattr(db_module, "engine", SimpleNamespace(dialect=SimpleNamespace(name="postgresql")))
    monkeypatch.setattr(scheduler_module, "_scheduler", None)
    assert scheduler_module.get_scheduler().get_job("db_backup") is None
