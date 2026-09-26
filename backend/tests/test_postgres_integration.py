"""Real-Postgres integration smoke (M7-P1).

Guarded by ``TEST_DATABASE_URL`` — skipped everywhere it is unset (every local
run; the SQLite suite covers behaviour). The CI ``backend-postgres`` job points
it at a throwaway ``postgres:16`` service and runs this module to prove the two
things the compile-only ``test_db_json_dialect`` tests cannot:

  1. the ENTIRE schema (``Base.metadata.create_all``) maps to real Postgres DDL
     and executes — the prerequisite for the M7-P3 data migration. (The local
     ``CreateTable(...).compile(dialect=postgresql)`` check catches un-renderable
     types; only a live server catches execution-time DDL problems.)
  2. ``json_text`` extracts snapshot scalars *semantically* on real Postgres
     (``jsonb ->>``), not merely that the emitted SQL string looks right.

Isolation: the schema is created once per module; each test runs inside an outer
transaction rolled back at teardown, so tests never see each other's rows. Tests
only ``flush`` (never ``commit``), so the rollback fully discards their writes.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import Float, cast, create_engine, inspect, select
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 — registers every mapper on Base.metadata
from app.core.config import settings
from app.core.db import Base
from app.core.db_json import json_text
from app.models import Alert, Stock

_PG_URL = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not _PG_URL.startswith("postgresql"),
    reason="TEST_DATABASE_URL (postgresql://…) unset — real-Postgres CI lane only",
)


@pytest.fixture(scope="module")
def pg_engine():
    """Module-scoped engine; create the whole schema once, drop it at the end.
    ``create_all`` here is itself the P3 schema-portability assertion — if any
    model fails to map to Postgres DDL, every test in the module errors loudly."""
    engine = create_engine(_PG_URL, future=True)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def pg(pg_engine):
    """Function-scoped session inside an outer transaction rolled back at
    teardown — the standard 'join an external transaction' isolation pattern."""
    conn = pg_engine.connect()
    txn = conn.begin()
    maker = sessionmaker(bind=conn, autoflush=False, autocommit=False)
    session = maker()
    try:
        yield session
    finally:
        session.close()
        txn.rollback()
        conn.close()


def test_full_schema_creates_on_postgres(pg_engine):
    """create_all (in the fixture) already executed the DDL; confirm the core
    tables really materialised on the server."""
    tables = set(inspect(pg_engine).get_table_names())
    assert {"alerts", "stocks"} <= tables


def test_l_ultima_scansione_riuscita_ignora_le_righe_senza_data_su_POSTGRES(pg) -> None:
    """La trappola dei NULL in testa, riprodotta dove esiste.

    In un ordinamento decrescente Postgres mette i NULL PER PRIMI. Con 18
    esecuzioni `success` senza `completed_at` in produzione, la forma
    `ORDER BY completed_at DESC LIMIT 1` restituiva quella senza data: il
    recupero all'avvio lanciava una scansione completa a ogni ricreazione del
    pod, e la finestra di recenza dei segnali non si allargava mai.

    ⚠️ Il test esegue PRIMA la forma vecchia e pretende che sbagli. Senza,
    sarebbe verde anche su un server che ordinasse i NULL in fondo, cioe' non
    proverebbe che la funzione nuova serve.
    """
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import desc

    from app.models import ScanRun
    from app.models.scan_run import last_successful_completed_at

    fresca = datetime.now(UTC) - timedelta(hours=2)
    pg.add(ScanRun(trigger="manual", status="success", completed_at=None))
    pg.add(ScanRun(trigger="cron", status="success", completed_at=fresca))
    pg.flush()

    vecchia_forma = pg.execute(
        select(ScanRun.completed_at)
        .where(ScanRun.status == "success")
        .order_by(desc(ScanRun.completed_at))
        .limit(1)
    ).scalar()
    assert vecchia_forma is None, "su questo server i NULL non vengono primi: il test non prova niente"

    assert last_successful_completed_at(pg) == fresca


def test_json_text_extracts_scalar_on_postgres(pg):
    """The migrated query idiom (filter/cast on snapshot fields) returns correct
    rows against real Postgres jsonb ->>, not just SQLite json_extract."""
    s = Stock(ticker="PGX", exchange="NASDAQ", name="PG Test", country="US")
    pg.add(s)
    pg.flush()
    for tone, strength in (("bull", 80), ("bull", 40), ("bear", 90)):
        pg.add(Alert(
            stock_id=s.id, trigger_price=1.0, signal_date=date(2026, 1, 1),
            signal_name="x", snapshot=json.dumps({"tone": tone, "strength": strength}),
        ))
    pg.flush()

    bulls = pg.execute(
        select(Alert).where(json_text(Alert.snapshot, "tone") == "bull")
    ).scalars().all()
    assert len(bulls) == 2

    strong = pg.execute(
        select(Alert).where(cast(json_text(Alert.snapshot, "strength"), Float) >= 75)
    ).scalars().all()
    assert len(strong) == 2  # strengths 80 and 90 clear the bar; 40 does not


def test_one_failed_stock_does_not_poison_the_rest_of_the_batch(pg, monkeypatch):
    """THE regression test for the 17 July 2026 ETF outage.

    Postgres puts a transaction into the aborted state as soon as ONE
    statement errors; every later command then returns InFailedSqlTransaction.
    ohlcv_service's per-stock loop catches its exceptions and carries on —
    correct on SQLite, catastrophic here: one price-basis mismatch aborted the
    transaction and the ~10 tickers behind it in the same batch (SPY, QQQ,
    XLF, XLE, XBI, SOXX…) were silently never written, so their charts stopped
    dead while every scan still reported success.

    This drives the REAL fetch_and_upsert loop (only the yfinance I/O and the
    row-building are stubbed) so it fails if the `begin_nested()` savepoint is
    ever removed. On SQLite it would pass either way — hence the Postgres lane.
    """
    from sqlalchemy import insert

    from app.models import OhlcvDaily
    from app.services import ohlcv_service

    bad = Stock(ticker="PGBAD", exchange="NASDAQ", name="Poisoner", country="US")
    good = Stock(ticker="PGGOOD", exchange="NASDAQ", name="Victim", country="US")
    pg.add_all([bad, good])
    pg.flush()

    # Pre-existing bar the poisoner will collide with (PK = stock_id + date).
    day = date(2026, 7, 20)
    base = {"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}
    pg.execute(insert(OhlcvDaily).values(stock_id=bad.id, date=day, **base))

    monkeypatch.setattr(ohlcv_service, "_yf_download", lambda *a, **k: object())
    monkeypatch.setattr(ohlcv_service, "_extract_ticker_frame", lambda df, t: [t])

    def fake_upsert(db, stock, frame):
        if stock.ticker == "PGBAD":
            # Duplicate PK → IntegrityError → transaction aborted on Postgres.
            db.execute(insert(OhlcvDaily).values(stock_id=stock.id, date=day, **base))
        db.execute(insert(OhlcvDaily).values(stock_id=stock.id, date=date(2026, 7, 21), **base))
        return 1, 0

    monkeypatch.setattr(ohlcv_service, "_upsert_one_stock", fake_upsert)

    result = ohlcv_service.fetch_and_upsert(pg, [bad, good], period="1mo")

    # The poisoner fails — expected. The one BEHIND it must still be written.
    assert result.stocks_failed == 1
    assert result.stocks_succeeded == 1, "the failed stock poisoned the rest of the batch"
    landed = pg.execute(
        select(OhlcvDaily.date).where(OhlcvDaily.stock_id == good.id)
    ).scalars().all()
    assert date(2026, 7, 21) in landed


def test_l_ampiezza_per_direzione_gira_su_POSTGRES(pg) -> None:
    """FA-064 su Postgres vero.

    La query raggruppa su un'espressione estratta dallo snapshot JSON e filtra
    su una tupla `(detector, giorno) IN (...)`. Entrambe le forme hanno un
    precedente di divergenza fra dialetti in questo progetto — la famiglia
    `json_text` e' esattamente cio' per cui questa corsia blocca il rilascio —
    e la suite SQLite non puo' dire se Postgres accetta il GROUP BY
    sull'espressione.
    """
    from datetime import datetime as _dt

    from app.services.signal_breadth_service import breadth_for, peers_for

    giorno = date(2026, 9, 8)
    titoli = {}
    for t, settore in (("NVDA", "IT"), ("AMD", "IT"), ("MU", "IT"), ("XOM", "Energy")):
        s = Stock(ticker=t, exchange="NASDAQ", name=t, sector=settore)
        pg.add(s)
        titoli[t] = s
    pg.flush()

    def _a(t, tono):
        a = Alert(stock_id=titoli[t].id, signal_name="trend_pullback", signal_date=giorno,
                  triggered_at=_dt(2026, 9, 8, 10), trigger_price=1.0,
                  snapshot=json.dumps({"tone": tono}))
        pg.add(a)
        return a

    mio = _a("NVDA", "bull")
    _a("AMD", "bull")
    _a("MU", "bear")
    _a("XOM", "bull")
    pg.flush()

    got = breadth_for(pg, [mio], stock_id=titoli["NVDA"].id, sector="IT")[mio.id]
    assert (got.same_tone, got.same_tone_sector, got.opposite_tone) == (2, 1, 1)
    assert [p.ticker for p in peers_for(pg, mio)] == ["AMD", "XOM"]


@contextmanager
def _database_vuoto(monkeypatch):
    """Un database Postgres NUOVO e vuoto, con Alembic puntato su di lui.

    ⚠️ `cfg.set_main_option("sqlalchemy.url", ...)` NON basta: `alembic/env.py`
    sovrascrive quell'opzione con `settings.database_url`, perche' `alembic.ini`
    la lascia VUOTA di proposito. Il primo giro di questi test ci era cascato e
    PASSAVA girando contro il database predefinito.
    """
    import uuid

    from alembic.config import Config
    from sqlalchemy import text

    nome = f"fa_mig_{uuid.uuid4().hex[:12]}"
    radice = create_engine(_PG_URL, future=True, isolation_level="AUTOCOMMIT")
    with radice.connect() as c:
        c.execute(text(f'CREATE DATABASE "{nome}"'))
    radice.dispose()

    url = _PG_URL.rsplit("/", 1)[0] + "/" + nome
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    monkeypatch.setattr(settings, "database_url", url)
    eng = create_engine(url, future=True)
    try:
        yield cfg, eng
    finally:
        eng.dispose()
        radice = create_engine(_PG_URL, future=True, isolation_level="AUTOCOMMIT")
        with radice.connect() as c:
            c.execute(text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :n AND pid <> pg_backend_pid()"), {"n": nome})
            c.execute(text(f'DROP DATABASE IF EXISTS "{nome}"'))
        radice.dispose()


def test_la_catena_INTERA_arriva_in_fondo_da_vuoto_su_POSTGRES(monkeypatch) -> None:
    """FA-070. `alembic upgrade head` da un database vuoto, su Postgres vero.

    ⚠️ Lo schema di produzione NON e' nato da questa catena: e' nato da
    `create_all` piu' uno `stamp`, e il drill del lunedi' lo verifica ogni
    settimana. Quindi nessuno aveva mai eseguito queste migrazioni su Postgres,
    e la prima volta che e' successo — lavorando a FA-061 — la catena si e'
    fermata su un default intero dato a una colonna booleana, che SQLite accetta.
    Ricostruire il database da zero con le migrazioni e' una cosa che si scopre
    rotta nel momento peggiore.

    Due asserzioni oltre al «non solleva»: la revisione registrata e' la testa,
    e ogni tabella dei modelli esiste. La seconda e' quella che distingue una
    catena che arriva in fondo da una che ci arriva avendo saltato qualcosa.
    """
    from alembic.script import ScriptDirectory
    from sqlalchemy import text

    from alembic import command

    with _database_vuoto(monkeypatch) as (cfg, eng):
        command.upgrade(cfg, "head")

        with eng.connect() as c:
            registrata = c.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
        assert registrata == ScriptDirectory.from_config(cfg).get_heads()

        tabelle = set(inspect(eng).get_table_names())
        mancanti = sorted(set(Base.metadata.tables) - tabelle)
        assert mancanti == [], f"tabelle dei modelli che la catena non crea: {mancanti}"


def _inserisci(c, tabella: str, **valori) -> None:
    """INSERT che riempie da solo le colonne NOT NULL senza default.

    Il test di FA-061 parte ora dallo schema che la catena produce DAVVERO, non
    da una tabella a tre colonne scritta a mano — e quello schema ha colonne
    obbligatorie che il test non ha motivo di conoscere. Leggerle dal catalogo
    tiene il test legato a cio' che la migrazione trova, invece che a una copia
    del modello che invecchierebbe alla prossima colonna.
    """
    from sqlalchemy import text

    obbligatorie = c.execute(text(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = :t AND is_nullable = 'NO' AND column_default IS NULL"
    ), {"t": tabella}).all()
    riempitivo = {
        "integer": 0, "bigint": 0, "smallint": 0,
        "double precision": 0.0, "real": 0.0, "numeric": 0,
        "boolean": False, "date": date(2026, 1, 2),
    }
    for nome, tipo in obbligatorie:
        if nome in valori:
            continue
        if tipo.startswith("timestamp"):
            valori[nome] = "2026-01-02T00:00:00+00:00"
        else:
            valori[nome] = riempitivo.get(tipo, "x")
    colonne = ", ".join(valori)
    segnaposto = ", ".join(f":{k}" for k in valori)
    c.execute(text(f"INSERT INTO {tabella} ({colonne}) VALUES ({segnaposto})"), valori)


def test_la_migrazione_FA_061_gira_su_POSTGRES_andata_e_ritorno(monkeypatch) -> None:
    """La migrazione degli episodi di setup, eseguita su Postgres vero.

    ⚠️ Questo test partiva da una tabella a tre colonne scritta a mano, piu' uno
    `stamp`, e il docstring ne spiegava la ragione: `upgrade head` da vuoto si
    fermava su `0601129beb3a` (un default intero dato a una colonna booleana), e
    tenere ostaggio la verifica di una migrazione nuova a una catena che nessuno
    aveva mai eseguito avrebbe significato non verificarne nessuna.

    FA-070 ha reso la catena eseguibile, quindi la scorciatoia non serve piu' e
    anzi costava qualcosa: la tabella scritta a mano era il contratto che il
    test IMMAGINAVA, non lo schema che la migrazione trova davvero. Ora si sale
    con la catena fino alla revisione precedente e poi di un passo.

    ⚠️ E si prova anche il RITORNO. Una migrazione che non si ripercorre
    all'indietro va scoperta adesso, non durante un ripristino.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    from alembic import command

    _PRIMA = "3d8693a96ce6"   # la revisione su cui FA-061 si innesta

    with _database_vuoto(monkeypatch) as (cfg, eng):
        # La forma PRE-migrazione, prodotta dalla catena e non descritta a mano.
        command.upgrade(cfg, _PRIMA)
        with eng.connect() as c:
            vincoli = {r[0] for r in c.execute(text(
                "SELECT conname FROM pg_constraint WHERE conrelid = "
                "'stock_setups'::regclass"))}
        # Il punto di partenza e' quello che la migrazione si aspetta: se la
        # catena non avesse il vincolo unico sulla coppia, il resto del test
        # proverebbe una trasformazione che non avviene.
        assert "uq_stock_setups_stock_detector" in vincoli

        command.upgrade(cfg, "head")
        with eng.connect() as c:
            ddl = c.execute(text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'stock_setups' "
                "  AND indexname = 'uq_stock_setups_open_episode'"
            )).scalar_one()
            colonne = {r[0] for r in c.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'stock_setups'"))}
            vincoli = {r[0] for r in c.execute(text(
                "SELECT conname FROM pg_constraint WHERE conrelid = "
                "'stock_setups'::regclass"))}
        # ⚠️ L'indice deve portare la sua clausola: senza il WHERE sarebbe un
        # vincolo su TUTTA la tabella, la storia degli episodi tornerebbe
        # impossibile, e nulla lo direbbe.
        assert "UNIQUE" in ddl.upper()
        assert "WHERE" in ddl.upper() and "active" in ddl
        assert "closed_reason" in colonne
        # Il vincolo vecchio se n'e' andato: se restasse, due episodi chiusi
        # sulla stessa coppia sarebbero ancora vietati.
        assert "uq_stock_setups_stock_detector" not in vincoli

        # Due episodi CHIUSI convivono, uno solo puo' essere APERTO. Il titolo
        # esiste davvero: lo schema vero ha la chiave esterna.
        with eng.begin() as c:
            _inserisci(c, "stocks", id=1, ticker="AAA", exchange="NYSE", name="Aaa")
            _inserisci(c, "stock_setups", stock_id=1, detector="x", status="expired")
            _inserisci(c, "stock_setups", stock_id=1, detector="x", status="expired")
            _inserisci(c, "stock_setups", stock_id=1, detector="x", status="active")
        # ⚠️ `IntegrityError` e non `Exception`: un'eccezione qualunque
        # passerebbe anche su un refuso nella SQL qui sopra, cioe' il test
        # sarebbe verde per la ragione sbagliata.
        with pytest.raises(IntegrityError), eng.begin() as c:
            _inserisci(c, "stock_setups", stock_id=1, detector="x", status="active")

        # Il ritorno. Dichiara la perdita e la esegue: lo schema di
        # destinazione non ha dove mettere il secondo episodio.
        command.downgrade(cfg, _PRIMA)
        with eng.connect() as c:
            rimaste = c.execute(text("SELECT count(*) FROM stock_setups")).scalar_one()
            colonne = {r[0] for r in c.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'stock_setups'"))}
        assert rimaste == 1, "il downgrade deve lasciare UNA riga per coppia"
        assert "closed_reason" not in colonne

        # E si risale, perche' un ripristino seguito da un aggiornamento e' il
        # caso reale, non l'andata da sola.
        command.upgrade(cfg, "head")


def test_il_tono_senza_direzione_entra_nella_colonna_su_POSTGRES(monkeypatch) -> None:
    """Il difetto che ha fermato ogni scansione in produzione, riprodotto dove esiste.

    FA-061 ha introdotto il tono `undetermined` (12 caratteri) in
    `stock_setups.tone`, una colonna `String(8)`. Postgres lo rifiuta con
    `StringDataRightTruncation`, e dalle 19:53 UTC del 2026-09-14 tutte le
    scansioni sono crollate al primo setup di `squeeze_expansion`. SQLite non
    fa rispettare la lunghezza, quindi solo questa corsia puo' vederlo.

    ⚠️ Il test prova PRIMA il rifiuto sullo schema di prima. Senza, sarebbe
    verde anche se la colonna fosse sempre stata larga abbastanza — cioe' non
    direbbe niente sulla migrazione.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import DataError

    from alembic import command
    from app.signals.setups.base import TONE_UNDETERMINED

    _PRIMA = "78d64d497ae0"   # la revisione su cui l'allargamento si innesta

    with _database_vuoto(monkeypatch) as (cfg, eng):
        command.upgrade(cfg, _PRIMA)
        with eng.begin() as c:
            _inserisci(c, "stocks", id=1, ticker="AAA", exchange="NYSE", name="Aaa")

        # Il controllo negativo: e' l'errore esatto dei log di produzione.
        # `DataError` e non `Exception`, per la stessa ragione dell'IntegrityError
        # del test sopra.
        with pytest.raises(DataError, match="value too long"), eng.begin() as c:
            _inserisci(c, "stock_setups", stock_id=1, detector="squeeze_expansion",
                       status="active", tone=TONE_UNDETERMINED)

        command.upgrade(cfg, "head")
        with eng.begin() as c:
            _inserisci(c, "stock_setups", stock_id=1, detector="squeeze_expansion",
                       status="active", tone=TONE_UNDETERMINED)

        # Il ritorno RIFIUTA finche' c'e' un tono che lo schema vecchio non
        # contiene, e non tocca niente: la revisione resta la testa.
        with pytest.raises(RuntimeError, match="stock_setups"):
            command.downgrade(cfg, _PRIMA)
        with eng.connect() as c:
            testa = c.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            toni = c.execute(text("SELECT tone FROM stock_setups")).scalars().all()
        assert testa != _PRIMA, "il downgrade rifiutato ha comunque spostato la revisione"
        assert toni == [TONE_UNDETERMINED], "il downgrade rifiutato ha toccato i dati"

        # Senza righe incompatibili il ritorno passa, e si risale.
        with eng.begin() as c:
            c.execute(text("DELETE FROM stock_setups"))
        command.downgrade(cfg, _PRIMA)
        command.upgrade(cfg, "head")


def test_la_migrazione_PLAN_OUTCOMES_gira_su_POSTGRES_andata_e_ritorno(monkeypatch) -> None:
    """La tabella degli esiti di piano, su Postgres vero, in entrambi i versi.

    Il test generale qui sopra confronta i modelli con le tabelle create e
    coprirebbe gia' l'esistenza. Questo aggiunge le due cose che quel confronto
    NON vede, ed entrambe sono trappole di dialetto:

    1. Il default di una colonna BOOLEANA. Scritto `sa_text("0")` renderebbe
       `DEFAULT 0` su Postgres, che li' e' un errore di TIPO; `sa.false()` e'
       dialect-aware. Su SQLite i due sono indistinguibili, quindi la corsia
       veloce non puo' dirlo — la stessa nota sta su `stocks.ohlcv_in_pounds`,
       dove e' gia' costata una volta.
    2. Il RITORNO. Una migrazione che non si ripercorre va scoperta adesso e
       non durante un ripristino.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    from alembic import command

    _PRIMA = "d9e4b6a1c7f2"   # la revisione su cui questa si innesta

    with _database_vuoto(monkeypatch) as (cfg, eng):
        command.upgrade(cfg, _PRIMA)
        assert "plan_outcomes" not in set(inspect(eng).get_table_names()), (
            "la tabella esiste gia' PRIMA della sua migrazione: il test "
            "proverebbe una trasformazione che non avviene"
        )

        command.upgrade(cfg, "head")
        assert "plan_outcomes" in set(inspect(eng).get_table_names())

        with eng.begin() as c:
            c.execute(text(
                "INSERT INTO stocks (ticker, exchange, name, country, "
                "ohlcv_in_pounds, ohlcv_nodata_streak, instrument_type) "
                "VALUES ('AAA', 'NASDAQ', 'AAA Corp', 'US', false, 0, 'equity')"))
            sid = c.execute(text("SELECT id FROM stocks WHERE ticker='AAA'")).scalar_one()
            c.execute(text(
                "INSERT INTO alerts (stock_id, triggered_at, trigger_price, snapshot) "
                "VALUES (:s, now(), 100.0, '{}')"), {"s": sid})
            aid = c.execute(text("SELECT id FROM alerts")).scalar_one()
            # ⚠️ `tp2_reached` NON e' passato: se il suo default non fosse
            # valido per Postgres, questa INSERT fallirebbe qui.
            c.execute(text(
                "INSERT INTO plan_outcomes (alert_id, stock_id, detector, "
                "signal_date, tone, horizon_days, entry_date, entry, stop, tp1, "
                "tp2, r, esito, resolved_date, bars_to_outcome, r_multiple, "
                "mae_r, mfe_r, matured_at) VALUES (:a, :s, 'sr_flip', "
                "'2026-03-01', 'bull', 21, '2026-03-02', 100, 96, 108, 112, 4, "
                "'ambigua', '2026-03-10', 6, -1, 0.25, 2.25, now())"),
                {"a": aid, "s": sid})

        with eng.connect() as c:
            fatto = c.execute(text(
                "SELECT tp2_reached FROM plan_outcomes")).scalar_one()
        assert fatto is False, "il default booleano non e' arrivato come booleano"

        # L'unicita' e' del DATABASE, non della diligenza del chiamante.
        with pytest.raises(IntegrityError), eng.begin() as c:
            c.execute(text(
                "INSERT INTO plan_outcomes (alert_id, stock_id, detector, "
                "signal_date, tone, horizon_days, entry_date, entry, stop, "
                "tp1, r, esito, resolved_date, bars_to_outcome, r_multiple, "
                "mae_r, mfe_r, matured_at) VALUES (:a, :s, 'sr_flip', "
                "'2026-03-01', 'bull', 21, '2026-03-02', 100, 96, 108, 4, "
                "'stop', '2026-03-11', 7, -1, 1.0, 0.5, now())"),
                {"a": aid, "s": sid})

        command.downgrade(cfg, _PRIMA)
        assert "plan_outcomes" not in set(inspect(eng).get_table_names()), (
            "il downgrade non ha rimosso la tabella"
        )


def test_un_doppione_negli_scartati_non_avvelena_la_sessione_su_POSTGRES(pg) -> None:
    """Il registro degli scartati scrive DENTRO il ciclo dello scan, che cattura
    l'eccezione di un titolo senza rollback. Su Postgres una scrittura fallita
    lascia la transazione abortita e ogni comando successivo risponde
    InFailedSqlTransaction: un doppione fermerebbe tutti i titoli dietro —
    la forma del fermo di diciannove ore gia' registrato. Su SQLite il test
    passerebbe comunque, quindi sta in questa corsia."""
    from datetime import UTC, datetime

    from sqlalchemy import func
    from sqlalchemy import insert as insert_semplice
    from sqlalchemy.exc import IntegrityError

    from app.models import SignalCandidate
    from app.signals.detectors.base import SignalMatch
    from app.signals.signal_scan_service import _registra_scartato

    s = Stock(ticker="PGSCART", exchange="NASDAQ", name="Scartati", country="US")
    pg.add(s)
    pg.flush()
    giorno = date(2026, 5, 30)
    m = SignalMatch(name="sr_flip", tone="bull", signal_date=giorno.isoformat(), chain=[],
                    invalidation=None, factors={"x": 1.0}, strength=40, probability=50)

    # Il controllo negativo: l'unicita' c'e', e un inserimento semplice la viola.
    _registra_scartato(pg, s.id, m, giorno, giorno, 100.0, False, True, True, scartati={})
    with pytest.raises(IntegrityError), pg.begin_nested():
        pg.execute(insert_semplice(SignalCandidate).values(
            stock_id=s.id, detector="sr_flip", tone="bull", signal_date=giorno,
            bar_date=giorno, close=1.0, strength=40, passa_forza=False,
            passa_trend=True, passa_follow=True, created_at=datetime.now(UTC)))

    # Il caso vero: il promemoria in memoria non sa della riga, e il secondo
    # inserimento deve TACERE.
    _registra_scartato(pg, s.id, m, giorno, giorno, 100.0, False, True, True, scartati={})

    # E la sessione deve essere ancora sana: una lettura qualunque dopo.
    n = pg.execute(select(func.count()).select_from(SignalCandidate)).scalar_one()
    assert n == 1


def test_la_migrazione_SCARTATI_gira_su_POSTGRES_andata_e_ritorno(monkeypatch) -> None:
    """La tabella degli scartati in entrambi i versi, con l'unicita' imposta
    dal database. Il ritorno la cancella: lo dice la migrazione stessa."""
    from sqlalchemy import text

    from alembic import command

    _PRIMA = "c3a91f26d8b4"

    with _database_vuoto(monkeypatch) as (cfg, eng):
        command.upgrade(cfg, _PRIMA)
        assert "signal_candidates" not in set(inspect(eng).get_table_names())
        command.upgrade(cfg, "head")
        assert "signal_candidates" in set(inspect(eng).get_table_names())
        indici = {i["name"]: i for i in inspect(eng).get_indexes("signal_candidates")}
        assert indici["ix_signal_candidates_unico"]["unique"]

        with eng.begin() as c:
            _inserisci(c, "stocks", id=1, ticker="AAA", exchange="NYSE", name="Aaa")
            c.execute(text(
                "INSERT INTO signal_candidates (stock_id, detector, tone, signal_date, "
                "bar_date, close, strength, passa_forza, passa_trend, passa_follow, "
                "created_at) VALUES (1, 'sr_flip', 'bull', '2026-05-30', '2026-05-30', "
                "100, 40, false, true, true, now())"))

        command.downgrade(cfg, _PRIMA)
        assert "signal_candidates" not in set(inspect(eng).get_table_names())
        command.upgrade(cfg, "head")


def test_la_migrazione_EMITTED_AT_riempie_lo_storico_su_POSTGRES(monkeypatch) -> None:
    """FA-100 su Postgres, dove gira in produzione: il riempimento passa da un
    UPDATE tipato (timestamptz) e da una copia fra colonne, poi NOT NULL e
    default arrivano con due ALTER invece che con la tabella ricreata di
    SQLite. Andata, ritorno, andata."""
    from datetime import UTC, datetime

    from sqlalchemy import text

    from alembic import command

    _PRIMA = "f7a3c9e2b1d4"

    with _database_vuoto(monkeypatch) as (cfg, eng):
        command.upgrade(cfg, _PRIMA)
        with eng.begin() as c:
            _inserisci(c, "stocks", id=1, ticker="AAA", exchange="NYSE", name="Aaa")
            # Rivisto: nato il 20, ultima revisione il 25.
            _inserisci(c, "alerts", id=1, stock_id=1, trigger_price=50.0,
                       snapshot=json.dumps({"first_emitted_at": "2026-09-20T23:32:00+00:00"}),
                       triggered_at="2026-09-25T23:33:00+00:00")
            # Mai rivisto, senza il campo: la nascita e' la scrittura.
            _inserisci(c, "alerts", id=2, stock_id=1, trigger_price=50.0, snapshot="{}",
                       triggered_at="2026-09-22T23:31:00+00:00")
        command.upgrade(cfg, "head")

        with eng.connect() as c:
            nascite = dict(c.execute(text("SELECT id, emitted_at FROM alerts")).all())
        assert nascite == {
            1: datetime(2026, 9, 20, 23, 32, tzinfo=UTC),
            2: datetime(2026, 9, 22, 23, 31, tzinfo=UTC),
        }
        colonna = {col["name"]: col for col in inspect(eng).get_columns("alerts")}["emitted_at"]
        assert colonna["nullable"] is False and colonna["default"] is not None
        assert "ix_alerts_emitted_at" in {i["name"] for i in inspect(eng).get_indexes("alerts")}

        command.downgrade(cfg, _PRIMA)
        assert "emitted_at" not in {col["name"] for col in inspect(eng).get_columns("alerts")}
        command.upgrade(cfg, "head")
