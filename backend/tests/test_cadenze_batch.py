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


# ─── 2026-09-24: kpi_rollup dopo la scansione, weekend spenti, pulizia a 5' ─


def test_il_riepilogo_kpi_viene_DOPO_la_scansione_notturna(scheduler) -> None:
    """Il riepilogo deve vedere la scansione delle 23:30 del giorno stesso:
    il suo primo scatto dopo ogni scansione feriale cade prima della scansione
    successiva, e almeno 45 minuti dopo (una scansione dura ~12 minuti piu' le
    maturazioni)."""
    scan = _scatti(scheduler.get_job("scan_alerts"), _SETTIMANA, 7)
    rollup = _scatti(scheduler.get_job("kpi_rollup"), _SETTIMANA, 8)
    assert len(scan) == 5
    for s in scan:
        dopo = [r for r in rollup if r > s]
        assert dopo, f"nessun riepilogo dopo la scansione {s:%a %H:%M}"
        assert timedelta(minutes=45) <= dopo[0] - s <= timedelta(hours=3), f"{s:%a}"


def test_utili_imminenti_solo_nei_feriali_e_ogni_ora(scheduler) -> None:
    scatti = _scatti(scheduler.get_job("refresh_imminent_earnings"), _SETTIMANA, 7)
    assert all(t.weekday() < 5 for t in scatti)
    assert len(scatti) == 5 * 24


def test_riparazione_buchi_salta_solo_la_domenica(scheduler) -> None:
    """Il giro di sabato 00:20 ripara ancora la scansione di venerdi' notte."""
    scatti = _scatti(scheduler.get_job("repair_ohlcv_gaps"), _SETTIMANA, 7)
    assert all(t.weekday() != 6 for t in scatti)
    assert any(t.weekday() == 5 and t.hour == 0 for t in scatti)
    assert len(scatti) == 6 * 4


def test_la_pulizia_degli_orfani_gira_ogni_cinque_minuti(scheduler) -> None:
    """Non piu' spesso della soglia che applica (5 minuti di heartbeat fermo):
    un giro al minuto non chiudeva una riga prima. Ma nemmeno piu' di rado,
    o una barra fantasma resterebbe a schermo oltre i dieci minuti."""
    from app.scheduler.jobs.cleanup_orphan_scans_job import _STALE_AFTER_MINUTES

    scatti = _scatti(scheduler.get_job("cleanup_orphan_scans"), _SETTIMANA, 1)
    passo = min(b - a for a, b in zip(scatti, scatti[1:], strict=False))
    assert passo == timedelta(minutes=_STALE_AFTER_MINUTES)


def test_l_addestramento_dei_modelli_in_ombra_e_la_domenica_mattina(scheduler) -> None:
    """Domenica, dopo la retention delle 04:00 e lontano da ogni scansione."""
    scatti = _scatti(scheduler.get_job("addestra_modelli_ombra"), _SETTIMANA, 14)
    assert len(scatti) == 2
    assert all(t.weekday() == 6 and t.hour == 5 for t in scatti)
    retention = _scatti(scheduler.get_job("retention"), _SETTIMANA, 7)
    assert all(r < s for r, s in zip(retention, scatti, strict=False))


def test_l_archivio_opzioni_gira_DENTRO_la_seduta_di_new_york_tutto_l_anno(scheduler) -> None:
    """⚠️ Fino al 2026-09-24 questo test pretendeva il contrario: partenza DOPO
    la chiusura USA. Fuori seduta Yahoo azzera bid e ask e la volatilita'
    implicita diventa un residuo senza senso (0,00001, 0,0156 — misurato nel
    pod), quindi il job archiviava numeri falsi o, con la guardia, niente.

    Si controlla un anno intero e non una settimana perche' Roma e New York
    cambiano ora in giorni diversi: a fine marzo e a inizio novembre lo scarto
    scende da 6 a 5 ore, e un orario scelto guardando settembre finirebbe fuori
    seduta proprio in quelle settimane. Partenza e fine del tetto devono stare
    fra le 9:30 e le 16:00 di New York, ogni volta."""
    from app.services.archivio_non_prezzo_service import archivia_opzioni

    ny = ZoneInfo("America/New_York")
    tetto = timedelta(seconds=archivia_opzioni.__kwdefaults__["tetto_s"])
    scatti = _scatti(scheduler.get_job("archivia_opzioni"), datetime(2026, 1, 1, tzinfo=ROMA), 366)
    assert len(scatti) > 250                     # tutti i feriali, non una manciata
    assert all(t.astimezone(ny).weekday() < 5 for t in scatti)
    for t in scatti:
        inizio, fine = t.astimezone(ny), (t + tetto).astimezone(ny)
        apertura = inizio.replace(hour=9, minute=30, second=0, microsecond=0)
        chiusura = inizio.replace(hour=16, minute=0, second=0, microsecond=0)
        assert apertura <= inizio and fine <= chiusura, f"{t.isoformat()} -> NY {inizio:%H:%M}-{fine:%H:%M}"


def test_l_archivio_opzioni_non_si_sovrappone_alle_scansioni(scheduler) -> None:
    """Rete e CPU dello stesso nodo: il giro delle catene non parte mentre una
    scansione e' in corso (il job lo salta), quindi l'orario non deve cadere
    nella finestra di nessuna delle due."""
    from app.services.archivio_non_prezzo_service import archivia_opzioni

    tetto = timedelta(seconds=archivia_opzioni.__kwdefaults__["tetto_s"])
    opzioni = _scatti(scheduler.get_job("archivia_opzioni"), _SETTIMANA, 7)
    scansioni = (_scatti(scheduler.get_job("scan_alerts"), _SETTIMANA, 7)
                 + _scatti(scheduler.get_job("scan_alerts_eu_close"), _SETTIMANA, 7))
    assert len(opzioni) == 5 and scansioni
    for o in opzioni:
        for s in scansioni:
            # una scansione dura ~10-20 minuti: 30 di margine da entrambe le parti
            assert o + tetto <= s - timedelta(minutes=5) or o >= s + timedelta(minutes=30), (o, s)


def test_l_archivio_fondamentali_segue_la_scansione_che_rinnova_la_cache(scheduler) -> None:
    scan = _scatti(scheduler.get_job("scan_alerts"), _SETTIMANA, 7)
    arch = _scatti(scheduler.get_job("archivia_fondamentali"), _SETTIMANA, 8)
    for s in scan:
        dopo = [a for a in arch if a > s]
        assert dopo and dopo[0] - s <= timedelta(hours=2)


def test_ogni_job_ha_un_nome_leggibile_nella_scheda_salute(scheduler) -> None:
    """Il commento in SchedulerCard lo chiede da luglio, e un job senza
    etichetta si legge in snake_case: lo si pretende qui, dove i job nascono."""
    from pathlib import Path

    sorgente = (Path(__file__).resolve().parents[2]
                / "frontend/src/components/health/SchedulerCard.tsx").read_text(encoding="utf-8")
    mancanti = [j.id for j in scheduler.get_jobs() if f"  {j.id}:" not in sorgente]
    assert not mancanti, f"job senza etichetta in SchedulerCard: {mancanti}"
