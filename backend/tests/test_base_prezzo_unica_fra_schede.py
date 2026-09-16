"""La scheda Analyst e la scheda Stock Score partono dallo STESSO prezzo.

Sulla pagina di un titolo il target consenso era identico nelle due schede
(67,43) e l'upside no: la Stock Score lo calcolava sull'ultima chiusura in
`ohlcv_daily` (55,41 del 14/09), la Analyst su `price_target.current` di
yfinance — 62,09, vecchio quanto la cache dei fondamentali (TTL 7 giorni).
Due percentuali diverse dello stesso target, a pochi centimetri, e nessuna
delle due sbagliata presa da sola.

`test_upside_base_price.py` aveva chiuso meta' del difetto: ogni upside
dichiara la propria base. Qui si chiude l'altra meta': dove la base e'
DISPONIBILE, le due schede usano la stessa, e il proprietario e' uno solo
(`price_base.last_close`). La chiusura memorizzata non ha breaker e non puo'
essere STALE, quindi imporla non introduce la dipendenza dal prezzo live che
quel test giustamente rifiutava.
"""
from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.api.scores import _quality_extras
from app.main import app
from app.models import OhlcvDaily, Stock, User
from app.services.stock_fundamentals_service import (
    AnalystPriceTarget,
    Fundamentals,
)

TARGET = 67.43
PREZZO_YFINANCE_VECCHIO = 62.09
ULTIMA_CHIUSURA = 55.41


@pytest.fixture
def client(db: Session):
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _titolo(db: Session, *, con_barre: bool = True) -> Stock:
    s = Stock(ticker="BASE_T", exchange="NYSE", name="Base Test", country="US")
    db.add(s)
    db.commit()
    if con_barre:
        for giorno, chiusura in ((date(2026, 9, 11), 57.0), (date(2026, 9, 14), ULTIMA_CHIUSURA)):
            db.add(OhlcvDaily(
                stock_id=s.id, date=giorno, open=chiusura, high=chiusura,
                low=chiusura, close=chiusura, volume=1000,
            ))
        db.commit()
    return s


def _fondamentali() -> Fundamentals:
    return Fundamentals(
        ticker="BASE_T",
        price_target=AnalystPriceTarget(
            current=PREZZO_YFINANCE_VECCHIO, low=50.0, mean=TARGET,
            median=68.0, high=80.0,
        ),
    )


def _leggi_analyst(client: TestClient) -> dict:
    with patch(
        "app.api.stocks.stock_fundamentals_service.get_fundamentals",
        return_value=_fondamentali(),
    ):
        r = client.get("/api/stocks/BASE_T/fundamentals")
    assert r.status_code == 200, r.text
    return r.json()["price_target"]


def test_le_due_schede_usano_la_stessa_base(client: TestClient, db: Session) -> None:
    stock = _titolo(db)
    pt = _leggi_analyst(client)

    with patch(
        "app.api.scores.stock_fundamentals_service.get_fundamentals_cached",
        return_value=_fondamentali(),
    ):
        extras = _quality_extras(db, stock)

    base_score = extras["analyst"]["upside_base_price"]
    assert pt["current"] == base_score == ULTIMA_CHIUSURA
    # E la base dichiara la sua data, in entrambe.
    assert pt["current_as_of"] == extras["analyst"]["upside_base_as_of"] == "2026-09-14"


def test_non_e_il_prezzo_di_yfinance(client: TestClient, db: Session) -> None:
    # Il controllo che distingue: se l'endpoint restituisse ancora
    # `pt.current`, questo numero sarebbe 62,09.
    _titolo(db)
    assert _leggi_analyst(client)["current"] != PREZZO_YFINANCE_VECCHIO


def test_senza_barre_resta_il_prezzo_della_fonte_senza_data(
    client: TestClient, db: Session,
) -> None:
    # Un titolo appena aggiunto non ha ancora barre: meglio la base di yfinance
    # che nessuna, ma senza data — non e' una chiusura nostra e non la finge.
    _titolo(db, con_barre=False)
    pt = _leggi_analyst(client)
    assert pt["current"] == PREZZO_YFINANCE_VECCHIO
    assert pt["current_as_of"] is None
