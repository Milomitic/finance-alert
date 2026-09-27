"""L'endpoint della confluenza (FA-107).

`compute_confluence` ha i suoi test; l'endpoint che la serve non era mai stato
eseguito. Qui si prova cio' che aggiunge lui: il limite sulla finestra e la
serializzazione di cluster e componenti fino al JSON che legge la pagina
Segnali.
"""
import json
from datetime import UTC, datetime, timedelta

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


def _oggi():
    """⚠️ Il giorno UTC, come la finestra del servizio. `date.today()` e' il
    giorno LOCALE: fra mezzanotte di Roma e mezzanotte UTC i due differiscono
    di uno, e il segnale «di due giorni fa» cade dentro la finestra di un
    giorno — questo test e' fallito cosi' la prima volta, all'01:40."""
    return datetime.now(UTC).date()


def _alert(db: Session, stock: Stock, nome: str, forza: float, tono: str, giorni_fa: int) -> Alert:
    a = Alert(
        stock_id=stock.id, trigger_price=10, signal_name=nome,
        signal_date=_oggi() - timedelta(days=giorni_fa),
        snapshot=json.dumps({"tone": tono, "strength": forza, "chain": [], "horizon": "short"}),
    )
    db.add(a)
    return a


@pytest.fixture
def dati(db: Session) -> None:
    s = Stock(ticker="AAA", exchange="NASDAQ", name="Aaa Corp", country="US")
    db.add(s)
    db.flush()
    # Le eta' sono scelte perche' ogni bordo del limite CAMBI il risultato:
    # senza limite, days=0 terrebbe solo oggi (niente cluster) e days=99
    # prenderebbe anche quello di quaranta giorni fa.
    _alert(db, s, "trend_pullback", 80, "bull", 0)
    _alert(db, s, "volume_breakout", 70, "bull", 1)
    _alert(db, s, "macd_divergence", 60, "bull", 10)
    _alert(db, s, "candle_reversal", 65, "bull", 40)
    db.commit()


def test_il_cluster_arriva_intero_fino_al_json(client, dati) -> None:
    r = client.get("/api/alerts/confluence?days=7")
    assert r.status_code == 200
    (c,) = r.json()
    assert (c["ticker"], c["name"], c["direction"], c["n_signals"]) == ("AAA", "Aaa Corp", "bull", 2)
    assert c["horizons"] == ["short"]
    comp = {x["signal_name"]: x for x in c["components"]}
    assert set(comp) == {"trend_pullback", "volume_breakout"}
    assert comp["trend_pullback"]["strength"] == 80.0
    assert comp["trend_pullback"]["tone"] == "bull"
    assert comp["trend_pullback"]["signal_date"] == _oggi().isoformat()


@pytest.mark.parametrize(
    ("days", "segnali"),
    [
        (0, 2),     # sotto il minimo vale UN giorno: oggi e ieri
        (-3, 2),
        (5, 2),
        (99, 3),    # sopra il massimo vale TRENTA: dieci giorni si', quaranta no
    ],
)
def test_la_finestra_e_limitata_fra_uno_e_trenta_giorni(client, dati, days, segnali) -> None:
    (c,) = client.get(f"/api/alerts/confluence?days={days}").json()
    assert c["n_signals"] == segnali
