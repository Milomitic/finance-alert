"""I titoli preferiti (FA-112)."""
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Stock, User
from app.models.preferito import Preferito
from app.services import preferiti_service as pref


@pytest.fixture
def titoli(db: Session) -> dict[str, Stock]:
    out = {}
    for t, valuta in [("AAPL", "USD"), ("ENI.MI", "EUR"), ("0700.HK", "HKD")]:
        s = Stock(ticker=t, exchange="X", name=f"{t} nome", currency=valuta)
        db.add(s)
        out[t] = s
    db.commit()
    return out


@pytest.fixture
def client(db: Session):
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_aggiungere_due_volte_non_duplica(db: Session, titoli) -> None:
    primo = pref.aggiungi(db, "AAPL")
    secondo = pref.aggiungi(db, "AAPL")
    assert primo[1] == secondo[1]  # la data d'aggiunta resta quella della prima volta
    assert len(db.execute(select(Preferito)).scalars().all()) == 1


def test_un_ticker_fuori_catalogo_non_e_un_preferito(db: Session, titoli) -> None:
    assert pref.aggiungi(db, "NONESISTE") is None
    assert pref.togli(db, "NONESISTE") is False


def test_la_lista_resta_nell_ordine_d_aggiunta(db: Session, titoli) -> None:
    base = datetime(2026, 9, 1, tzinfo=UTC)
    for i, t in enumerate(["ENI.MI", "AAPL", "0700.HK"]):
        db.add(Preferito(stock_id=titoli[t].id, aggiunto_il=base + timedelta(hours=i)))
    db.commit()
    assert [s.ticker for s, _, _ in pref.elenco(db)] == ["ENI.MI", "AAPL", "0700.HK"]
    assert pref.stock_ids(db) == {s.id for s in titoli.values()}


def test_togliere_e_idempotente(db: Session, titoli) -> None:
    pref.aggiungi(db, "AAPL")
    assert pref.togli(db, "AAPL") is True
    assert pref.togli(db, "AAPL") is False
    assert pref.elenco(db) == []


def test_un_titolo_tolto_dal_catalogo_esce_dai_preferiti(db: Session, titoli) -> None:
    """ON DELETE CASCADE: una potatura del catalogo non lascia stelle orfane."""
    pref.aggiungi(db, "AAPL")
    db.delete(titoli["AAPL"])
    db.commit()
    assert db.execute(select(Preferito)).scalars().all() == []


def test_l_api_aggiunge_elenca_e_toglie(client, titoli) -> None:
    r = client.put("/api/preferiti/ENI.MI")
    assert r.status_code == 200
    assert (r.json()["ticker"], r.json()["currency"]) == ("ENI.MI", "EUR")
    assert client.put("/api/preferiti/0700.HK").status_code == 200
    assert [p["ticker"] for p in client.get("/api/preferiti").json()] == ["ENI.MI", "0700.HK"]

    assert client.delete("/api/preferiti/ENI.MI").status_code == 204
    assert client.delete("/api/preferiti/ENI.MI").status_code == 204
    assert [p["ticker"] for p in client.get("/api/preferiti").json()] == ["0700.HK"]


def test_l_api_rifiuta_un_ticker_sconosciuto(client, titoli) -> None:
    r = client.put("/api/preferiti/NONESISTE")
    assert r.status_code == 404
