"""FA-184/185: panoramica dei rendimenti e statistiche di uno strumento."""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import User
from app.services import market_detail_service as mds
from app.services import mercati_service as ms


def _dettaglio(simbolo: str, anni: int = 6, passo: float = 0.0004) -> mds.MarketDetailDC:
    """Feriali da `anni` fa a oggi-ish, prezzo che sale con un calo del 30%
    a meta' e poi recupera."""
    fine = date(2026, 11, 26)
    g, giorni = fine - timedelta(days=365 * anni), []
    while g <= fine:
        if g.weekday() < 5:
            giorni.append(g)
        g += timedelta(days=1)
    n = len(giorni)
    chiusure = []
    for i in range(n):
        base = 100.0 * (1 + passo) ** i
        if n // 2 <= i < n // 2 + 60:
            base *= 0.7
        chiusure.append(base)
    barre = [mds.OhlcvBar(d, c, c, c, c, None) for d, c in zip(giorni, chiusure, strict=True)]
    return mds.MarketDetailDC(symbol=simbolo, range_key="1d", bars=barre)


@pytest.fixture
def client(db):
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_statistiche_di_un_indice(client):
    with patch.object(mds, "get_detail", side_effect=lambda s, r: _dettaglio(s)):
        r = client.get("/api/markets/%5EGSPC/statistiche")
    assert r.status_code == 200
    d = r.json()
    assert d["rendimenti"]["1a"] > 0 and d["rendimenti"]["5a_ann"] is not None
    assert d["calo_massimo_storico"]["profondita"] == pytest.approx(-0.30, abs=0.01)
    assert d["calo_massimo_storico"]["recupero"] is not None
    assert d["calendario"]["anni"][0]["anno"] == 2026 and d["calendario"]["anni"][0]["parziale"]
    assert len(d["calendario"]["media_mesi"]) == 12
    assert d["vol_20g"] is not None


def test_statistiche_di_un_simbolo_sconosciuto_o_senza_dati(client):
    assert client.get("/api/markets/NOPE/statistiche").status_code == 404
    with patch.object(mds, "get_detail", return_value=None):
        assert client.get("/api/markets/%5EGSPC/statistiche").status_code == 404


def test_la_panoramica_ha_ogni_strumento_e_salta_quello_rotto(client):
    def dett(s, r):
        if s == "^VIX":
            raise RuntimeError("yahoo giu'")
        return None if s == "ETH-USD" else _dettaglio(s)

    with patch.object(mds, "get_detail", side_effect=dett):
        d = client.get("/api/markets/panoramica").json()
    simboli = [x["symbol"] for x in d["strumenti"]]
    assert "^GSPC" in simboli and "^VIX" not in simboli and "ETH-USD" not in simboli
    assert d["alla_chiusura_del"] == "2026-11-26"
    gspc = next(x for x in d["strumenti"] if x["symbol"] == "^GSPC")
    assert 0 <= gspc["posizione_52s"] <= 1
    assert gspc["distanza_ema200"] is not None


def test_le_cripto_annualizzano_su_365_sedute():
    def alterna(s, r):
        d = _dettaglio(s)
        for i, b in enumerate(d.bars):
            b.close = 100.0 * (1.02 if i % 2 else 0.98)
        return d

    with patch.object(mds, "get_detail", side_effect=alterna):
        azioni = ms.riga_panoramica("^GSPC", "S&P", "index", "us")
        cripto = ms.riga_panoramica("BTC-USD", "Bitcoin", "crypto", None)
    # Una volatilita' vera (rendimenti alterni), non zero: con una serie a
    # crescita costante 0 == 0 * sqrt(365/252) passerebbe comunque.
    assert azioni["vol_20g"] > 0.1
    assert cripto["vol_20g"] == pytest.approx(azioni["vol_20g"] * (365 / 252) ** 0.5)
