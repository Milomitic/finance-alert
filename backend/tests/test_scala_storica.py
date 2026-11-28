"""La scala storica dei piani, per chi chiude a mano (FA-206)."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Alert, PlanOutcome, Stock, User
from app.services.plan_performance_service import scala_storica


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _stock(db: Session) -> Stock:
    s = Stock(ticker="SCAL", exchange="NASDAQ", name="Scala")
    db.add(s)
    db.flush()
    return s


def _piano(db: Session, s: Stock, *, esito: str, picco: float, giorno: int = 0,
           r_mult: float = 0.0, tono: str = "bull", detector: str = "sr_flip",
           chiusa: bool = True, giorni_al_picco: int = 5) -> PlanOutcome:
    ingresso = date(2026, 1, 1) + timedelta(days=giorno)
    a = Alert(stock_id=s.id, signal_name=detector, signal_date=ingresso,
              triggered_at=datetime(2026, 1, 1, tzinfo=UTC), trigger_price=100.0,
              snapshot=json.dumps({"tone": tono}))
    db.add(a)
    db.flush()
    p = PlanOutcome(
        alert_id=a.id, stock_id=s.id, detector=detector, signal_date=ingresso, tone=tono,
        horizon_days=21, entry_date=ingresso, entry=100.0, stop=96.0, tp1=108.0, tp2=None,
        r=4.0, esito=esito, resolved_date=ingresso + timedelta(days=10), bars_to_outcome=6,
        r_multiple=r_mult, mae_r=0.3, mfe_r=1.0, tp2_reached=False, method_version="6",
        matured_at=datetime.now(UTC), legs_window_complete=chiusa,
        peak_fraction=picco, peak_date=ingresso + timedelta(days=giorni_al_picco),
        close_fraction=picco / 2, close_90_before_exit=False)
    db.add(p)
    db.flush()
    return p


def test_scala_gradini_esiti_e_restituzione(db: Session) -> None:
    s = _stock(db)
    _piano(db, s, esito="tp1", picco=1.0, r_mult=2.0, giorni_al_picco=8)
    _piano(db, s, esito="stop", picco=0.6, r_mult=-1.0, giorni_al_picco=3)    # passato da meta'
    _piano(db, s, esito="stop", picco=0.1, r_mult=-1.0, giorni_al_picco=1)
    _piano(db, s, esito="scaduto", picco=0.92, r_mult=0.5, giorni_al_picco=12)  # quasi
    # Esclusi: finestra aperta, altro verso, altro detector.
    _piano(db, s, esito="tp1", picco=1.0, chiusa=False)
    _piano(db, s, esito="tp1", picco=1.0, tono="bear")
    _piano(db, s, esito="tp1", picco=1.0, detector="gap_and_go")

    d = scala_storica(db, detector="sr_flip", tone="bull")

    assert d["piani"] == 4 and d["sufficiente"] is False and d["orizzonte"] == 21
    g = {x["soglia"]: x for x in d["gradini"]}
    assert [g[k]["toccati"] for k in (25, 50, 75, 90, 100)] == [3, 3, 2, 2, 1]
    assert g[50]["esiti"] == {"tp1": 1, "stop": 1, "scaduto": 1}
    # Al 90% senza TP1: lo scaduto. Il gradino 100 e' l'esito, non il picco.
    assert g[90]["esiti"] == {"tp1": 1, "scaduto": 1}
    assert g[100]["esiti"] == {"tp1": 1}
    assert g[50]["quota"] == pytest.approx(75.0)
    lo, hi = g[50]["intervallo"]
    assert lo < 75.0 < hi
    assert d["giorni_al_picco"] == pytest.approx(5.5)      # mediana di 1, 3, 8, 12
    assert d["stop"] == {"numero": 2, "passati_da_meta": 1, "passati_da_un_quarto": 1,
                         "picco_mediano": pytest.approx(0.35)}
    # Lo scaduto e' arrivato al 92% e ha chiuso a +0,5R = 2 su 8 di tragitto.
    assert d["scaduti"] == {"numero": 1, "picco_mediano": pytest.approx(0.92),
                            "chiusura_mediana": pytest.approx(0.25)}


def test_l_intervallo_paga_le_finestre_non_le_righe(db: Session) -> None:
    s = _stock(db)
    # Venti piani nello stesso giorno sono UNA finestra.
    for _ in range(20):
        _piano(db, s, esito="stop", picco=0.6, r_mult=-1.0)
    d = scala_storica(db, detector="sr_flip", tone="bull")
    assert d["piani"] == 20 and d["finestre"] == 1 and d["sufficiente"] is True
    lo, hi = next(x for x in d["gradini"] if x["soglia"] == 50)["intervallo"]
    assert hi - lo > 50     # una finestra non dimostra niente


def test_vuota_senza_piani_chiusi(db: Session) -> None:
    s = _stock(db)
    _piano(db, s, esito="tp1", picco=1.0, chiusa=False)
    assert scala_storica(db, detector="sr_flip", tone="bull") == {
        "detector": "sr_flip", "tone": "bull", "piani": 0, "sufficiente": False}


def test_endpoint_legge_detector_e_verso_dall_alert(client: TestClient, db: Session) -> None:
    s = _stock(db)
    p = _piano(db, s, esito="tp1", picco=1.0, r_mult=2.0)
    _piano(db, s, esito="tp1", picco=1.0, tono="bear")
    db.commit()
    r = client.get(f"/api/alerts/{p.alert_id}/scala-storica")
    assert r.status_code == 200
    assert r.json()["tone"] == "bull" and r.json()["piani"] == 1
    assert client.get("/api/alerts/999999/scala-storica").status_code == 404


def test_endpoint_none_senza_verso(client: TestClient, db: Session) -> None:
    s = _stock(db)
    a = Alert(stock_id=s.id, signal_name="sr_flip", triggered_at=datetime(2026, 1, 1, tzinfo=UTC),
              trigger_price=1.0, snapshot="{}")
    db.add(a)
    db.commit()
    r = client.get(f"/api/alerts/{a.id}/scala-storica")
    assert r.status_code == 200 and r.json() is None


def test_endpoint_per_condizione_della_scheda_esiti(client: TestClient, db: Session) -> None:
    s = _stock(db)
    _piano(db, s, esito="tp1", picco=1.0, r_mult=2.0)
    _piano(db, s, esito="stop", picco=0.6, r_mult=-1.0)
    _piano(db, s, esito="tp1", picco=1.0, tono="bear")
    db.commit()
    r = client.get("/api/alerts/plan-outcomes/scala", params={"detector": "sr_flip", "tone": "bull"})
    assert r.status_code == 200 and r.json()["piani"] == 2
    assert r.json()["stop"]["passati_da_meta"] == 1
    assert client.get("/api/alerts/plan-outcomes/scala",
                      params={"detector": "sr_flip", "tone": "x"}).status_code == 400
