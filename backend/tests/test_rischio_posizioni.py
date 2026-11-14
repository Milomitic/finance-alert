"""Il rischio delle posizioni aperte (FA-143) e il costo di tenuta (FA-145).

Statistica storica dello strumento, mai una previsione: i test fissano che i
numeri siano quelli che dichiarano di essere, e che dove la storia non basta
non compaia un numero."""
from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta

import pytest

from app.models import EtoroConto, EtoroPosizione, EtoroStrumento, OhlcvDaily, Stock
from app.services import rischio_posizioni_service as rp
from app.services.rischio_posizioni_service import Barra

D0 = date(2016, 1, 4)


def _passeggiata(n: int, seme: int, passo: float = 0.01, deriva: float = 0.0) -> list[Barra]:
    """Prezzo che sale o scende dello stesso passo con la stessa probabilita'."""
    rng = random.Random(seme)
    p, out = 100.0, []
    for i in range(n):
        q = p * (1 + deriva + (passo if rng.random() < 0.5 else -passo))
        out.append(Barra((D0 + timedelta(days=i)).isoformat(), max(p, q), min(p, q), q))
        p = q
    return out


# ─── Primo passaggio ────────────────────────────────────────────────────────

def test_stop_e_target_equidistanti_su_una_passeggiata_simmetrica_fanno_meta_e_meta():
    barre = _passeggiata(40_000, 1)
    g = rp.primo_passaggio(barre, "long", 0.03, 0.03, orizzonte=60)
    risolte = g["stop"] + g["target"]
    assert risolte > 500
    assert abs(g["stop"] / risolte - 0.5) < 0.05
    assert g["finestre"] == g["stop"] + g["target"] + g["nessuno"]


def test_un_corto_vede_lo_specchio():
    sale = _passeggiata(3_000, 2, deriva=0.004)
    lungo = rp.primo_passaggio(sale, "long", 0.05, 0.05)
    corto = rp.primo_passaggio(sale, "short", 0.05, 0.05)
    assert lungo["target"] > lungo["stop"] and corto["stop"] > corto["target"]


def test_stop_e_target_nella_stessa_barra_contano_come_stop():
    barre = [Barra(f"d{i}", 100, 100, 100) for i in range(300)]
    barre[1] = Barra("d1", 110, 90, 100)          # tocca entrambi nella prima finestra
    g = rp.primo_passaggio(barre, "long", 0.05, 0.05, orizzonte=21)
    assert g["stop"] == 1 and g["target"] == 0


def test_senza_storia_o_senza_distanza_non_c_e_un_numero():
    assert rp.primo_passaggio(_passeggiata(200, 3), "long", 0.05, 0.05) is None
    assert rp.primo_passaggio(_passeggiata(400, 3), "long", 0.0, 0.05) is None
    assert rp.primo_passaggio(_passeggiata(400, 3), "long", -0.01, 0.05) is None


def test_le_finestre_non_si_sovrappongono():
    g = rp.primo_passaggio(_passeggiata(1_000, 4), "long", 0.5, None, orizzonte=21)
    assert g["finestre"] == (1_000 - 1) // 21
    assert g["target"] == 0


# ─── Distanze, beta, correlazione ───────────────────────────────────────────

def test_la_distanza_dallo_stop_ha_il_segno_del_lato():
    d = rp.distanza_dallo_stop(100, 90, "long", 2.0, 0.02)
    assert d == pytest.approx({"pct": 0.10, "atr": 5.0, "sedute_tipiche": 5.0})
    assert rp.distanza_dallo_stop(100, 110, "short", 2.0, None)["pct"] == pytest.approx(0.10)
    # Gia' oltre lo stop: negativa, non nascosta.
    assert rp.distanza_dallo_stop(100, 105, "long", None, None)["pct"] < 0
    assert rp.distanza_dallo_stop(100, None, "long", 2.0, 0.02)["pct"] is None


def test_la_beta_e_quella_della_regressione():
    rng = random.Random(5)
    indice = {f"d{i}": rng.gauss(0, 0.01) for i in range(300)}
    titolo = {d: 3 * r for d, r in indice.items()}
    assert rp.beta(titolo, indice) == pytest.approx(3.0)
    assert rp.beta(dict(list(titolo.items())[:50]), indice) is None


def test_posizioni_effettive():
    assert rp.posizioni_effettive([1.0], [[1.0]]) == 1.0
    assert rp.posizioni_effettive([1, 1, 1], [[1, 1, 1]] * 3) == 1.0
    ident = [[1.0 if i == j else 0.0 for j in range(3)] for i in range(3)]
    assert rp.posizioni_effettive([1, 1, 1], ident) == 3.0
    assert rp.posizioni_effettive([1, 1], None) is None


# ─── L'assemblatore e l'endpoint ───────────────────────────────────────────

def _portafoglio(db, *, leva: int = 5, lato: str = "long", stop: float | None = 80.0):
    s = Stock(ticker="SOXL", exchange="NYSE", name="Direxion Semis 3x", country="US",
              instrument_type="etf")
    db.add(s)
    db.flush()
    for b in _passeggiata(600, 6):
        db.add(OhlcvDaily(stock_id=s.id, date=date.fromisoformat(b.data), open=b.chiusura,
                          high=b.alto, low=b.basso, close=b.chiusura, volume=1e6))
    adesso = datetime.now(UTC)
    db.add(EtoroStrumento(instrument_id=1, simbolo="SOXL", nome="SOXL", stock_id=s.id,
                          abbinamento="auto", aggiornato_il=adesso))
    db.flush()   # lo strumento prima della posizione che lo riferisce
    db.add(EtoroPosizione(position_id=10, instrument_id=1, lato=lato, leva=leva,
                          regolamento="cfd", aperta_il=adesso - timedelta(days=30),
                          prezzo_apertura=100.0, unita=10, importo_usd=1000.0,
                          esposizione_usd=5000.0, margine_usd=1000.0, stop=stop, target=None,
                          prezzo_corrente=100.0, commissioni_usd=3.0, vista_il=adesso))
    db.add(EtoroConto(id=1, aggiornato_il=adesso, valuta="USD", valore_totale=2000.0))
    db.commit()


def test_il_quadro_porta_esposizione_sul_sottostante_e_leva(db, monkeypatch):
    _portafoglio(db)
    indice = _passeggiata(600, 6)            # lo stesso percorso: beta 1 in rendimenti
    monkeypatch.setattr(rp, "_barre_indice", lambda sym: indice)
    q = rp.rischio(db)
    assert q["leva_effettiva"] == 2.5
    # SOXL e' tre volte i semiconduttori: 5.000 di esposizione sono 15.000 sul sottostante.
    assert q["per_sottostante"][0] == {"nome": "Semiconduttori (SOX)", "usd": 15000.0}
    p = q["posizioni"][0]
    assert p["distanza_stop_pct"] == pytest.approx(20.0)
    assert p["primo_passaggio"]["finestre"] > 20
    # Scenario lineare: 5.000 x beta 1 x -5% = -250.
    meno5 = [s for s in q["scenario"] if s["indice"] == "S&P 500" and s["shock_pct"] == -5][0]
    assert meno5["pnl_usd"] == pytest.approx(-250.0, rel=1e-6)
    assert q["posizioni_effettive"] == 1.0


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.api import etoro as api
    from app.api.deps import get_current_user, get_db
    from app.main import app
    from app.models import User

    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    api._CACHE_RISCHIO.clear()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_il_costo_di_tenuta_e_quattro_notti_e_il_fine_settimana(db, client, monkeypatch):
    from types import SimpleNamespace as NS

    from app.services import etoro_catalogo_service as catalogo
    from app.services import etoro_client

    _portafoglio(db)
    monkeypatch.setattr(rp, "_barre_indice", lambda sym: [])
    monkeypatch.setattr(etoro_client, "configurato", lambda: True)
    monkeypatch.setattr(catalogo, "costi", lambda *a, **k: NS(notte_usd=1.0, weekend_usd=3.0))
    c = client.get("/api/etoro/rischio").json()["posizioni"][0]["costo_tenuta"]
    assert (c["pagate_usd"], c["settimana_usd"], c["settimane_12_usd"]) == (3.0, 7.0, 84.0)


def test_una_posizione_senza_leva_non_paga_notti(db, client, monkeypatch):
    _portafoglio(db, leva=1)
    monkeypatch.setattr(rp, "_barre_indice", lambda sym: [])
    c = client.get("/api/etoro/rischio").json()["posizioni"][0]["costo_tenuta"]
    assert c["settimane_4_usd"] == 0.0


# ─── Le fonti delle barre, eseguite davvero (il cancello del codice morto) ──

def test_le_barre_di_uno_strumento_fuori_catalogo_vengono_da_yahoo_e_restano_in_memoria(monkeypatch):
    import pandas as pd

    from app.services import ohlcv_service

    chiamate = []

    def finto(tickers, **kw):
        chiamate.append((tuple(tickers), kw))
        idx = pd.to_datetime(["2026-11-12", "2026-11-13"])
        cols = pd.MultiIndex.from_product([["TECL"], ["High", "Low", "Close"]])
        return pd.DataFrame([[11, 9, 10], [12, 10, 11]], index=idx, columns=cols)

    rp._CACHE_YAHOO.clear()
    monkeypatch.setattr(ohlcv_service, "_yf_download", finto)
    barre = rp._barre_yahoo("TECL")
    assert barre == [Barra("2026-11-12", 11.0, 9.0, 10.0), Barra("2026-11-13", 12.0, 10.0, 11.0)]
    assert rp._barre_yahoo("TECL") == barre
    assert len(chiamate) == 1 and chiamate[0][1] == {"period": "10y"}

    monkeypatch.setattr(ohlcv_service, "_yf_download", lambda *a, **k: (_ for _ in ()).throw(OSError("giu'")))
    assert rp._barre_yahoo("XYZ") == []
    rp._CACHE_YAHOO.clear()


def test_le_barre_dell_indice_vengono_dal_dettaglio_mercato(monkeypatch):
    from types import SimpleNamespace as NS

    from app.services import market_detail_service

    barra = NS(date=date(2026, 11, 13), high=6010.0, low=5950.0, close=6000.0)
    monkeypatch.setattr(market_detail_service, "get_detail", lambda s, r: NS(bars=[barra]))
    assert rp._barre_indice("^GSPC") == [Barra("2026-11-13", 6010.0, 5950.0, 6000.0)]
    monkeypatch.setattr(market_detail_service, "get_detail", lambda s, r: None)
    assert rp._barre_indice("^GSPC") == []
    monkeypatch.setattr(market_detail_service, "get_detail",
                        lambda s, r: (_ for _ in ()).throw(RuntimeError("yahoo giu'")))
    assert rp._barre_indice("^GSPC") == []


def test_sotto_pytest_l_avvio_non_lancia_thread_di_riscaldamento(monkeypatch):
    """Un thread nato nel ciclo di vita di un TestClient sopravvive al test e
    usa la connessione del test successivo: in CI ha fatto cadere pytest con
    un segmentation fault di SQLite."""
    import threading

    from app import main

    partiti = []
    monkeypatch.setattr(threading.Thread, "start", lambda self: partiti.append(self.name))
    main._warm_sector_performance_on_boot()
    main._warm_premarket_on_boot()
    assert partiti == []
