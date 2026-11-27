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


# ── FA-186: composizione dell'indice ────────────────────────────────────────

def _semina_indice(db, codice: str, titoli: list[tuple[str, float | None, float | None, str]]):
    from datetime import UTC, datetime

    from app.models import Index, Stock, StockIndex
    from app.models.stock_metrics import StockMetrics

    ix = Index(code=codice, name=f"Indice {codice}")
    db.add(ix)
    db.commit()
    for t, cap, var, settore in titoli:
        s = Stock(ticker=t, exchange="NYSE", name=f"{t} Inc", sector=settore, country="US",
                  market_cap=cap, currency="USD")
        db.add(s)
        db.commit()
        db.add(StockIndex(stock_id=s.id, index_id=ix.id))
        db.add(StockMetrics(stock_id=s.id, computed_at=datetime(2026, 11, 27, 22, tzinfo=UTC), change_pct=var))
    db.commit()


def test_composizione_di_un_indice_pesato_sulla_capitalizzazione(client, db):
    titoli = [(f"T{i}", 100.0 * (i + 1), float(i - 3), "Tech" if i % 2 else "Salute") for i in range(8)]
    titoli.append(("SENZA", None, None, "Tech"))
    _semina_indice(db, "SP500", titoli)
    d = client.get("/api/markets/%5EGSPC/composizione").json()
    assert d["indice"] == {"code": "SP500", "nome": "Indice SP500", "titoli_nel_catalogo": 9, "nota": None,
                           "pesato_sul_prezzo": False}
    assert [t["ticker"] for t in d["migliori"]] == ["T7", "T6", "T5", "T4", "T3"]
    assert d["peggiori"][0]["ticker"] == "T0"
    # contributo = peso di capitalizzazione x variazione in punti
    t7 = d["migliori"][0]
    assert t7["peso_pct"] == pytest.approx(800 / 3600 * 100)
    assert t7["contributo_pp"] == pytest.approx(800 / 3600 * 4.0)
    assert sum(s["peso_pct"] for s in d["settori"]) == pytest.approx(100.0)
    assert d["ampiezza"]["avanzano"] == 4 and d["ampiezza"]["scendono"] == 3   # senza snapshot: dai titoli


def test_un_indice_pesato_sul_prezzo_non_ha_contributi(client, db):
    _semina_indice(db, "DJI", [("A", 100.0, 1.0, "X"), ("B", 200.0, -1.0, "X")])
    d = client.get("/api/markets/%5EDJI/composizione").json()
    assert d["indice"]["pesato_sul_prezzo"] is True
    assert all(t["contributo_pp"] is None and t["peso_pct"] is None for t in d["migliori"])
    assert d["settori"][0]["peso_pct"] is None


def test_senza_costituenti_e_404(client, db):
    assert client.get("/api/markets/%5EVIX/composizione").status_code == 404
    assert client.get("/api/markets/%5EGSPC/composizione").status_code == 404   # indice non nel catalogo


# ── FA-187: confronto normalizzato ──────────────────────────────────────────

def _serie_studio(date_, chiusure):
    from app.services.studio_service import Serie

    return Serie(list(date_), list(chiusure))


def test_il_confronto_parte_da_100_lo_stesso_giorno_e_porta_avanti_il_sabato(client):
    from app.services import studio_service

    ven, sab, lun = date(2026, 11, 20), date(2026, 11, 21), date(2026, 11, 23)
    gio = date(2026, 11, 19)
    serie = {
        "^GSPC": _serie_studio([gio, ven, lun], [100.0, 110.0, 121.0]),
        "BTC-USD": _serie_studio([ven, sab, lun], [50.0, 55.0, 25.0]),   # comincia dopo
    }
    with patch.object(studio_service, "serie_di", side_effect=lambda db, s: serie.get(s)):
        d = client.get("/api/markets/confronto?simboli=^GSPC,BTC-USD&periodo=1m").json()
    assert d["dal"] == ven.isoformat() and d["date"] == [ven.isoformat(), sab.isoformat(), lun.isoformat()]
    assert d["serie"]["^GSPC"] == [100.0, 100.0, 110.0]       # il sabato resta al venerdi'
    assert d["serie"]["BTC-USD"] == [100.0, 110.0, 50.0]
    assert d["riepilogo"]["BTC-USD"]["peggior_calo"] == pytest.approx(50 / 110 - 1)
    assert d["riepilogo"]["^GSPC"]["rendimento"] == pytest.approx(0.10)


def test_confronto_simbolo_sconosciuto_e_troppi_simboli(client):
    from app.services import studio_service

    with patch.object(studio_service, "serie_di", return_value=None):
        r = client.get("/api/markets/confronto?simboli=NOPE")
    assert r.status_code == 404 and "NOPE" in r.json()["detail"]
    assert client.get("/api/markets/confronto?simboli=" + ",".join("ABCDEFG")).status_code == 422
    assert client.get("/api/markets/confronto?simboli=A&periodo=99a").status_code == 422


def test_una_serie_lunga_si_sfoltisce_tenendo_l_ultimo_giorno():
    from app.services import studio_service

    giorni = [date(2016, 1, 1) + timedelta(days=i) for i in range(3650)]
    s = _serie_studio(giorni, [100.0 + i for i in range(3650)])
    with patch.object(studio_service, "serie_di", return_value=s):
        d = ms.confronto(None, ["X"], "10a")
    assert len(d["date"]) <= ms.MAX_PUNTI + 1
    assert d["date"][-1] == giorni[-1].isoformat()
