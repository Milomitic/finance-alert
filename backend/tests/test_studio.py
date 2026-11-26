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


def test_la_distribuzione_accompagna_la_media():
    """F1: percentili, peggiore e migliore accanto alla media."""
    d = [date(2020, 1, 1) + timedelta(days=30 * i) for i in range(11)]
    m = ss._misura([float(i) for i in range(11)], d, 1)
    assert (m["p10"], m["mediana"], m["p90"]) == (1.0, 5.0, 9.0)
    assert (m["peggiore"], m["migliore"]) == (0.0, 10.0)


def test_l_istogramma_usa_la_stessa_griglia_per_le_due_forme():
    h = ss.istogramma([0.1, 0.2, 0.3], [0.0, 0.1, 0.2, 0.3, 0.4], fasce=4)
    assert len(h) == 4
    assert sum(r["condizione"] for r in h) == pytest.approx(1.0)
    assert sum(r["base"] for r in h) == pytest.approx(1.0)
    assert ss.istogramma([], [1.0]) == []


def test_un_effetto_che_cambia_segno_fra_le_meta_e_instabile():
    """F4: escludere lo zero nel complesso non basta se le due meta' non concordano."""
    g = [date(2010, 1, 1) + timedelta(days=i) for i in range(10)]
    base = [0.0] * 10
    cond = [0.10, 0.10, 0.10, 0.10, 0.10, -0.01, -0.01, -0.01, -0.01, -0.01]
    st = ss.stabilita(cond, g, base, g)
    assert st["concordi"] is False
    netta = {"media": 0.05, "finestre": 40, "intervallo": [0.03, 0.07]}
    zero = {"media": 0.0, "finestre": 100, "intervallo": [-0.001, 0.001]}
    assert ss.confronto(netta, zero, st)["verdetto"] == "instabile"
    assert ss.confronto(netta, zero, {"concordi": True})["verdetto"] == "diversa_dalla_base"


def test_la_correzione_per_famiglia_toglie_i_falsi_positivi():
    """F5: Benjamini-Hochberg su diciassette confronti."""
    p = [0.001, 0.04, 0.2, None] + [0.5] * 13
    passa = ss.benjamini_hochberg(p)
    assert passa[0] is True
    assert passa[1] is False   # 0,04 da solo passerebbe, nella famiglia no
    assert passa[3] is False   # non stimabile non passa mai
    assert ss.p_valore([1.0, 1.0], 2) is None   # dispersione nulla


def test_la_stagionalita_dichiara_quanti_confronti_sopravvivono():
    g = [date(2000, 1, 3) + timedelta(days=i) for i in range(800)]
    serie = ss.Serie(g, [100.0 + (i % 7) * 0.5 for i in range(800)])
    r = ss.stagionalita(serie)
    assert r["confronti"] == 17
    assert all("significativo" in m for m in r["mesi"] + r["giorni"])
    assert r["sopravvissuti"] == sum(m["significativo"] for m in r["mesi"] + r["giorni"])


def test_la_serie_di_un_mercato_si_tiene_per_il_giorno(monkeypatch):
    chiamate = []

    class B:
        def __init__(self, d, c):
            self.data, self.chiusura = d, c

    from app.services import rischio_posizioni_service as rp

    def finte(simbolo):
        chiamate.append(simbolo)
        return [B("2026-01-02", 1.0), B("2026-01-05", 2.0)]

    monkeypatch.setattr(rp, "_barre_indice", finte)
    ss._SERIE_MERCATI.clear()

    class Db:
        def execute(self, *_a, **_k):
            class R:
                def scalars(self):
                    class S:
                        def first(self):
                            return None
                    return S()
            return R()

    a = ss.serie_di(Db(), "^XYZ")
    b = ss.serie_di(Db(), "^xyz")
    assert a is b and chiamate == ["^XYZ"]
    ss._SERIE_MERCATI.clear()
