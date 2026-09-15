"""Da quale setup e' nato un alert (FA-066).

Il collegamento esiste da FA-061 — `StockSetup.converted_alert_id` — ma usciva
solo dalla lista dei setup, che e' paginata a cinquanta righe. Il dettaglio
titolo deve poter dire «questo segnale era in formazione dal 3 agosto» senza
dipendere da quale pagina di un'altra lista contenga l'episodio.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Alert, OhlcvDaily, Stock, StockSetup, User
from app.services import alert_service


@pytest.fixture
def client(db):
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _titolo(db) -> Stock:
    s = Stock(ticker="ORIG", exchange="NASDAQ", name="Origine Inc", country="US")
    db.add(s)
    db.flush()
    # Il dettaglio titolo vuole barre per rendere il payload.
    for i in range(1, 40):
        db.add(OhlcvDaily(stock_id=s.id, date=date(2026, 7, 1) + timedelta(days=i),
                          open=10, high=11, low=9, close=10, volume=1000))
    db.flush()
    return s


def _alert(db, s: Stock, giorno: date = date(2026, 8, 10)) -> Alert:
    a = Alert(
        stock_id=s.id, trigger_price=10.0, signal_date=giorno,
        signal_name="trend_pullback", snapshot=json.dumps({"tone": "bull"}),
        triggered_at=datetime.combine(giorno + timedelta(days=1), datetime.min.time(), UTC),
    )
    db.add(a)
    db.flush()
    return a


def _setup(db, s: Stock, *, alert: Alert | None, dal: datetime, preavviso: int | None = None,
           detector: str = "trend_pullback") -> StockSetup:
    r = StockSetup(
        stock_id=s.id, detector=detector, tone="bull", proximity=0.8, convenience=75.0,
        missing="il prezzo deve tornare sopra la EMA50",
        status="converted" if alert else "active",
        first_seen_at=dal, last_seen_at=dal,
        resolved_at=dal + timedelta(days=preavviso or 1) if alert else None,
        converted_alert_id=alert.id if alert else None, lead_days=preavviso,
    )
    db.add(r)
    db.flush()
    return r


def test_la_lista_dice_da_quale_setup_e_nato(client, db):
    s = _titolo(db)
    a = _alert(db, s)
    st = _setup(db, s, alert=a, dal=datetime(2026, 8, 4, tzinfo=UTC), preavviso=6)
    db.commit()

    [riga] = client.get("/api/alerts?ticker=ORIG").json()["items"]

    origine = riga["setup_origin"]
    assert origine["setup_id"] == st.id
    assert origine["detector"] == "trend_pullback"
    assert origine["lead_days"] == 6
    assert origine["first_seen_at"].startswith("2026-08-04")


def test_un_alert_non_convertito_non_ne_riceve_uno_per_somiglianza(client, db):
    """⚠️ Il controllo negativo che conta: un setup ATTIVO sullo stesso titolo e
    lo stesso detector ha tutta l'aria di essere l'origine, e non lo e'. Il
    collegamento e' la colonna, mai un'inferenza su titolo e detector."""
    s = _titolo(db)
    _alert(db, s)
    _setup(db, s, alert=None, dal=datetime(2026, 8, 4, tzinfo=UTC))
    db.commit()

    [riga] = client.get("/api/alerts?ticker=ORIG").json()["items"]

    assert riga["setup_origin"] is None


def test_le_tre_rotte_concordano(client, db):
    s = _titolo(db)
    a = _alert(db, s)
    _setup(db, s, alert=a, dal=datetime(2026, 8, 4, tzinfo=UTC), preavviso=6)
    db.commit()

    dalla_lista = client.get("/api/alerts?ticker=ORIG").json()["items"][0]["setup_origin"]
    dal_singolo = client.get(f"/api/alerts/{a.id}").json()["setup_origin"]
    dal_titolo = client.get("/api/stocks/ORIG/detail").json()["alerts_history"][0]["setup_origin"]

    assert dalla_lista is not None
    assert dal_singolo == dalla_lista
    assert dal_titolo == dalla_lista


def test_due_episodi_nello_stesso_alert_tiene_il_preavviso_piu_lungo(db):
    s = _titolo(db)
    a = _alert(db, s)
    tardi = _setup(db, s, alert=a, dal=datetime(2026, 8, 8, tzinfo=UTC), preavviso=2,
                   detector="oversold_reversal")
    presto = _setup(db, s, alert=a, dal=datetime(2026, 8, 1, tzinfo=UTC), preavviso=9)
    db.commit()

    origine = alert_service._setup_origins(db, [a.id])[a.id]

    assert origine["setup_id"] == presto.id
    assert origine["setup_id"] != tardi.id


def test_una_query_per_pagina_non_una_per_riga(db):
    s = _titolo(db)
    for giorno in (date(2026, 8, 3), date(2026, 8, 5), date(2026, 8, 7)):
        a = _alert(db, s, giorno)
        _setup(db, s, alert=a, dal=datetime.combine(giorno - timedelta(days=3),
                                                    datetime.min.time(), UTC), preavviso=3)
    db.commit()

    istruzioni: list[str] = []

    def conta(conn, cursor, statement, *args):
        if "stock_setups" in statement:
            istruzioni.append(statement)

    motore = db.get_bind()
    event.listen(motore, "before_cursor_execute", conta)
    try:
        items, _, _ = alert_service.list_alerts(db, limit=50, offset=0, ticker="ORIG")
    finally:
        event.remove(motore, "before_cursor_execute", conta)

    # Il pavimento: tre alert, tre origini — altrimenti «una query» sarebbe vero
    # anche di una funzione che non ne cerca nessuna.
    assert sum(1 for i in items if i["setup_origin"]) == 3
    assert len(istruzioni) == 1
