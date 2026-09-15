"""Boot catch-up for the weekly institutional refresh crons (lane S1).

The sat 04:00/04:30 crons never fire on a desktop that's off on Saturday
mornings — the same local-first failure the scan boot catch-up already
solves. These tests cover:

- `institutional_service.filings_refresh_is_stale`: the staleness predicate
  (no filings / old MAX(created_at) → stale; recent → fresh);
- `app.main._catch_up_institutionals_on_boot`: kicks the catch-up thread
  when stale, skips when fresh, and never runs under PYTEST_CURRENT_TEST;
- `app.main._run_institutionals_catchup`: runs BOTH jobs sequentially and
  one job failing doesn't block the other;
- misfire_grace_time on the two cron registrations (laptop asleep at 04:00
  but awake at 09:00 must still run them).
"""
import threading
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

import app.main as main_module
from app.models import Institutional, InstitutionalFiling
from app.services import institutional_service


def _seed_filing(db: Session, *, created_at: datetime, slug: str = "fund") -> None:
    inst = Institutional(slug=slug, name=slug.upper(), type="superinvestor", source="dataroma")
    db.add(inst)
    db.flush()
    filing = InstitutionalFiling(
        institutional_id=inst.id,
        period_end_date=date.today() - timedelta(days=40),
        # Naive UTC on purpose: SQLite's server_default=now() stores naive
        # datetimes, and the predicate must normalize them.
        created_at=created_at,
    )
    db.add(filing)
    db.commit()


# ---------------------------------------------------------------------------
# Staleness predicate
# ---------------------------------------------------------------------------

def test_stale_when_no_filings_exist(db: Session) -> None:
    assert institutional_service.filings_refresh_is_stale(db) is True


def test_fresh_when_latest_filing_is_recent(db: Session) -> None:
    _seed_filing(db, created_at=datetime.utcnow() - timedelta(days=2))
    assert institutional_service.filings_refresh_is_stale(db) is False


def test_stale_when_latest_filing_is_older_than_threshold(db: Session) -> None:
    _seed_filing(db, created_at=datetime.utcnow() - timedelta(days=9))
    assert institutional_service.filings_refresh_is_stale(db) is True


def test_freshest_row_wins_over_older_history(db: Session) -> None:
    # MAX(created_at) semantics: one ancient row + one fresh row = fresh.
    _seed_filing(db, created_at=datetime.utcnow() - timedelta(days=300), slug="old-fund")
    _seed_filing(db, created_at=datetime.utcnow() - timedelta(days=1), slug="new-fund")
    assert institutional_service.filings_refresh_is_stale(db) is False


# ---------------------------------------------------------------------------
# Boot hook
# ---------------------------------------------------------------------------

def test_boot_catchup_never_runs_under_pytest(db: Session, monkeypatch) -> None:
    """PYTEST_CURRENT_TEST is set by pytest itself here — the guard must
    short-circuit BEFORE touching the DB or spawning any thread, exactly
    like the scan catch-up. (Empty DB = stale, so without the guard the
    thread WOULD be kicked.)"""
    called: list[bool] = []
    monkeypatch.setattr(
        main_module, "_run_institutionals_catchup", lambda: called.append(True)
    )
    main_module._catch_up_institutionals_on_boot()
    assert called == []


def test_boot_catchup_kicks_thread_when_stale(db: Session, monkeypatch) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    done = threading.Event()
    monkeypatch.setattr(main_module, "_run_institutionals_catchup", done.set)
    # Empty DB → filings_refresh_is_stale is True → thread spawned.
    main_module._catch_up_institutionals_on_boot()
    assert done.wait(timeout=5), "catch-up thread was not kicked despite stale data"


def test_boot_catchup_skips_when_fresh(db: Session, monkeypatch) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    _seed_filing(db, created_at=datetime.utcnow() - timedelta(days=1))
    called: list[bool] = []
    monkeypatch.setattr(
        main_module, "_run_institutionals_catchup", lambda: called.append(True)
    )
    main_module._catch_up_institutionals_on_boot()
    assert called == []


def test_catchup_runs_both_jobs_and_survives_a_failure(monkeypatch) -> None:
    """Dataroma failing (e.g. transient HTTP) must not block the SEC job."""
    order: list[str] = []

    def _boom() -> None:
        order.append("dataroma")
        raise RuntimeError("simulated scrape failure")

    monkeypatch.setattr(
        "app.scheduler.jobs.refresh_institutionals.run_refresh_institutionals",
        _boom,
    )
    monkeypatch.setattr(
        "app.scheduler.jobs.refresh_sec_13f.run_refresh_sec_13f",
        lambda: order.append("sec_13f"),
    )
    main_module._run_institutionals_catchup()
    assert order == ["dataroma", "sec_13f"]


# ---------------------------------------------------------------------------
# Il refresh RIUSCITO conta, non solo il filing NUOVO (2026-09-15)
# ---------------------------------------------------------------------------
#
# ⚠️ Il difetto misurato in produzione: 87 avvii del pod in 7 giorni, 87
# «institutional filings stale/absent», zero «fresh». I 13F escono una volta a
# TRIMESTRE; un refresh settimanale che non trova filing nuovi non crea righe,
# quindi `MAX(created_at)` resta fermo (ultimo: 22 agosto) e dopo 8 giorni ogni
# avvio rilanciava Dataroma e SEC 13F, ~3 minuti di scraping esterno a rilascio.
# La domanda giusta non e' «quando e' arrivato l'ultimo filing» ma «quando e'
# riuscito l'ultimo refresh».

def _marcatore(db: Session, fonte: str, *, giorni_fa: float) -> None:
    from app.models import FetchCache

    db.add(FetchCache(
        ticker=institutional_service.REFRESH_MARKER_TICKER,
        kind=f"refresh:{fonte}",
        payload="{}",
        fetched_at=datetime.utcnow() - timedelta(days=giorni_fa),
    ))
    db.commit()


def test_fresh_when_filings_are_old_but_both_sources_refreshed_recently(db: Session) -> None:
    """Il caso di produzione: filing vecchio di tre settimane, refresh riusciti ieri."""
    _seed_filing(db, created_at=datetime.utcnow() - timedelta(days=24))
    _marcatore(db, "dataroma", giorni_fa=1)
    _marcatore(db, "sec_13f", giorni_fa=1)
    assert institutional_service.filings_refresh_is_stale(db) is False


def test_stale_when_only_one_source_refreshed_recently(db: Session) -> None:
    """Il recupero lancia ENTRAMBE le fonti: se una non e' riuscita, va rifatto."""
    _seed_filing(db, created_at=datetime.utcnow() - timedelta(days=24))
    _marcatore(db, "dataroma", giorni_fa=1)
    assert institutional_service.filings_refresh_is_stale(db) is True


def test_stale_when_the_refresh_markers_are_old_too(db: Session) -> None:
    _seed_filing(db, created_at=datetime.utcnow() - timedelta(days=24))
    _marcatore(db, "dataroma", giorni_fa=9)
    _marcatore(db, "sec_13f", giorni_fa=9)
    assert institutional_service.filings_refresh_is_stale(db) is True


def _marcatori(db: Session) -> set[str]:
    from sqlalchemy import select

    from app.models import FetchCache

    return set(db.execute(
        select(FetchCache.kind).where(
            FetchCache.ticker == institutional_service.REFRESH_MARKER_TICKER
        )
    ).scalars())


@pytest.fixture
def job_db(db: Session, monkeypatch) -> Session:
    """Lega il `SessionLocal` dei due job alla sessione del test.

    ⚠️ Non e' ridondante col `conftest`. Quello sostituisce
    `app.core.db.SessionLocal`, ma i job fanno `from app.core.db import
    SessionLocal` al caricamento del modulo e restano legati all'ORIGINALE:
    senza questa fixture scrivono nel database configurato — in locale
    `backend/data/app.db`, il database di sviluppo. La prima versione di questi
    test lo ha fatto: i test «il marcatore c'e'» erano rossi leggendo il database
    di test vuoto, e peggio, quelli «non scrive niente» erano VERDI per la
    ragione sbagliata.
    """
    import app.core.db as db_module
    from app.scheduler.jobs import refresh_institutionals, refresh_sec_13f

    monkeypatch.setattr(refresh_institutionals, "SessionLocal", db_module.SessionLocal)
    monkeypatch.setattr(refresh_sec_13f, "SessionLocal", db_module.SessionLocal)
    return db


def test_dataroma_job_records_its_refresh_even_without_new_filings(job_db: Session, monkeypatch) -> None:
    db = job_db
    """⚠️ Il marcatore si scrive ANCHE a zero filing nuovi: e' esattamente il
    caso normale di tre settimane su quattro, ed e' il caso che il vecchio
    controllo non vedeva."""
    from app.scheduler.jobs import refresh_institutionals
    from app.services import institutional_scraper

    monkeypatch.setattr(institutional_scraper, "scrape_managers_index", lambda: ["un-gestore"])
    monkeypatch.setattr(institutional_scraper, "scrape_all_portfolios", lambda managers: [])
    monkeypatch.setattr(
        institutional_service, "persist_scrape_results",
        lambda db2, results, **kw: institutional_service.UpsertResult(0, 0, 0, 0, 0),
    )
    refresh_institutionals.run_refresh_institutionals()
    db.expire_all()
    assert _marcatori(db) == {"refresh:dataroma"}


def test_dataroma_job_that_aborts_records_nothing(job_db: Session, monkeypatch) -> None:
    db = job_db
    """Un refresh che non e' avvenuto non puo' dichiararsi riuscito: al
    prossimo avvio si deve riprovare."""
    from app.scheduler.jobs import refresh_institutionals
    from app.services import institutional_scraper

    monkeypatch.setattr(institutional_scraper, "scrape_managers_index", lambda: [])
    refresh_institutionals.run_refresh_institutionals()
    db.expire_all()
    assert _marcatori(db) == set()


def test_dataroma_job_whose_persist_fails_records_nothing(job_db: Session, monkeypatch) -> None:
    db = job_db
    from app.scheduler.jobs import refresh_institutionals
    from app.services import institutional_scraper

    def _boom(db2, results, **kw):
        raise RuntimeError("persist fallito")

    monkeypatch.setattr(institutional_scraper, "scrape_managers_index", lambda: ["un-gestore"])
    monkeypatch.setattr(institutional_scraper, "scrape_all_portfolios", lambda managers: [])
    monkeypatch.setattr(institutional_service, "persist_scrape_results", _boom)
    refresh_institutionals.run_refresh_institutionals()
    db.expire_all()
    assert _marcatori(db) == set()


def test_sec_13f_job_records_its_refresh(job_db: Session, monkeypatch) -> None:
    db = job_db
    from types import SimpleNamespace

    from app.scheduler.jobs import refresh_sec_13f
    from app.services import sec_13f_scraper

    monkeypatch.setattr(
        sec_13f_scraper, "list_curated_funds",
        lambda: [SimpleNamespace(slug="fondo", type_="institutional")],
    )
    monkeypatch.setattr(sec_13f_scraper, "fetch_all_curated", lambda: [])
    monkeypatch.setattr(sec_13f_scraper, "build_name_to_ticker_map", lambda stocks: {})
    monkeypatch.setattr(sec_13f_scraper, "load_cusip_ticker_map", lambda db2: {})
    monkeypatch.setattr(sec_13f_scraper, "fetch_sec_company_tickers", lambda: {})
    monkeypatch.setattr(
        institutional_service, "persist_scrape_results",
        lambda db2, results, **kw: institutional_service.UpsertResult(0, 0, 0, 0, 0),
    )
    refresh_sec_13f.run_refresh_sec_13f()
    db.expire_all()
    assert _marcatori(db) == {"refresh:sec_13f"}


# ---------------------------------------------------------------------------
# Cron misfire tolerance
# ---------------------------------------------------------------------------

def test_weekly_institutional_crons_have_misfire_grace(monkeypatch) -> None:
    """A laptop asleep at sat 04:00 but awake at 09:00 must still run the
    two weekly refreshes: both cron registrations need a misfire grace of
    at least 5 hours (we register 12h).

    The module singleton may have been started+stopped by an earlier test's
    TestClient lifespan (a stopped scheduler no longer exposes its jobs), so
    we force a FRESH never-started instance and inspect its pending jobs.
    """
    import app.scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module, "_scheduler", None)
    scheduler = scheduler_module.get_scheduler()  # built, never started
    for job_id in ("refresh_institutionals", "refresh_sec_13f"):
        job = scheduler.get_job(job_id)
        assert job is not None, f"job {job_id} is not registered"
        assert job.misfire_grace_time is not None
        assert job.misfire_grace_time >= 5 * 3600
