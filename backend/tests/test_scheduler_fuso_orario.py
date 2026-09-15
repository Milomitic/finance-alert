"""Ogni orario dello scheduler e' nel fuso di Roma, anche su una macchina UTC.

⚠️ Il difetto (2026-09-15): `BackgroundScheduler(timezone="Europe/Rome")` vale
solo per i job aggiunti con la stringa `"cron"`. Un `CronTrigger` costruito a
mano prende il fuso della MACCHINA (`tzlocal.get_localzone()`): Roma sul desktop
di sviluppo, `Etc/UTC` nel pod. Da quando l'app e' sul cloud ogni job girava due
ore dopo l'orario scritto.

⚠️ Per questo il test SIMULA una macchina UTC. Su Windows a Roma un test che si
limitasse a leggere il fuso del trigger sarebbe verde anche col difetto dentro —
che e' esattamente come il difetto e' sopravvissuto: verde in locale, rosso solo
dove gira davvero.
"""
from __future__ import annotations

from zoneinfo import ZoneInfo

import pytest
from apscheduler.triggers.cron import CronTrigger


@pytest.fixture
def scheduler_su_macchina_utc(monkeypatch):
    import apscheduler.triggers.cron as cron_module

    import app.scheduler as scheduler_module

    monkeypatch.setattr(cron_module, "get_localzone", lambda: ZoneInfo("UTC"))
    monkeypatch.setattr(scheduler_module, "_scheduler", None)
    return scheduler_module.get_scheduler()


def test_ogni_job_cron_e_nel_fuso_di_roma_anche_su_una_macchina_utc(scheduler_su_macchina_utc) -> None:
    cron = [j for j in scheduler_su_macchina_utc.get_jobs() if isinstance(j.trigger, CronTrigger)]
    # Pavimento: senza job cron «tutti nel fuso giusto» sarebbe vero di niente.
    assert len(cron) >= 15
    sbagliati = {j.id: str(j.trigger.timezone) for j in cron if str(j.trigger.timezone) != "Europe/Rome"}
    assert sbagliati == {}


def test_la_simulazione_della_macchina_utc_funziona(monkeypatch) -> None:
    """Controllo negativo: un CronTrigger senza fuso, costruito sotto la stessa
    simulazione, DEVE uscire in UTC. Altrimenti il test sopra non potrebbe mai
    fallire, e sarebbe verde per la stessa ragione per cui il difetto lo era."""
    import apscheduler.triggers.cron as cron_module

    monkeypatch.setattr(cron_module, "get_localzone", lambda: ZoneInfo("UTC"))
    assert str(CronTrigger(hour=23, minute=30).timezone) == "UTC"
