"""Il prezzo di un segnale porta la sua valuta.

FA-045, trovata dalla verifica a schermo dell'11 settembre sul percorso
posizione -> segnale che FA-029 aveva appena reso raggiungibile: aprendo il
segnale di una posizione su ARGX.BR — titolo belga che la pagina Posizioni
mostra correttamente a `EUR 850.60` — il dialogo rendeva sei cifre in dollari.

⚠️ Misurato in produzione: **2.669 segnali su 8.905, il 30,0%**, sono su titoli
non quotati in dollari (1.084 GBP, 1.012 EUR, 545 HKD, piu una coda). Stessa
magnitudine di FA-025 (312 titoli su 1010), che era P1.

⚠️ Non era una riga sola nel frontend: il payload dell'alert non portava la
valuta affatto — verificato sul contratto, `currency` assente sia dall'alert
sia dallo snapshot — quindi il dato mancava alla radice.

La valuta viaggia GREZZA, come per lo screener: normalizzare l'etichetta
(`GBp` -> `GBP`) e compito del lato che rende, dove `displayCurrency` lo fa
gia per ogni prezzo dell'app. Due normalizzazioni divergono; una sola no.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Alert, Stock, User


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _alert(db: Session, ticker: str, currency: str | None, price: float = 100.0) -> int:
    stock = Stock(ticker=ticker, exchange="X", name=ticker, country="BE", currency=currency)
    db.add(stock)
    db.flush()
    a = Alert(
        stock_id=stock.id,
        signal_name="high52_momentum",
        trigger_price=price,
        snapshot='{"tone": "bull"}',
    )
    db.add(a)
    db.commit()
    return a.id


def test_la_lista_porta_la_valuta_del_titolo(client, db):
    _alert(db, "ARGX.BR", "EUR", 850.60)
    r = client.get("/api/alerts")
    assert r.status_code == 200, r.text
    riga = r.json()["items"][0]
    assert riga["currency"] == "EUR"
    assert riga["trigger_price"] == pytest.approx(850.60)


def test_il_dettaglio_per_id_porta_la_stessa_valuta(client, db):
    """⚠️ Le due forme non possono divergere: e la ragione per cui
    `_row_to_item` fu estratto invece di riscritto."""
    aid = _alert(db, "ARGX.BR", "EUR", 850.60)
    lista = client.get("/api/alerts").json()["items"][0]
    dettaglio = client.get(f"/api/alerts/{aid}").json()
    assert dettaglio["currency"] == lista["currency"] == "EUR"
    assert set(dettaglio) == set(lista), "le due forme hanno campi diversi"


def test_una_valuta_assente_resta_nulla_e_non_diventa_dollari(client, db):
    """La regola che `fx_service` dichiara nel proprio docstring: assumere USD
    perche il campo e vuoto e un'ipotesi presentata come un fatto."""
    _alert(db, "IGN", None)
    assert client.get("/api/alerts").json()["items"][0]["currency"] is None


def test_le_pence_viaggiano_grezze_e_le_normalizza_chi_rende(client, db):
    """⚠️ `GBp` NON si converte qui. `currency_units.major_unit_currency` possiede
    la regola dell'ETICHETTA e il frontend la applica in `displayCurrency` per
    ogni prezzo dell'app: normalizzare anche qui darebbe due proprietari alla
    stessa regola, che e il difetto che questo repo ha gia pagato tre volte."""
    _alert(db, "SHEL.L", "GBp")
    assert client.get("/api/alerts").json()["items"][0]["currency"] == "GBp"


def test_la_valuta_e_quella_del_TITOLO_non_una_costante(client, db):
    """Tre titoli, tre valute: se il campo fosse cablato passerebbe comunque
    un test su una riga sola."""
    _alert(db, "ARGX.BR", "EUR")
    _alert(db, "0005.HK", "HKD")
    _alert(db, "NVDA", "USD")
    righe = {x["ticker"]: x["currency"] for x in client.get("/api/alerts").json()["items"]}
    assert righe == {"ARGX.BR": "EUR", "0005.HK": "HKD", "NVDA": "USD"}
