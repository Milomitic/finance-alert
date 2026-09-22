"""L'esito del PIANO viaggia insieme all'alert, in lista e nel dettaglio.

Il magazzino `plan_outcomes` esisteva e si vedeva solo nella scheda Esiti:
davanti a un segnale — la schermata dove si sta davvero — non c'era modo di
sapere se il target fosse stato colpito, ne' quale gamba avesse chiuso.

⚠️ E le asserzioni guardano i VALORI, non le chiavi. E' la lezione di FA-055,
scritta nel file di parita' accanto: `AlertOut` dichiara ogni campo con un
default, quindi una rotta che non lo popola serializza `null` invece di
ometterlo — e `plan: null` letto da fuori non distingue «questo segnale non ha
un piano» da «questa rotta non lo riempie». Un test sulle chiavi sarebbe verde
in entrambi i casi.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Alert, PlanOutcome, Stock, User


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _alert(db: Session, ticker: str = "AAA") -> Alert:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=f"{ticker} Inc.", country="US")
    db.add(s)
    db.flush()
    a = Alert(
        stock_id=s.id, signal_name="sr_flip", signal_date=date(2026, 3, 1),
        triggered_at=datetime(2026, 3, 1, tzinfo=UTC), trigger_price=100.0,
        snapshot=json.dumps({"tone": "bull", "strength": 70.0}),
    )
    db.add(a)
    db.flush()
    return a


def _piano(db: Session, a: Alert, **extra) -> PlanOutcome:
    riga = PlanOutcome(
        alert_id=a.id, stock_id=a.stock_id, detector="sr_flip",
        signal_date=date(2026, 3, 1), tone="bull", horizon_days=21,
        entry_date=date(2026, 3, 2), entry=100.0, stop=96.0, tp1=108.0, tp2=112.0,
        r=4.0, esito="stop", resolved_date=date(2026, 3, 5), bars_to_outcome=3,
        r_multiple=-1.0, mae_r=1.0, mfe_r=0.4, tp2_reached=False,
        stop_hit_date=date(2026, 3, 5), tp1_hit_date=date(2026, 3, 18),
        tp2_hit_date=None, method_version="2",
        matured_at=datetime.now(UTC),
        **extra,
    )
    db.add(riga)
    db.flush()
    return riga


def test_la_lista_porta_la_gara_e_l_ORDINE_delle_gambe(client: TestClient, db: Session) -> None:
    """⚠️ Le tre date sono il punto. «Stop il 5, target il 18» vale -1R ed e'
    giusto — la posizione era chiusa — e dice anche che quello stop era troppo
    stretto e il trade aveva ragione. Senza le date quel fatto non e'
    ricavabile ne' dall'esito ne' dall'R."""
    a = _alert(db)
    _piano(db, a)
    db.commit()

    riga = client.get("/api/alerts").json()["items"][0]

    assert riga["plan"] is not None
    assert riga["plan"]["esito"] == "stop"
    assert riga["plan"]["r_multiple"] == pytest.approx(-1.0)
    assert riga["plan"]["stop_hit_date"] == "2026-03-05"
    assert riga["plan"]["tp1_hit_date"] == "2026-03-18"
    # La geometria congelata: e' quella su cui la gara e' stata corsa, non
    # quella che si ricalcolerebbe oggi.
    assert riga["plan"]["stop"] == pytest.approx(96.0)
    assert riga["plan"]["tp1"] == pytest.approx(108.0)


def test_anche_il_DETTAGLIO_lo_porta(client: TestClient, db: Session) -> None:
    """Due percorsi che costruiscono a mano la stessa forma divergono, e qui la
    divergenza sarebbe silenziosa: il frontend riceverebbe un alert senza
    piano solo quando lo apre da una posizione invece che dalla lista."""
    a = _alert(db, "BBB")
    _piano(db, a)
    db.commit()

    corpo = client.get(f"/api/alerts/{a.id}").json()

    assert corpo["plan"]["esito"] == "stop"
    assert corpo["plan"]["tp1_hit_date"] == "2026-03-18"


def test_un_alert_SENZA_piano_rende_None(client: TestClient, db: Session) -> None:
    """Controllo negativo, e non e' una formalita': senza, un serializzatore
    che rendesse sempre un oggetto vuoto — o un piano preso dall'alert
    sbagliato — supererebbe i due test qui sopra.

    ⚠️ E `None` qui e' il caso ORDINARIO, non un dato mancante: sei detector su
    diciassette non emettevano un livello di invalidazione, quindi i loro
    alert non hanno un piano da misurare e non lo avranno mai.
    """
    _alert(db, "CCC")
    db.commit()

    assert client.get("/api/alerts").json()["items"][0]["plan"] is None


def test_la_join_non_moltiplica_le_righe(client: TestClient, db: Session) -> None:
    """⚠️ Un `outerjoin` in piu' nella query della lista e' anche un modo di
    falsare conteggio e pagine. Qui non puo', perche' `ix_plan_outcomes_alert`
    e' UNICO su `alert_id` — ma e' il genere di cosa che si nota solo quando
    un totale comincia a non tornare, quindi si fissa adesso."""
    a = _alert(db, "DDD")
    _piano(db, a)
    db.commit()

    corpo = client.get("/api/alerts").json()

    assert corpo["total"] == 1
    assert len(corpo["items"]) == 1
