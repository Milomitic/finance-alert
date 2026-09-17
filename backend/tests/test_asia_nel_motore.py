"""I quindici titoli asiatici entrano nel motore, e SOLO loro.

Due meta' di una stessa richiesta, che senza test si rompono in silenzio in
direzioni opposte:

1. Le righe nuove (14 ADR su NYSE/NASDAQ + YINN su NYSE Arca) devono essere
   VISIBILI. Lo sono per via di `SURFACED_EXCHANGES`, cioe' per una proprieta'
   della borsa e non del ticker: se qualcuno scrivesse `NYSE American` o `AMEX`
   nel CSV, le righe nascerebbero invisibili e la semina sembrerebbe riuscita.
   Il test lega quindi il seme alla visibilita', non solo all'inserimento.

2. Samsung e SK Hynix stanno su KRX, che NON e' fra le borse esposte, e devono
   diventare visibili UNA PER UNA. L'utente ha chiesto «solo queste»: il
   controllo negativo su un'altra coreana e' cio' che distingue un'eccezione
   per ticker da uno sbraco dell'intero paese.

⚠️ E il test che protegge davvero il catalogo e' il terzo gruppo: il seme e'
idempotente per RIGA ma lo script canonico lavora per FILE, e `direxion_etfs.csv`
contiene 26 righe che la potatura del 2026-06 ha tolto di proposito. Seminare
quel file per prendersi YINN ne riporterebbe dentro 25 non richieste.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.visibility import is_visible_country, visible_country_clause
from app.models import Stock

SEED_DIR = Path(__file__).resolve().parent.parent / "app" / "data" / "seed"
ASIA_CSV = SEED_DIR / "asia_adr.csv"


def _aggiungi(db: Session, ticker: str, exchange: str, country: str) -> None:
    db.add(Stock(ticker=ticker, exchange=exchange, country=country, name=f"Prova {ticker}"))


def _visibili(db: Session) -> set[str]:
    """I ticker che sopravvivono alla clausola usata da ricerca, screener e scan."""
    return set(db.execute(select(Stock.ticker).where(visible_country_clause())).scalars())


# ─── 1. L'eccezione per ticker su KRX ──────────────────────────────────────

def test_samsung_e_sk_hynix_sono_visibili_pur_stando_su_krx(db: Session) -> None:
    _aggiungi(db, "005930.KS", "KRX", "KR")
    _aggiungi(db, "000660.KS", "KRX", "KR")
    db.flush()

    visibili = _visibili(db)
    assert "005930.KS" in visibili
    assert "000660.KS" in visibili


def test_le_altre_coreane_su_krx_restano_nascoste(db: Session) -> None:
    """Controllo negativo: l'eccezione e' per TICKER, non per paese.

    Senza questo, sostituire l'elenco dei ticker con la rimozione di "KR" da
    HIDDEN_COUNTRIES farebbe passare il test qui sopra e sbloccherebbe TUTTE
    e venti le KOSPI — il contrario di «solo queste».
    """
    _aggiungi(db, "005930.KS", "KRX", "KR")   # nell'elenco
    _aggiungi(db, "035420.KS", "KRX", "KR")   # NAVER, fuori dall'elenco
    _aggiungi(db, "7203.T", "JPX", "JP")      # Toyota sulla borsa di Tokyo
    db.flush()

    visibili = _visibili(db)
    assert "005930.KS" in visibili
    assert "035420.KS" not in visibili
    assert "7203.T" not in visibili


def test_la_gemella_python_concorda_con_la_clausola_sql(db: Session) -> None:
    """Le due implementazioni della stessa regola non devono divergere.

    `visible_country_clause` (SQL) e `is_visible_country` (in memoria) sono due
    copie della stessa decisione: la seconda la usano gli aggregatori che hanno
    gia' le righe in RAM. Due copie divergono al primo ritocco, ed e' successo
    in questo repo con `_posture` (un 500 in produzione).
    """
    casi = [
        ("005930.KS", "KRX", "KR"),    # eccezione per ticker
        ("000660.KS", "KRX", "KR"),    # eccezione per ticker
        ("035420.KS", "KRX", "KR"),    # nascosta
        ("7203.T", "JPX", "JP"),       # nascosta
        ("TM", "NYSE", "JP"),          # ADR: borsa esposta
        ("YINN", "NYSE Arca", "US"),   # ETF su borsa esposta
        ("9988.HK", "HKEX", "CN"),     # HK e' esposta
        ("AAPL", "NASDAQ", "US"),      # nessuna regola in gioco
    ]
    for ticker, exchange, country in casi:
        _aggiungi(db, ticker, exchange, country)
    db.flush()

    visibili = _visibili(db)
    for ticker, exchange, country in casi:
        atteso = ticker in visibili
        assert is_visible_country(country, exchange, ticker) is atteso, (
            f"{ticker}: SQL dice visibile={atteso}, la gemella Python dice il contrario"
        )


# ─── 2. Il CSV nuovo ───────────────────────────────────────────────────────

def test_il_csv_asia_ha_la_forma_che_il_seme_si_aspetta() -> None:
    """Sette campi, nomi non vuoti, ticker unici, NESSUNA riga di commento.

    ⚠️ `csv.DictReader` non conosce i commenti: una riga che comincia con '#'
    diventerebbe una riga DATI con `name` vuoto, e `Stock.name` e' NOT NULL.
    Le motivazioni stanno nello script, non qui.
    """
    with ASIA_CSV.open(encoding="utf-8") as f:
        righe = list(csv.DictReader(f))

    assert righe, "il CSV non deve essere vuoto"
    visti: set[str] = set()
    for r in righe:
        assert not r["ticker"].startswith("#"), f"riga di commento: {r['ticker']}"
        assert r["name"].strip(), f"{r['ticker']} senza nome"
        assert r["currency"].strip(), f"{r['ticker']} senza valuta"
        assert r["exchange"].strip(), f"{r['ticker']} senza borsa"
        assert r["ticker"] not in visti, f"ticker duplicato: {r['ticker']}"
        visti.add(r["ticker"])


def test_ogni_riga_del_csv_asia_nasce_visibile(db: Session) -> None:
    """Il punto dell'esercizio: se una borsa fosse scritta male, la riga
    entrerebbe nel catalogo e resterebbe invisibile — semina «riuscita» e
    utente che continua a non trovare niente."""
    from app.scripts.seed_asia_adr import semina

    semina(db)
    db.flush()

    with ASIA_CSV.open(encoding="utf-8") as f:
        attesi = {r["ticker"] for r in csv.DictReader(f)}
    visibili = _visibili(db)
    assert attesi <= visibili, f"nate invisibili: {sorted(attesi - visibili)}"


# ─── 3. Il seme ristretto alle righe ───────────────────────────────────────

def test_il_seme_crea_gli_adr_e_anche_yinn(db: Session) -> None:
    from app.scripts.seed_asia_adr import semina

    semina(db)
    db.flush()

    presenti = set(db.execute(select(Stock.ticker)).scalars())
    for t in ("TM", "SONY", "BABA", "KB", "CPNG", "YINN"):
        assert t in presenti, f"{t} non e' stata creata"


def test_yinn_nasce_etf_e_gli_adr_nascono_azioni(db: Session) -> None:
    """`instrument_type` decide se la riga riceve punteggi fondamentali e se
    entra nel confronto di mercato: un ETF a leva in mezzo alle azioni sporca
    entrambi."""
    from app.scripts.seed_asia_adr import semina

    semina(db)
    db.flush()

    tipo = dict(db.execute(select(Stock.ticker, Stock.instrument_type)).all())
    assert tipo["YINN"] == "etf"
    assert tipo["TM"] == "equity"
    assert tipo["BABA"] == "equity"


def test_il_seme_NON_risuscita_le_direxion_che_la_potatura_aveva_tolto(db: Session) -> None:
    """Il test che protegge il catalogo.

    YINN e' dichiarata in `direxion_etfs.csv` insieme ad altre 35 righe, di cui
    26 tolte dalla potatura del 2026-06 (misurato in produzione). Prendere YINN
    riseminando il file intero ne riporterebbe dentro 25 non richieste — fra cui
    YANG, il suo speculare ribassista.
    """
    from app.scripts.seed_asia_adr import semina

    semina(db)
    db.flush()

    presenti = set(db.execute(select(Stock.ticker)).scalars())
    assert "YINN" in presenti
    for potata in ("YANG", "FAS", "FAZ", "TQQQ", "SQQQ", "DUST", "JNUG", "TMF"):
        assert potata not in presenti, (
            f"{potata} e' stata risuscitata: il seme sta lavorando per FILE invece che per RIGA"
        )


def test_il_seme_e_idempotente(db: Session) -> None:
    from app.scripts.seed_asia_adr import semina

    primo = semina(db)
    db.flush()
    secondo = semina(db)
    db.flush()

    assert primo.added > 0
    assert secondo.added == 0, "una seconda corsa non deve creare righe nuove"
    assert secondo.updated == primo.added


def test_il_filtro_per_riga_prende_solo_i_ticker_chiesti(db: Session) -> None:
    """L'unita' sotto lo script, provata da sola su un CSV di prova."""
    from app.services.seed_service import seed_stocks_subset_from_csv

    csv_prova = (
        "ticker,name,exchange,sector,industry,country,currency\n"
        "VOGLIO,Voluta SpA,NYSE,Financial Services,Leveraged ETF,US,USD\n"
        "NONVOGLIO,Non voluta SpA,NYSE,Financial Services,Leveraged ETF,US,USD\n"
    )
    res = seed_stocks_subset_from_csv(
        db, io.StringIO(csv_prova), only=frozenset({"VOGLIO"})
    )
    db.flush()

    presenti = set(db.execute(select(Stock.ticker)).scalars())
    assert res.added == 1
    assert "VOGLIO" in presenti
    assert "NONVOGLIO" not in presenti


# ─── 4. La conseguenza a schermo ───────────────────────────────────────────

def test_lo_screener_offre_krx_proprio_perche_esiste_l_eccezione(db: Session) -> None:
    """Il menu «Borsa» dello screener deve offrire KRX quando c'e' un titolo
    KRX esposto — altrimenti l'utente vede le due righe in ricerca ma non puo'
    filtrarle.

    ⚠️ Le opzioni dei filtri sono costruite da una query PROPRIA: passa dalla
    stessa clausola, ma se qualcuno la dimenticasse li' il difetto sarebbe
    parziale, cioe' del tipo peggiore — visibili da una parte e assenti
    dall'altra.
    """
    from fastapi.testclient import TestClient

    from app.api.deps import get_current_user, get_db
    from app.main import app
    from app.models import User

    _aggiungi(db, "005930.KS", "KRX", "KR")   # esposta
    _aggiungi(db, "035420.KS", "KRX", "KR")   # NAVER, nascosta
    _aggiungi(db, "7203.T", "JPX", "JP")      # Toyota Tokyo, nascosta
    utente = User(username="admin", password_hash="x")
    db.add(utente)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: utente
    try:
        dati = TestClient(app).get("/api/stocks/filters").json()
    finally:
        app.dependency_overrides.clear()

    assert "KRX" in dati["exchanges"], "la borsa del titolo esposto non e' filtrabile"
    assert "JPX" not in dati["exchanges"], "JPX non ha titoli esposti: non va offerta"


def test_run_semina_e_COMMITTA_sulla_sessione_giusta(db: Session, monkeypatch) -> None:
    """`run()` e' cio' che gira davvero nel pod, `db.commit()` compreso.

    ⚠️ Il monkeypatch non e' una formalita': lo script fa
    `from app.core.db import SessionLocal` al caricamento del modulo, quindi
    resta legato all'ORIGINALE anche quando il conftest sostituisce quello di
    `app.core.db`. Senza, questo test scriverebbe nel database di SVILUPPO e
    poi fallirebbe leggendo quello di test — o peggio passerebbe misurando il
    database sbagliato. La stessa trappola e' documentata in
    `test_institutionals_catchup.py`, dove e' gia' costata una volta.
    """
    from app.core import db as db_module
    from app.scripts import seed_asia_adr

    monkeypatch.setattr(seed_asia_adr, "SessionLocal", db_module.SessionLocal)
    seed_asia_adr.run()

    presenti = set(db.execute(select(Stock.ticker)).scalars())
    assert {"TM", "BABA", "KB", "YINN"} <= presenti
    assert "YANG" not in presenti, "il filtro per riga non ha retto dentro run()"
