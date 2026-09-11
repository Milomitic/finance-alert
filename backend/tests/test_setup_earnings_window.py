"""La trimestrale dentro la finestra di attesa di un setup.

Voce 4.3 del piano, audit §7.4. *In formazione* dice da quanto un setup
aspetta; il calendario sa quando quel ticker pubblica. Separate, nessuna delle
due pagine puo porre la domanda che conta: **il setup si risolve prima o dopo
la trimestrale?** Una trimestrale sovrascrive la tesi tecnica.

⚠️ LA FINESTRA E IL TETTO, NON LA SCADENZA SCORREVOLE. Un setup chiude per due
regole: `_EXPIRE_AFTER_DAYS` da `last_seen_at` e `_MAX_AGE_DAYS` da
`first_seen_at`. La prima si sposta in avanti a ogni scansione finche le
condizioni tengono, quindi non dice quando il setup si risolve — dice quanto
sopravvive senza essere rivisto, ed e permanentemente a dieci giorni da oggi.
Solo il tetto non puo muoversi. Misurato in produzione il 2026-09-11 su 60
setup in lista: finestra scorrevole p50 9g e max 10g, tetto p50 14g e max 27g,
e il tetto e il vincolo effettivo su 9 righe su 60 — quindi il `min()` delle
due coincide quasi sempre con la scorrevole e SOTTO-RIPORTEREBBE proprio il
caso per cui questa funzione esiste.

⚠️ La data e CACHE-ONLY. Il path della lista non deve mai poter innescare una
chiamata yfinance: e la regola che `calendar_service` dichiara nel proprio
docstring e che `_next_earnings_dates_cached` gia rispettava per gli alert.
Cache fredda -> campo nullo -> nessun marcatore: sconosciuto non e «nessun
evento», ed e per questo che il campo e nullable invece di essere un booleano.
"""
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Stock, User
from app.models.stock_setup import STATUS_ACTIVE, StockSetup
from app.services import setup_service
from app.services import stock_fundamentals_service as sfs
from app.services.setup_service import _MAX_AGE_DAYS

NOW = datetime.now(UTC)
TODAY = NOW.date()


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _setup(db: Session, ticker: str, *, age_days: int) -> StockSetup:
    stock = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US")
    db.add(stock)
    db.flush()
    row = StockSetup(
        stock_id=stock.id, detector="oversold_reversal", tone="bull",
        proximity=0.8, convenience=70.0, missing="la barra deve girare",
        factors_json="{}", annotations_json="{}", status=STATUS_ACTIVE,
        shortlisted=True,
        first_seen_at=NOW - timedelta(days=age_days),
        last_seen_at=NOW,
    )
    db.add(row)
    db.commit()
    return row


@pytest.fixture(autouse=True)
def _clean_cache():
    """Il modulo dei fondamentali e un singleton di processo."""
    saved = dict(sfs._CACHE)
    sfs._CACHE.clear()
    yield
    sfs._CACHE.clear()
    sfs._CACHE.update(saved)


def _cache_earnings(ticker: str, when: date | None) -> None:
    from app.services.stock_fundamentals_service import Fundamentals
    f = Fundamentals(ticker=ticker)
    f.next_earnings_date = when.isoformat() if when else None
    sfs._CACHE[ticker] = f


def _row(client: TestClient, ticker: str) -> dict:
    r = client.get("/api/setups")
    assert r.status_code == 200, r.text
    rows = [s for s in r.json()["setups"] if s["ticker"] == ticker]
    assert rows, f"{ticker} assente dalla lista"
    return rows[0]


def test_la_finestra_e_il_tetto_dal_primo_avvistamento(client, db):
    """`pending_until` = first_seen + _MAX_AGE_DAYS, non last_seen + 10."""
    _setup(db, "AAA", age_days=14)
    got = _row(client, "AAA")["pending_until"]
    assert got == (TODAY + timedelta(days=_MAX_AGE_DAYS - 14)).isoformat()


def test_la_trimestrale_dentro_la_finestra_arriva_al_frontend(client, db):
    _setup(db, "BBB", age_days=20)          # tetto fra 8 giorni
    when = TODAY + timedelta(days=5)
    _cache_earnings("BBB", when)
    assert _row(client, "BBB")["next_earnings_date"] == when.isoformat()


def test_la_trimestrale_oltre_la_finestra_viaggia_lo_stesso(client, db):
    """Il backend riporta il FATTO; e il frontend a decidere se marcarlo.

    Due consumatori con finestre diverse — l'orizzonte di un segnale e la vita
    residua di un setup — non possono condividere un booleano precalcolato.
    """
    _setup(db, "CCC", age_days=20)
    when = TODAY + timedelta(days=55)
    _cache_earnings("CCC", when)
    assert _row(client, "CCC")["next_earnings_date"] == when.isoformat()


def test_cache_fredda_lascia_il_campo_nullo(client, db):
    """Sconosciuto non e «nessun evento», e non e mai una chiamata di rete."""
    _setup(db, "DDD", age_days=3)
    assert _row(client, "DDD")["next_earnings_date"] is None


def test_una_data_illeggibile_non_rompe_la_lista(client, db):
    _setup(db, "EEE", age_days=3)
    from app.services.stock_fundamentals_service import Fundamentals
    f = Fundamentals(ticker="EEE")
    f.next_earnings_date = "non-una-data"
    sfs._CACHE["EEE"] = f
    assert _row(client, "EEE")["next_earnings_date"] is None


def test_senza_primo_avvistamento_non_si_inventa_una_finestra():
    """Il guardiano sta sulla FUNZIONE, non sull'API.

    ⚠️ Questo caso non e raggiungibile dall'endpoint: `first_seen_at` e
    `nullable=False` con `server_default=func.now()`, quindi inserire `None`
    fa scrivere al DB l'ora corrente e la riga torna con una data. Un test che
    lo chiedesse via HTTP non proverebbe la difesa — descriverebbe uno stato
    che lo schema vieta, e fallirebbe per il motivo sbagliato.

    La firma accetta comunque `datetime | None` perche il tipo dell'API lo
    dichiara nullable, e una finestra inventata su una data assente sarebbe
    peggio di nessuna finestra.
    """
    assert setup_service.pending_until(None) is None


def test_alert_e_setup_leggono_la_stessa_data(client, db):
    """Le due pagine non possono divergere sulla stessa trimestrale.

    Il controllo e strutturale, non cosmetico: `alert_service` aveva una
    propria copia della lettura, e bastava che una delle due smettesse di
    tagliare la data a dieci caratteri perche lo stesso titolo mostrasse
    trimestrali diverse su due schermi, senza che nessuno dei due lo dicesse.
    Ora il corpo e uno solo e questo test lo pinna dal lato del comportamento.
    """
    from app.services import alert_service

    when = TODAY + timedelta(days=7)
    _cache_earnings("GGG", when)
    # La forma con l'ora attaccata e quella che yfinance restituisce davvero.
    from app.services.stock_fundamentals_service import Fundamentals
    f = Fundamentals(ticker="HHH")
    f.next_earnings_date = f"{when.isoformat()} 00:00:00"
    sfs._CACHE["HHH"] = f

    got = alert_service._next_earnings_dates_cached({"GGG", "HHH"})
    assert got == {"GGG": when, "HHH": when}

    _setup(db, "GGG", age_days=2)
    assert _row(client, "GGG")["next_earnings_date"] == got["GGG"].isoformat()
