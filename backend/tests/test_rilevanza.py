"""La rilevanza (FA-113): prima le posizioni aperte, poi i preferiti, poi il resto."""
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Alert, Position, Stock, User
from app.models.preferito import Preferito
from app.services import alert_service, rilevanza_service


@pytest.fixture
def catalogo(db: Session) -> dict[str, Stock]:
    """Quattro titoli e un alert ciascuno. Il piu' RECENTE e' su un titolo che
    nessuno segue: con l'ordine per nascita starebbe in cima."""
    out = {}
    base = datetime(2026, 9, 28, 12, tzinfo=UTC)
    for i, t in enumerate(["NESSUNO", "PREF", "POS", "CHIUSA"]):
        s = Stock(ticker=t, exchange="X", name=t)
        db.add(s)
        db.flush()
        out[t] = s
        db.add(Alert(
            stock_id=s.id, signal_name="volume_breakout", trigger_price=10,
            snapshot=json.dumps({"tone": "bull"}),
            emitted_at=base - timedelta(hours=10 * i), triggered_at=base,
        ))
    db.add(Preferito(stock_id=out["PREF"].id))
    db.add(Position(stock_id=out["POS"].id, entry_price=Decimal("10")))
    db.add(Position(stock_id=out["CHIUSA"].id, entry_price=Decimal("10"),
                    closed_at=base))
    db.commit()
    return out


def test_i_titoli_rilevanti(db: Session, catalogo) -> None:
    ril = rilevanza_service.titoli_rilevanti(db)
    assert ril == {catalogo["PREF"].id: "preferito", catalogo["POS"].id: "posizione"}


def test_una_posizione_vince_su_un_preferito(db: Session, catalogo) -> None:
    db.add(Preferito(stock_id=catalogo["POS"].id))
    db.commit()
    assert rilevanza_service.titoli_rilevanti(db)[catalogo["POS"].id] == "posizione"


def test_la_lista_per_rilevanza(db: Session, catalogo) -> None:
    items, _, _ = alert_service.list_alerts(db, sort_by="rilevanza", sort_dir="desc")
    assert [i["ticker"] for i in items] == ["POS", "PREF", "NESSUNO", "CHIUSA"]
    assert [i["rilevanza"] for i in items] == ["posizione", "preferito", None, None]


def test_dentro_il_gruppo_resta_la_piu_recente_prima(db: Session, catalogo) -> None:
    """Il peso e' un gruppo, non un ordine: fra i titoli non seguiti vale la
    nascita, piu' recente prima — anche col verso invertito."""
    items, _, _ = alert_service.list_alerts(db, sort_by="rilevanza", sort_dir="asc")
    assert [i["ticker"] for i in items] == ["NESSUNO", "CHIUSA", "PREF", "POS"]


def test_solo_i_miei_titoli(db: Session, catalogo) -> None:
    items, totale, _ = alert_service.list_alerts(db, solo_rilevanti=True)
    assert ({i["ticker"] for i in items}, totale) == ({"POS", "PREF"}, 2)


def test_la_rilevanza_viaggia_anche_con_l_ordine_per_nascita(db: Session, catalogo) -> None:
    items, _, _ = alert_service.list_alerts(db)
    assert {i["ticker"]: i["rilevanza"] for i in items}["PREF"] == "preferito"


@pytest.fixture
def client(db: Session):
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_l_api_accetta_rilevanza_e_il_filtro(client, catalogo) -> None:
    r = client.get("/api/alerts?sort_by=rilevanza&solo_rilevanti=true")
    assert r.status_code == 200
    assert [(i["ticker"], i["rilevanza"]) for i in r.json()["items"]] == [
        ("POS", "posizione"), ("PREF", "preferito"),
    ]
