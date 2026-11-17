"""La dashboard riceve la valuta di quotazione accanto a ogni prezzo (C-20).

Prima scriveva «$» davanti a ogni prezzo dei movers, dei massimi a 52
settimane e dei target degli analisti, e un terzo del catalogo non e' in
dollari: un titolo di Londra usciva in dollari. La valuta arriva nell'unita'
maggiore (GBp -> GBP), e una valuta sconosciuta resta None: il frontend
mostra allora il numero nudo, mai un dollaro inventato.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import OhlcvDaily, Stock, User
from app.services import analyst_actions_feed, market_stats_service
from app.services.analyst_actions_feed import AnalystActionFeedItem
from tests.test_market_stats_service import _seed_basic


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_azioni_analisti_portano_la_valuta_in_unita_maggiore(
    client: TestClient, db: Session, monkeypatch
) -> None:
    for t, valuta in (("BP.L", "GBp"), ("ADBE", "USD"), ("ZZZ", None)):
        s = Stock(ticker=t, exchange="X", name=t, currency=valuta)
        db.add(s)
        db.commit()
        db.add(OhlcvDaily(stock_id=s.id, date=date(2026, 6, 1), open=1, high=1, low=1, close=1, volume=1))
    db.commit()
    voci = [
        AnalystActionFeedItem(
            ticker=t, name=t, date="2026-06-12", firm="F", to_grade="Buy", from_grade="Hold",
            action="up", current_price_target=10.0, prior_price_target=9.0,
            price_target_action="Raises", from_news=False,
        )
        for t in ("BP.L", "ADBE", "ZZZ")
    ]
    monkeypatch.setattr(analyst_actions_feed, "recent_actions", lambda **kw: voci)

    righe = {r["ticker"]: r for r in client.get("/api/dashboard/analyst-actions").json()}
    assert righe["BP.L"]["currency"] == "GBP"
    assert righe["ADBE"]["currency"] == "USD"
    assert righe["ZZZ"]["currency"] is None


def test_i_movers_portano_la_valuta_del_titolo(client: TestClient, db: Session) -> None:
    _seed_basic(db, n_stocks=3, n_bars=210)
    for s in db.query(Stock).all():
        s.currency = "EUR"
    db.commit()
    market_stats_service.recompute_snapshot(db)

    movers = client.get("/api/dashboard/market-summary").json()["movers"]
    righe = [r for blocco in movers.values() if isinstance(blocco, list) for r in blocco]
    assert righe, "nessun mover reso: il test sarebbe vero di niente"
    assert {r["currency"] for r in righe} == {"EUR"}


