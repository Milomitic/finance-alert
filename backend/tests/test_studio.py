"""La pagina Studio (FA-157): statistica storica con casi, finestre e base."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import MacroReleaseDate, MacroSeries, OhlcvDaily, Stock, User
from app.services import stock_fundamentals_service as sfs
from app.services import studio_service as ss

D0 = date(2024, 1, 1)


def _serie(chiusure):
    return ss.Serie([D0 + timedelta(days=i) for i in range(len(chiusure))], chiusure)


def test_una_serie_costante_rende_zero_casi_e_non_una_media():
    out = ss.dopo_movimento(_serie([100.0] * 300), sedute=5, soglia_pct=-10, orizzonte=21)
    assert out["condizione"]["casi"] == 0 and out["condizione"]["media"] is None
    assert out["base"]["media"] == 0.0 and out["differenza"] is None


def test_dopo_un_calo_contro_la_base():
    # Ogni 50 sedute un calo del 20% in 5 sedute, poi un recupero.
    c = []
    for _ in range(8):
        c += [100.0] * 40 + [96, 92, 88, 84, 80] + [85, 90, 95, 100, 100]
    out = ss.dopo_movimento(_serie(c), sedute=5, soglia_pct=-15, orizzonte=5)
    cond = out["condizione"]
    assert cond["casi"] > 0 and cond["finestre"] <= cond["casi"]
    assert cond["media"] > out["base"]["media"]
    assert cond["quota_positivi"] == 1.0


def test_la_stagionalita_conta_mesi_e_giorni():
    c = [100.0 * (1.001 ** i) for i in range(800)]
    out = ss.stagionalita(_serie(c))
    assert len(out["mesi"]) == 12 and len(out["giorni"]) == 5
    assert all(m["media"] > 0 for m in out["mesi"] if m["casi"])
    assert out["base_mesi"]["casi"] == sum(m["casi"] for m in out["mesi"])


def test_il_percorso_attorno_all_evento():
    c = [100.0] * 60 + [110.0] * 60
    evento = D0 + timedelta(days=60)
    out = ss.evento(_serie(c), [evento, evento, D0], orizzonte=3)
    assert out["a_orizzonte"]["casi"] == 1                 # doppioni e bordi fuori
    assert out["a_orizzonte"]["media"] == pytest.approx(0.10)
    medie = {p["seduta"]: p["media"] for p in out["percorso"]}
    assert medie[-1] == 0.0 and medie[0] == pytest.approx(0.10)


@pytest.fixture
def client(db):
    u = User(username="st", password_hash="x")
    s = Stock(ticker="STU", exchange="X", name="Stu")
    db.add_all([u, s])
    db.flush()
    for i in range(200):
        db.add(OhlcvDaily(stock_id=s.id, date=D0 + timedelta(days=i), open=1, high=1, low=1,
                          close=100.0 + i, volume=1))
    serie = MacroSeries(fred_series_id="CPIX", label="CPI", region="US", importance="high")
    db.add(serie)
    db.flush()
    db.add(MacroReleaseDate(series_id=serie.id, date=D0 + timedelta(days=100)))
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: u
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_gli_endpoint(client, monkeypatch):
    assert client.get("/api/studio/dopo_movimento", params={"simbolo": "stu", "soglia_pct": 1,
                                                             "sedute": 5, "orizzonte": 5}).status_code == 200
    assert client.get("/api/studio/dopo_movimento", params={"simbolo": "STU", "soglia_pct": 0}).status_code == 422
    assert client.get("/api/studio/stagionalita", params={"simbolo": "STU"}).json()["simbolo"] == "STU"
    monkeypatch.setitem(sfs._CACHE, "STU", sfs.Fundamentals(ticker="STU", earnings=[
        sfs.EarningsPoint(date=(D0 + timedelta(days=50)).isoformat(), eps_estimate=1,
                          eps_reported=1, surprise_pct=0),
        sfs.EarningsPoint(date="2030-01-01", eps_estimate=1, eps_reported=None, surprise_pct=None)]))
    r = client.get("/api/studio/evento", params={"simbolo": "STU"}).json()
    assert r["eventi"] == 1 and r["a_orizzonte"]["casi"] == 1
    r = client.get("/api/studio/evento", params={"simbolo": "STU", "tipo": "macro", "serie_macro": "CPIX"}).json()
    assert r["eventi"] == 1
    assert client.get("/api/studio/evento", params={"simbolo": "STU", "tipo": "macro"}).status_code == 422
    assert client.get("/api/studio/stagionalita", params={"simbolo": "NESSUNO"}).status_code == 404


def test_il_confronto_ha_intervallo_e_verdetto():
    """D-84: la differenza in grassetto non aveva un intervallo suo."""
    base = {"media": 0.02, "finestre": 120, "intervallo": [0.01, 0.03]}
    poche = {"media": 0.05, "finestre": 9, "intervallo": [-0.03, 0.13]}
    r = ss.confronto(poche, base)
    assert r["differenza"] == pytest.approx(0.03)
    assert r["verdetto"] == "non_concludente"           # 9 finestre su 20
    lo, hi = r["intervallo_differenza"]
    assert lo == pytest.approx(0.03 - (0.08**2 + 0.01**2) ** 0.5)
    assert hi == pytest.approx(0.03 + (0.08**2 + 0.01**2) ** 0.5)

    larga = {"media": 0.025, "finestre": 40, "intervallo": [0.0, 0.05]}
    assert ss.confronto(larga, base)["verdetto"] == "compatibile_con_zero"
    netta = {"media": 0.08, "finestre": 40, "intervallo": [0.06, 0.10]}
    assert ss.confronto(netta, base)["verdetto"] == "diversa_dalla_base"
    assert ss.confronto({"media": None}, base)["verdetto"] == "non_concludente"
