"""APScheduler setup and lifecycle bound to FastAPI."""
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from app.core import db as db_module
from app.core.config import settings
from app.scheduler.jobs.cleanup_orphan_scans_job import run_cleanup_orphan_scans
from app.scheduler.jobs.db_backup import run_db_backup
from app.scheduler.jobs.dedupe_stocks_job import run_dedupe_stocks
from app.scheduler.jobs.health_probes_job import (
    run_health_probes_fast,
    run_health_probes_slow,
)
from app.scheduler.jobs.kpi_rollup import run_kpi_rollup
from app.scheduler.jobs.live_movers_sweep import run_live_universe_sweep
from app.scheduler.jobs.refresh_catalog import run_refresh_all
from app.scheduler.jobs.refresh_fred import run_refresh_fred
from app.scheduler.jobs.refresh_imminent_earnings import run_refresh_imminent_earnings
from app.scheduler.jobs.refresh_institutionals import run_refresh_institutionals
from app.scheduler.jobs.refresh_premarket import run_refresh_premarket
from app.scheduler.jobs.refresh_sec_13f import run_refresh_sec_13f
from app.scheduler.jobs.repair_ohlcv_gaps import run_repair_ohlcv_gaps
from app.scheduler.jobs.retention import run_retention
from app.scheduler.jobs.scan_alerts import run_scan_alerts
from app.scheduler.jobs.send_digest import run_send_digest
from app.services.scheduler_metrics import install_listener as _install_scheduler_listener

_scheduler: BackgroundScheduler | None = None

#: Il fuso di OGNI orario scritto in questo file.
_TZ = "Europe/Rome"


def _cron(**campi) -> CronTrigger:
    """Un `CronTrigger` nel fuso di Roma, dichiarato esplicitamente.

    ⚠️ `BackgroundScheduler(timezone=...)` NON basta, ed e' stato creduto per
    mesi. Quel fuso vale solo per i job aggiunti con la stringa `"cron"`; un
    `CronTrigger` costruito a mano prende `tzlocal.get_localzone()`, cioe' il
    fuso della MACCHINA. Sul desktop di sviluppo era Roma e tutto tornava; nel
    pod e' `Etc/UTC`, quindi dal passaggio al cloud ogni job girava due ore dopo
    l'orario scritto qui accanto — le scansioni alle 18:30 e 23:30 UTC (#617,
    #622), il digest alle 10:00 di Roma. Scoperto il 2026-09-15 perche' un test
    sulle finestre di FRED era verde su Windows e rosso in CI.
    `tests/test_scheduler_fuso_orario.py` lo fissa simulando una macchina UTC.
    """
    return CronTrigger(timezone=_TZ, **campi)


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone=_TZ)
        _install_scheduler_listener(_scheduler)
        _scheduler.add_job(
            run_refresh_all,
            trigger=_cron(day_of_week="sat", hour=3, minute=0),
            id="refresh_catalog",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        _scheduler.add_job(
            run_dedupe_stocks,
            trigger=_cron(day_of_week="sat", hour=3, minute=30),
            id="dedupe_stocks",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        # Nightly DB snapshot (audit B4-1) — 03:30, after the 23:30 scan and
        # the weekend 03:00 catalog refresh have finished. VACUUM INTO takes a
        # consistent read-snapshot under WAL (writers not blocked); the job
        # itself skips with a WARNING if a scan is running.
        #
        # ⚠️ Solo su SQLite (FA-079 #5). Su Postgres `run_db_backup` esce subito
        # — i backup sono il WAL archiviato del cluster CNPG — quindi registrarlo
        # significava una riga «ok» ogni notte sulla pagina Salute per un job che
        # non fa niente. Letto da `db_module.engine` a costruzione, cosi' un test
        # puo' sostituire il motore.
        if db_module.engine.dialect.name == "sqlite":
            _scheduler.add_job(
                run_db_backup,
                trigger=_cron(day_of_week="*", hour=3, minute=30),
                id="db_backup",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
        # Weekly retention prune of scan_runs (audit B4-11) — Sunday 04:00,
        # after the nightly 03:30 backup window and far from the scan hours.
        # Deletes rows older than 180 days keeping the newest 500 regardless;
        # skips with a WARNING if a scan is running.
        _scheduler.add_job(
            run_retention,
            trigger=_cron(day_of_week="sun", hour=4, minute=0),
            id="retention",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        # Solo lun-ven (FA-079, 2026-09-15). Sabato e domenica non arriva
        # nessuna barra nuova: la scansione di venerdi' 23:30 ha gia' visto la
        # chiusura USA, e le due del weekend rifacevano ~12 minuti di lavoro
        # identico ciascuna. ⚠️ Accoppiato a `FinanceAlertNotScanning` in
        # `infra/observability/app-alert-rules.yaml`, che ora tace nel weekend:
        # senza quella guardia la soglia di 26 h scatterebbe ogni sabato sera.
        # `tests/test_scansione_feriale_e_allarme.py` tiene le due cose insieme.
        _scheduler.add_job(
            run_scan_alerts,
            trigger=_cron(
                day_of_week="mon-fri", hour=settings.scan_hour, minute=settings.scan_minute
            ),
            id="scan_alerts",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        # Extra weekday evening tick after the EU close so a pattern that
        # completed at today's close is detected this evening (while the app
        # is open) instead of waiting for the 23:30 tick. Cheap: scan_universe
        # uses STORED OHLCV and the fetch step is smart-incremental.
        #
        # ⚠️ Senza ricalcolo degli score (FA-079 #2): la lente Qualita' dipende
        # dai fondamentali (TTL 7 giorni) e la rifa' la scansione delle 23:30,
        # che segue sempre questa. Risparmia ~6 minuti per feriale. La lente
        # Tecnico si calcola comunque, dentro la valutazione dei segnali.
        _scheduler.add_job(
            run_scan_alerts,
            trigger=_cron(
                day_of_week="mon-fri",
                hour=settings.scan_hour_2, minute=settings.scan_minute_2,
            ),
            kwargs={"recompute_scores": False},
            id="scan_alerts_eu_close",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        # Universe-wide live top-movers sweep — one rotating chunk per tick so
        # the dashboard 1G board can surface genuine intraday movers from the
        # whole universe (not just the EOD candidate pool). Self-gates to
        # open-market tickers, so off-hours ticks are no-ops. 0 disables.
        if settings.live_movers_sweep_seconds > 0:
            _scheduler.add_job(
                run_live_universe_sweep,
                trigger=IntervalTrigger(seconds=settings.live_movers_sweep_seconds),
                id="live_movers_sweep",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
        # OHLCV gap self-repair — every 6h at :20 (00:20 lands ~50min after the
        # nightly scan, so a batch the scan dropped is topped up the same
        # night). Cheap no-op when nothing is behind. Exists because the scan
        # makes exactly ONE fetch attempt per stock per tick and never
        # revisits it: before this job, one transient upstream failure left a
        # PERMANENT hole in the charts — ~100 symbols including AMZN/MSFT lost
        # a week of bars in July 2026 without a single failed scan.
        # Solo lun-sab (2026-09-24): il giro delle 00:20 di sabato ripara ancora
        # la scansione di venerdi' notte; domenica non arriva nessuna barra.
        _scheduler.add_job(
            run_repair_ohlcv_gaps,
            trigger=_cron(day_of_week="mon-sat", hour="*/6", minute=20),
            id="repair_ohlcv_gaps",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        _scheduler.add_job(
            run_send_digest,
            trigger=_cron(
                day_of_week="*", hour=settings.digest_hour, minute=settings.digest_minute
            ),
            id="send_digest",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        # 00:45, DOPO la scansione delle 23:30 (2026-09-24). Alle 23:00 il
        # riepilogo fotografava lo stato di mezz'ora PRIMA della scansione piu'
        # importante del giorno, cioe' sempre un giorno indietro.
        _scheduler.add_job(
            run_kpi_rollup,
            trigger=_cron(day_of_week="*", hour=0, minute=45),
            id="kpi_rollup",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        _scheduler.add_job(
            run_refresh_institutionals,
            trigger=_cron(day_of_week="sat", hour=4, minute=0),
            id="refresh_institutionals",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            # Il PC è tipicamente spento/sospeso alle 04:00 di sabato: se il
            # processo si risveglia entro 12h dall'orario mancato, il job
            # parte comunque invece di slittare di una settimana intera.
            # (Il boot a macchina SPENTA è coperto dal catch-up in main.py.)
            misfire_grace_time=60 * 60 * 12,
        )
        _scheduler.add_job(
            run_refresh_premarket,
            # Every 5 min; the job self-gates to the US pre-market
            # window (~03:55-09:35 ET) and no-ops cheaply otherwise.
            trigger=_cron(day_of_week="mon-fri", minute="*/5"),
            id="refresh_premarket",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        _scheduler.add_job(
            run_refresh_sec_13f,
            trigger=_cron(day_of_week="sat", hour=4, minute=30),
            id="refresh_sec_13f",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            # Stessa tolleranza misfire del refresh Dataroma qui sopra.
            misfire_grace_time=60 * 60 * 12,
        )
        # FRED macro refresh — 5 passate nei feriali, agganciate ai rilasci
        # (FA-079 #3, 2026-09-15; prima ogni 2 ore, tutti i giorni: 84 passate
        # a settimana contro 25). Orari di Roma:
        #   07:15  serie giornaliere pubblicate nella sera USA e tassi BCE/BoE/BoJ
        #   15:15  / 16:15 / 17:15  i dati USA delle 08:30 ET (CPI, PPI, NFP,
        #          disoccupazione, PIL, vendite al dettaglio), che cadono alle
        #          14:30 di Roma — 13:30 nelle settimane in cui l'ora legale USA
        #          ed europea non coincidono — e l'HICP flash dell'Eurozona
        #   23:15  rendimenti H.15 (~16:15 ET) e decisioni FOMC (14:00 ET)
        # Ogni rilascio USA ha una passata entro 2 ore, il ritardo gia' accettato
        # col vecchio intervallo. Nel weekend FRED non pubblica niente di nostro.
        # La salute della fonte non ne risente: la sonda FRED gira nel gruppo
        # veloce e la conferma fra una passata e l'altra.
        # `tests/test_cadenze_batch.py` verifica le finestre su una settimana vera.
        _scheduler.add_job(
            run_refresh_fred,
            trigger=_cron(day_of_week="mon-fri", hour="7,15,16,17,23", minute=15),
            id="refresh_fred",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        # Imminent-earnings smart refresh — every hour at :45. Scans the
        # L1 cache for tickers with an earnings event in ±1 day, then
        # force-refreshes only those. Captures actuals within ~1h of
        # release; the Finnhub fallback inside `_fetch_fresh` typically
        # cuts the lag from 1-3h (yfinance scrape) to ~30 min.
        # Solo lun-ven (2026-09-24): nel fine settimana non esce nessuna
        # trimestrale, e i 48 giri di sabato e domenica non trovavano niente.
        _scheduler.add_job(
            run_refresh_imminent_earnings,
            trigger=_cron(day_of_week="mon-fri", minute=45),
            id="refresh_imminent_earnings",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        # Cleanup orfani ScanRun — ogni 5 minuti (era ogni minuto fino al
        # 2026-09-24: la pulizia chiude una riga il cui heartbeat e' fermo da
        # ~5 minuti, quindi un giro al minuto non la vedeva prima). Necessario perché
        # _cleanup_orphan_scans in main.py gira solo al boot; se uvicorn
        # resta su ma un worker scan crasha, la riga resta 'running'
        # all'infinito (la UI mostra una progress bar fantasma).
        _scheduler.add_job(
            run_cleanup_orphan_scans,
            trigger=_cron(minute="*/5"),
            id="cleanup_orphan_scans",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        # Health probes — keep platform-health UI populated even when no
        # user traffic is exercising a given source. Fast set every 15 min
        # (light calls; was 5 until FA-079 #4 — ~1.440 external calls a day
        # down to ~480), slow set every 30 min (heavier or rate-limited
        # like Marketaux 100/day). First run scheduled 15s after boot so
        # the UI exits "Idle" immediately instead of waiting up to 15 min.
        # Safe for staleness: the tightest catalog threshold is FRED's
        # 2h x 1.5 = 3h, and `tests/test_cadenze_batch.py` pins that every
        # threshold outlasts at least two probe intervals.
        now = datetime.now()
        _scheduler.add_job(
            run_health_probes_fast,
            trigger=_cron(minute="*/15"),
            id="health_probes_fast",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=now + timedelta(seconds=15),
        )
        _scheduler.add_job(
            run_health_probes_slow,
            trigger=_cron(minute="*/30"),
            id="health_probes_slow",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=now + timedelta(seconds=45),
        )
    return _scheduler


def start_scheduler() -> None:
    s = get_scheduler()
    if not s.running:
        s.start()
        logger.info(
            "Scheduler started with jobs: " + ", ".join(j.id for j in s.get_jobs())
        )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
