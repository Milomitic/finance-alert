"""Un segnale raggiungibile per id.

Nasce per le posizioni: `Position.alert_id` arriva gia al frontend e non porta
da nessuna parte, perche la lista alert e paginata e il segnale che ha aperto
una posizione due mesi fa non e nella pagina che si sta guardando.
"""
from datetime import UTC, datetime

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


def _seed(db: Session) -> Alert:
    stock = Stock(ticker="AAPL", exchange="NASDAQ", name="Apple")
    db.add(stock)
    db.commit()
    a = Alert(
        signal_name="volume_breakout",
        stock_id=stock.id,
        trigger_price=187.35,
        snapshot='{"strength": 71.0, "tone": "bull"}',
    )
    db.add(a)
    db.commit()
    return a


def test_returns_the_alert(client: TestClient, db: Session) -> None:
    a = _seed(db)

    resp = client.get(f"/api/alerts/{a.id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == a.id
    assert body["ticker"] == "AAPL"
    assert body["rule_kind"] == "signal:volume_breakout"
    assert body["trigger_price"] == pytest.approx(187.35)
    # La catena e la Forza sono l'intero motivo per cui si apre il dettaglio:
    # un endpoint che restituisse tutto tranne lo snapshot passerebbe ogni
    # altra asserzione qui sopra.
    assert body["snapshot"]["strength"] == 71.0


def test_missing_id_is_404(client: TestClient, db: Session) -> None:
    _seed(db)

    assert client.get("/api/alerts/999999").status_code == 404


def test_forma_identica_a_quella_della_lista(client: TestClient, db: Session) -> None:
    """Il campo per campo, non un sottoinsieme.

    I due percorsi costruivano il dict a mano, ognuno per conto proprio. Una
    divergenza li sarebbe silenziosa: il dialogo mostrerebbe meno cose quando
    lo si apre da una posizione invece che dalla lista, e nessun test che
    guardi un solo lato potrebbe accorgersene. Da qui `_row_to_item`.
    """
    a = _seed(db)

    uno = client.get(f"/api/alerts/{a.id}").json()
    dalla_lista = next(
        i for i in client.get("/api/alerts").json()["items"] if i["id"] == a.id
    )

    assert uno == dalla_lista


def test_un_segnale_archiviato_resta_raggiungibile(
    client: TestClient, db: Session
) -> None:
    """⚠️ Deliberato, e opposto al default della lista.

    Un segnale archiviato ha comunque generato la posizione che si sta
    guardando. Nasconderlo qui riprodurrebbe in piccolo il difetto che il
    magazzino esiti ha gia pagato in grande — filtrare su un campo che scrive
    l'UTENTE: l'archiviazione traccia l'eta, non la rilevanza, e le posizioni
    piu vecchie sono esattamente quelle il cui segnale e archiviato.
    """
    a = _seed(db)
    a.archived_at = datetime.now(UTC)
    db.commit()

    # La lista, col suo default, non lo mostra.
    assert client.get("/api/alerts").json()["total"] == 0
    # L'endpoint per id si.
    assert client.get(f"/api/alerts/{a.id}").status_code == 200


@pytest.mark.parametrize(
    "path",
    ["/api/alerts/scan-status", "/api/alerts/signal-calibration"],
)
def test_le_rotte_letterali_non_vengono_ingoiate(
    client: TestClient, db: Session, path: str
) -> None:
    """⚠️ Il regresso che questo endpoint puo causare non e sul suo endpoint.

    FastAPI prova le rotte nell'ordine di dichiarazione. Un `{alert_id}`
    tipizzato `int` dichiarato prima delle rotte letterali di questo router
    intercetta `scan-status` e `signal-calibration`, tenta di convertirle in
    numero e risponde **422** — su endpoint che funzionavano e che nessuno ha
    toccato. La barra di scansione smetterebbe di aggiornarsi senza che il
    codice della scansione sia cambiato.

    Il 422 e la firma esatta del difetto, quindi e quello che si asserisce.
    """
    resp = client.get(path)

    assert resp.status_code != 422, resp.text
    assert resp.status_code == 200
