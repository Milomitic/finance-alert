"""Indici e fondi di un titolo, sulla rotta che li MOSTRA.

⚠️ Il difetto che questo chiude e' la forma di FA-055. `StockOut` dichiara
`in_indices` e `in_etfs` con un default vuoto, e la rotta del dettaglio
costruiva la risposta con una `model_validate` nuda: la pagina riceveva due
liste vuote invece di un errore, e le pastiglie «S&P 500» o «fra i primi 25 di
SOXX» non comparivano su nessun titolo. Da fuori, `[]` non distingue «non e' in
nessun indice» da «questa rotta non lo riempie».

Le asserzioni guardano quindi i VALORI su ENTRAMBE le rotte: un test sulle
chiavi sarebbe verde in tutti e due i casi.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Index, OhlcvDaily, Stock, StockIndex, User


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _titolo(db: Session) -> Stock:
    s = Stock(ticker="NVDA", exchange="NASDAQ", name="Nvidia", country="US",
              sector="Information Technology")
    db.add(s)
    db.flush()
    # Il dettaglio vuole delle barre per rispondere.
    for i in range(1, 40):
        d = date(2026, 6, 1) + timedelta(days=i)
        db.add(OhlcvDaily(stock_id=s.id, date=d, open=100, high=101, low=99,
                          close=100 + i * 0.1, volume=1000))
    idx = Index(code="SP500", name="S&P 500")
    db.add(idx)
    db.flush()
    db.add(StockIndex(stock_id=s.id, index_id=idx.id))
    db.commit()
    return s


def test_il_DETTAGLIO_porta_gli_indici(client: TestClient, db: Session) -> None:
    _titolo(db)

    corpo = client.get("/api/stocks/NVDA/detail").json()

    assert [i["code"] for i in corpo["stock"]["in_indices"]] == ["SP500"]


def test_e_la_rotta_del_TITOLO_dice_la_stessa_cosa(client: TestClient, db: Session) -> None:
    """Due percorsi che riempiono a mano la stessa forma divergono, ed e'
    successo: uno lo faceva e l'altro no. Ora chiamano la stessa funzione, e
    questo test lo tiene vero."""
    _titolo(db)

    dettaglio = client.get("/api/stocks/NVDA/detail").json()["stock"]
    titolo = client.get("/api/stocks/NVDA").json()

    assert dettaglio["in_indices"] == titolo["in_indices"]
    assert dettaglio["in_etfs"] == titolo["in_etfs"]


def test_un_titolo_senza_indici_rende_liste_VUOTE_non_assenti(
    client: TestClient, db: Session,
) -> None:
    """Controllo negativo: senza, una funzione che rendesse sempre un indice
    finto supererebbe i due test sopra. E le chiavi ci sono comunque, perche'
    un consumatore che fa `.map()` su `undefined` esplode."""
    s = Stock(ticker="SOLO", exchange="NASDAQ", name="Solo Inc.", country="US")
    db.add(s)
    db.flush()
    for i in range(1, 40):
        db.add(OhlcvDaily(stock_id=s.id, date=date(2026, 6, 1) + timedelta(days=i),
                          open=100, high=101, low=99, close=100, volume=1000))
    db.commit()

    corpo = client.get("/api/stocks/SOLO/detail").json()["stock"]

    assert corpo["in_indices"] == []
    assert corpo["in_etfs"] == []
