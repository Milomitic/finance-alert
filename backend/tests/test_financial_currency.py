"""La valuta dei RENDICONTI, distinta da quella di quotazione.

Ricavi, utile ed EPS del conto economico arrivano da yfinance nella valuta in
cui l'azienda rendiconta (`info["financialCurrency"]`), che per un titolo su
molti non e' quella in cui quota: SHEL.L quota in pence e rendiconta in
dollari, TSM quota in dollari e rendiconta in dollari taiwanesi. La scheda
Fondamentali stampava un `$` fisso davanti a tutte queste cifre.
"""
from dataclasses import asdict
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Stock, User
from app.services import fetch_cache_store
from app.services import stock_fundamentals_service as sfs
from app.services.stock_fundamentals_service import Fundamentals, _financial_currency

# ─── la normalizzazione ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("grezza", "attesa"),
    [
        ("USD", "USD"),
        ("TWD", "TWD"),
        ("eur", "EUR"),
        (" DKK ", "DKK"),
        # Pence: si normalizza l'ETICHETTA, come per i prezzi.
        ("GBp", "GBP"),
        ("GBX", "GBP"),
    ],
)
def test_un_codice_valido_diventa_l_etichetta(grezza, attesa):
    assert _financial_currency({"financialCurrency": grezza}) == attesa


@pytest.mark.parametrize(
    "info",
    [
        None,
        "USD",                                  # non un dict
        {},                                     # chiave assente
        {"financialCurrency": None},
        {"financialCurrency": ""},
        {"financialCurrency": "US Dollar"},     # non un codice
        {"financialCurrency": "US$"},
        {"financialCurrency": 840},             # numerico ISO, non il codice
    ],
)
def test_cio_che_non_e_un_codice_e_ignoto_non_dollari(info):
    """⚠️ Ignota resta ignota: un ripiego su USD sarebbe un'ipotesi
    presentata come un fatto."""
    assert _financial_currency(info) is None


def test_la_valuta_di_quotazione_non_c_entra():
    """Il caso per cui il campo esiste: quota in pence, rendiconta in
    dollari. Il controllo negativo sta nell'asserzione stessa — leggere
    `currency` darebbe GBP."""
    assert _financial_currency({"currency": "GBp", "financialCurrency": "USD"}) == "USD"


# ─── dentro il fetch ────────────────────────────────────────────────────


def test_fetch_fresh_la_legge_da_info(monkeypatch):
    raw = {
        "info": {
            "currency": "GBp",
            "financialCurrency": "USD",
            "trailingPE": 12.0,
            "website": "https://www.shell.com",
        },
    }
    monkeypatch.setattr(sfs, "_yf_fetch_with_retry", lambda t: raw)
    monkeypatch.setattr(sfs, "_throttle_upstream_fetch", lambda: None)

    f = sfs._fetch_fresh("SHEL.L")

    assert f.financial_currency == "USD"


def test_fetch_fresh_senza_info_resta_ignota(monkeypatch):
    monkeypatch.setattr(sfs, "_yf_fetch_with_retry", lambda t: {})
    monkeypatch.setattr(sfs, "_throttle_upstream_fetch", lambda: None)

    assert sfs._fetch_fresh("AAPL").financial_currency is None


# ─── la cache L2 ────────────────────────────────────────────────────────


def test_il_campo_sopravvive_al_giro_in_l2():
    f = Fundamentals(ticker="TSM", financial_currency="TWD")
    assert fetch_cache_store._fundamentals_from_dict(asdict(f)).financial_currency == "TWD"


def test_una_riga_l2_scritta_prima_del_campo_legge_ignota():
    """⚠️ Il campo e' entrato SENZA alzare `_FUNDAMENTALS_SCHEMA_VERSION`, di
    proposito: la versione nuova avrebbe reso ogni riga L2 una mancanza, cioe'
    fondamentali assenti per i detector della scansione (che leggono solo la
    cache) e un ri-scaricamento dell'intero universo alla prima ricomposizione
    dei punteggi. Per un'ETICHETTA non vale quel prezzo: una riga vecchia dice
    «ignota» — il frontend mostra il numero nudo — finche' il TTL di sette
    giorni o il pulsante di aggiornamento della scheda non la riscrivono."""
    vecchio = {"ticker": "AAPL", "annual": [], "quarterly": [], "earnings": []}
    f = fetch_cache_store._fundamentals_from_dict(vecchio)
    assert f.financial_currency is None
    assert fetch_cache_store._FUNDAMENTALS_SCHEMA_VERSION == 7


# ─── l'API ──────────────────────────────────────────────────────────────


@pytest.fixture
def client(db: Session):
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_l_endpoint_la_espone(client: TestClient, db: Session):
    db.add(Stock(ticker="SHEL_TEST", exchange="LSE", name="Shell", country="UK", currency="GBP"))
    db.commit()
    with patch(
        "app.api.stocks.stock_fundamentals_service.get_fundamentals",
        return_value=Fundamentals(ticker="SHEL_TEST", financial_currency="USD"),
    ):
        r = client.get("/api/stocks/SHEL_TEST/fundamentals")
    assert r.status_code == 200, r.text
    assert r.json()["financial_currency"] == "USD"


def test_l_endpoint_la_dice_ignota_quando_lo_e(client: TestClient, db: Session):
    db.add(Stock(ticker="OLD_TEST", exchange="NYSE", name="Old", country="US", currency="USD"))
    db.commit()
    with patch(
        "app.api.stocks.stock_fundamentals_service.get_fundamentals",
        return_value=Fundamentals(ticker="OLD_TEST"),
    ):
        r = client.get("/api/stocks/OLD_TEST/fundamentals")
    assert r.status_code == 200, r.text
    # Presente e nulla, non assente e non «USD» per difetto.
    assert "financial_currency" in r.json()
    assert r.json()["financial_currency"] is None
