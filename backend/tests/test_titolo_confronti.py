"""Il dettaglio titolo a confronto (FA-156): pari, trimestrali, punteggio, nota."""
import json
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import OhlcvDaily, ScoreHistory, Stock, StockScore, User
from app.services import fx_service
from app.services import stock_fundamentals_service as sfs
from app.services import titolo_confronti_service as tc

D0 = date(2026, 3, 2)


def _titolo(db, ticker, cap, industria="Semis", settore="Tech", valuta="USD", paese="US"):
    s = Stock(ticker=ticker, exchange="X", name=ticker, market_cap=cap, industry=industria,
              sector=settore, currency=valuta, country=paese)
    db.add(s)
    db.flush()
    return s


def _barre(db, s, chiusure):
    for i, c in enumerate(chiusure):
        db.add(OhlcvDaily(stock_id=s.id, date=D0 + timedelta(days=i), open=c, high=c, low=c,
                          close=c, volume=1))


# ─── Pari ─────────────────────────────────────────────────────────────────

def test_i_pari_sono_i_piu_vicini_per_capitalizzazione_in_dollari(db, monkeypatch):
    monkeypatch.setattr(fx_service, "to_usd", lambda v, c: v / 1000 if c == "KRW" else v)
    mio = _titolo(db, "MIO", 100e9)
    for t, cap in [("VICINO", 90e9), ("GRANDE", 3000e9), ("PICCOLO", 1e9), ("MEDIO", 200e9)]:
        _titolo(db, t, cap)
    _titolo(db, "COREANO", 95_000e9, valuta="KRW")   # 95 mld USD: vicino, non enorme
    _titolo(db, "ALTRA", 100e9, industria="Banks")
    db.add(StockScore(stock_id=mio.id, composite=61.0, risk_tier="moderate",
                      computed_at=datetime.now(UTC), breakdown="{}"))
    db.commit()
    out = tc.pari(db, "MIO")
    assert out["base"] == "industria" and out["gruppo"] == "Semis"
    tick = [r["ticker"] for r in out["righe"]]
    assert tick[0] == "MIO" and tick[1:3] == ["COREANO", "VICINO"]
    assert "ALTRA" not in tick
    assert out["righe"][0]["qualita"] == 61.0


def test_con_pochi_pari_nell_industria_si_allarga_al_settore(db):
    _titolo(db, "SOLO", 10e9, industria="Rara")
    _titolo(db, "UNO", 10e9, industria="Altra")
    db.commit()
    out = tc.pari(db, "SOLO")
    assert out["base"] == "settore" and [r["ticker"] for r in out["righe"]] == ["SOLO", "UNO"]
    assert tc.pari(db, "NESSUNO") is None


def test_il_rendimento_a_tre_mesi(db):
    s = _titolo(db, "R3M", 1e9)
    _barre(db, s, [100.0] + [110.0] * 63)
    db.commit()
    assert tc._rendimento_3m(db, s.id) == pytest.approx(0.10)
    t = _titolo(db, "CORTO", 1e9)
    _barre(db, t, [1.0] * 10)
    db.commit()
    assert tc._rendimento_3m(db, t.id) is None


# ─── Reazioni alle trimestrali ────────────────────────────────────────────

def _con_trimestrali(monkeypatch, ticker, punti):
    f = sfs.Fundamentals(ticker=ticker, earnings=[
        sfs.EarningsPoint(date=d, eps_estimate=1.0, eps_reported=1.1, surprise_pct=s, time_utc=o)
        for d, s, o in punti])
    monkeypatch.setitem(sfs._CACHE, ticker, f)


def test_la_seduta_di_reazione_segue_l_ora_dell_annuncio(db, monkeypatch):
    s = _titolo(db, "TRIM", 1e9)
    # Giorni 0..9: 100, 100, 100, 110 (giorno 3), 121 (giorno 4), poi fermo.
    _barre(db, s, [100, 100, 100, 110, 121, 121, 121, 121, 121, 121])
    db.commit()
    g3 = (D0 + timedelta(days=3)).isoformat()
    _con_trimestrali(monkeypatch, "TRIM", [(g3, 5.0, "12:00")])    # prima dell'apertura
    r = tc.reazioni_trimestrali(db, "TRIM")["righe"][0]
    assert (r["quando"], r["reazione_pct"]) == ("pre", pytest.approx(0.10))
    assert r["cinque_sedute_pct"] == pytest.approx(0.21)
    _con_trimestrali(monkeypatch, "TRIM", [(g3, 5.0, "21:30")])    # dopo la chiusura
    assert tc.reazioni_trimestrali(db, "TRIM")["righe"][0]["reazione_pct"] == pytest.approx(0.10)
    _con_trimestrali(monkeypatch, "TRIM", [(g3, 5.0, None)])       # ora ignota: due sedute
    r = tc.reazioni_trimestrali(db, "TRIM")["righe"][0]
    assert r["due_sedute"] is True and r["reazione_pct"] == pytest.approx(0.21)


def test_trimestrali_senza_utile_o_senza_barre_non_entrano(db, monkeypatch):
    s = _titolo(db, "VUOTO", 1e9)
    _barre(db, s, [100, 101, 102])
    db.commit()
    f = sfs.Fundamentals(ticker="VUOTO", earnings=[
        sfs.EarningsPoint(date=(D0 + timedelta(days=1)).isoformat(), eps_estimate=1.0,
                          eps_reported=None, surprise_pct=None),
        sfs.EarningsPoint(date="2030-01-01", eps_estimate=1.0, eps_reported=1.0, surprise_pct=0.0),
        sfs.EarningsPoint(date="nonsense", eps_estimate=1.0, eps_reported=1.0, surprise_pct=0.0),
    ])
    monkeypatch.setitem(sfs._CACHE, "VUOTO", f)
    assert tc.reazioni_trimestrali(db, "VUOTO") == {"righe": [], "mediana_assoluta_pct": None}


# ─── Variazione del punteggio ────────────────────────────────────────────

def _istantanea(db, s, giorno, composite, pilastri):
    db.add(ScoreHistory(stock_id=s.id, lens="qualita", captured_on=giorno,
                        composite=composite, pillars=json.dumps(pilastri)))


def test_il_pilastro_che_ha_mosso_il_composito(db):
    s = _titolo(db, "PUNT", 1e9)
    oggi = date(2026, 11, 15)
    base = {"profitability": 50, "sustainability": 50, "growth": 50, "value": 50, "sentiment": 50}
    _istantanea(db, s, oggi - timedelta(days=95), 50.0, base)
    _istantanea(db, s, oggi - timedelta(days=31), 50.0, base)
    _istantanea(db, s, oggi, 52.8, {**base, "growth": 60})
    db.commit()
    out = tc.variazione_punteggio(db, "PUNT", oggi=oggi)
    f30 = out["finestre"][0]
    assert (f30["giorni"], f30["delta"]) == (30, pytest.approx(2.8))
    assert f30["contributi"][0]["pilastro"] == "growth"
    assert f30["contributi"][0]["contributo"] == pytest.approx(2.8)     # 0,28 x 10
    assert f30["altro"] == pytest.approx(0.0)
    assert [f["giorni"] for f in out["finestre"]] == [30, 90]


def test_senza_storia_niente_finestre(db):
    _titolo(db, "NUOVO", 1e9)
    db.commit()
    assert tc.variazione_punteggio(db, "NUOVO") == {"finestre": []}


# ─── Gli endpoint e la nota ──────────────────────────────────────────────

@pytest.fixture
def client(db):
    user = User(username="u", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_gli_endpoint_di_lettura(db, client):
    _titolo(db, "API", 1e9)
    db.commit()
    for percorso in ("pari", "reazioni-trimestrali", "variazione-punteggio"):
        assert client.get(f"/api/stocks/API/{percorso}").status_code == 200
        assert client.get(f"/api/stocks/NONC/{percorso}").status_code == 404


def test_la_nota_si_scrive_si_rilegge_e_si_toglie(db, client):
    _titolo(db, "NOTA", 1e9)
    db.commit()
    assert client.get("/api/stocks/NOTA/nota").json() == {"testo": "", "aggiornata_il": None}
    r = client.put("/api/stocks/NOTA/nota", json={"testo": "  stop sotto 40  "})
    assert r.status_code == 200 and r.json()["testo"] == "stop sotto 40"
    client.put("/api/stocks/NOTA/nota", json={"testo": "rivista"})
    assert client.get("/api/stocks/NOTA/nota").json()["testo"] == "rivista"
    assert client.put("/api/stocks/NOTA/nota", json={"testo": ""}).json()["testo"] == ""
    assert client.get("/api/stocks/NOTA/nota").json()["testo"] == ""
    assert client.put("/api/stocks/NOTA/nota", json={"testo": "x" * 5000}).status_code == 422
    assert client.put("/api/stocks/NONC/nota", json={"testo": "x"}).status_code == 404


def test_i_pari_portano_il_pe_storico_e_quello_forward(db, monkeypatch):
    """Richiesta del 2026-11-22: il P/E forward accanto a quello storico."""
    from types import SimpleNamespace

    mio = _titolo(db, "MIO", 100e9)
    _titolo(db, "VICINO", 90e9)
    _titolo(db, "ALTRO", 80e9)
    db.commit()
    fondamentali = SimpleNamespace(micro=SimpleNamespace(trailing_pe=30.0, forward_pe=24.5, revenue_growth=0.1))
    monkeypatch.setitem(sfs._CACHE, "MIO", fondamentali)
    riga = next(r for r in tc.pari(db, "MIO")["righe"] if r["ticker"] == mio.ticker)
    assert (riga["pe"], riga["pe_forward"]) == (30.0, 24.5)
