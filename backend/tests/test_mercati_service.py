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


def test_l_endpoint_delle_sessioni(client):
    d = client.get("/api/markets/sessioni").json()
    assert [b["regione"] for b in d["borse"]] == ["JP", "HK", "EU", "UK", "US"]
    assert all(b["fase"] in {"pre", "seduta", "after", "chiusa"} for b in d["borse"])


# ── FA-190: paniere esteso ──────────────────────────────────────────────────

def test_il_paniere_della_home_non_cambia_e_i_mercati_estesi_si_aprono():
    from app.api import market, market_detail

    assert len(market.LIVE_ASSET_DEFINITIONS) == 15          # la home resta com'era
    simboli = [d[0] for d in market.TUTTI_I_MERCATI]
    assert len(simboli) == len(set(simboli))
    assert {"^RUT", "^GDAXI", "DX-Y.NYB", "EURUSD=X", "HG=F"} <= set(simboli)
    assert "^TNX" not in simboli                              # un livello, non un prezzo
    assert market_detail._LIVE_META["^RUT"][1] == "index"
    assert market_detail._FUTURE_DI["^RUT"] == "RTY=F"


def test_i_cambi_sono_vivi_come_i_future():
    from datetime import UTC, datetime

    from app.api import market

    martedi = datetime(2026, 12, 1, 3, 0, tzinfo=UTC)        # notte europea, Globex aperto
    assert market._quote_is_live("fx", False, None, martedi)
    sabato = datetime(2026, 11, 28, 12, 0, tzinfo=UTC)
    assert not market._quote_is_live("fx", False, None, sabato)


def test_l_endpoint_dei_mercati_estesi(client):
    from app.api import market
    from app.services import live_quote_service as lq

    def quotazioni(simboli, **k):
        return {s: lq.LiveQuote(ticker=s, price=1.0, change_pct=0.5, market_state="CLOSED") for s in simboli}

    with patch.object(lq, "get_quotes_batch", side_effect=quotazioni), \
         patch("app.services.live_sparkline_service.get_sparklines", return_value={}):
        d = client.get("/api/markets/estesi").json()
    assert [a["symbol"] for a in d["assets"]] == [x[0] for x in market.MERCATI_ESTESI]
    rut = next(a for a in d["assets"] if a["symbol"] == "^RUT")
    assert rut["using_futures"] is True and rut["quote_symbol"] == "RTY=F"


# ── FA-188: contesto ────────────────────────────────────────────────────────

def test_percentile_con_i_pari_a_meta():
    assert ms.percentile_di(5.0, [1.0, 2.0, 5.0, 9.0]) == pytest.approx(62.5)
    assert ms.percentile_di(3.0, [3.0, 3.0]) == 50.0
    assert ms.percentile_di(3.0, []) is None


def _semina_fred(db, fred_id: str, valori: list[tuple[date, float]]):
    from app.models import MacroObservation, MacroSeries

    s = MacroSeries(fred_series_id=fred_id, label=fred_id, region="US", importance="high")
    db.add(s)
    db.flush()
    for g, v in valori:
        db.add(MacroObservation(series_id=s.id, date=g, value=v))
    db.commit()


def test_il_contesto_ha_tassi_curva_e_ampiezza_senza_percentile_se_l_archivio_e_corto(client, db):
    from datetime import UTC, datetime

    from app.models.ampiezza_giornaliera import AmpiezzaGiornaliera

    g0 = date(2026, 9, 1)
    giorni = [g0 + timedelta(days=i) for i in range(90)]
    _semina_fred(db, "DGS10", [(g, 4.0 + i / 100) for i, g in enumerate(giorni)])
    _semina_fred(db, "DGS2", [(g, 3.5) for g in giorni])
    _semina_fred(db, "DFEDTARU", [(g, 4.25) for g in giorni])
    db.add(AmpiezzaGiornaliera(giorno=g0, ambito="universo", titoli=1000, avanzano=500, scendono=400,
                               sopra_ema50_pct=50, sopra_ema200_pct=49.5, rsi_sopra_70=1, rsi_sotto_30=1,
                               var_media_pct=0.1, scritto_il=datetime(2026, 9, 1, tzinfo=UTC)))
    db.commit()
    snap = (None, {"global": {"pct_above_ema200": 49.5}})
    with patch.object(mds, "get_detail", side_effect=lambda s, r: _dettaglio(s)), \
         patch("app.services.market_stats_service.get_latest_snapshot_payload", return_value=snap):
        d = client.get("/api/markets/contesto").json()
    t = {x["chiave"]: x for x in d["tessere"]}
    assert set(t) == {"vix", "curva", "fed", "ampiezza", "dollaro"}          # la BCE manca: niente tessera
    assert t["curva"]["valore"] == pytest.approx(4.89 - 3.5)
    assert t["curva"]["prima"] == pytest.approx(4.0 + 59 / 100 - 3.5)
    assert t["fed"]["valore"] == 4.25 and t["fed"]["unita"] == "%"
    assert t["ampiezza"]["percentile"] is None and "1 giorno," in t["ampiezza"]["nota"]
    assert t["vix"]["variazione_relativa"] is not None and t["vix"]["percentile_dal"].startswith("20")


def test_una_fonte_guasta_toglie_solo_la_sua_tessera(client, db):
    def guasto(s, r):
        raise RuntimeError("yahoo giu'")

    with patch.object(mds, "get_detail", side_effect=guasto), \
         patch("app.services.market_stats_service.get_latest_snapshot_payload", return_value=(None, {})):
        d = client.get("/api/markets/contesto").json()
    assert d["tessere"] == []


def test_con_abbastanza_archivio_l_ampiezza_ha_il_suo_percentile(client, db, monkeypatch):
    from datetime import UTC, datetime

    from app.models.ampiezza_giornaliera import AmpiezzaGiornaliera

    monkeypatch.setattr(ms, "MIN_GIORNI_PERCENTILE_AMPIEZZA", 3)
    for i, v in enumerate([40.0, 45.0, 60.0]):
        db.add(AmpiezzaGiornaliera(giorno=date(2026, 11, 1 + i), ambito="universo", titoli=1, avanzano=0, scendono=0,
                                   sopra_ema50_pct=v, sopra_ema200_pct=v, rsi_sopra_70=0, rsi_sotto_30=0,
                                   var_media_pct=0, scritto_il=datetime(2026, 11, 1, tzinfo=UTC)))
    db.commit()
    with patch.object(mds, "get_detail", return_value=None), \
         patch("app.services.market_stats_service.get_latest_snapshot_payload",
               return_value=(None, {"global": {"pct_above_ema200": 50.0}})):
        t = client.get("/api/markets/contesto").json()["tessere"][0]
    assert t["chiave"] == "ampiezza" and t["percentile"] == pytest.approx(200 / 3)
    assert t["percentile_dal"] == "2026-11-01" and t["nota"] is None


# ── FA-189: correlazioni ────────────────────────────────────────────────────

def _rend(n: int, f, dal: date = date(2025, 1, 1)) -> dict:
    return {dal + timedelta(days=i): f(i) for i in range(n)}


def test_correlazione_di_una_coppia_simmetrica_e_con_se_stessa():
    import math

    a = _rend(100, lambda i: math.sin(i))
    b = _rend(100, lambda i: -math.sin(i))
    assert ms.correlazione_coppia(a, a, 60) == 1.0
    assert ms.correlazione_coppia(a, b, 60) == -1.0
    assert ms.correlazione_coppia(a, b, 60) == ms.correlazione_coppia(b, a, 60)


def test_poche_date_comuni_o_serie_ferma_danno_vuoto_non_nan():
    import math

    a = _rend(100, lambda i: math.sin(i))
    assert ms.correlazione_coppia(a, _rend(20, lambda i: 0.01 * i), 60) is None
    assert ms.correlazione_coppia(a, _rend(100, lambda i: 0.0), 60) is None


def test_la_correlazione_si_calcola_sulle_date_della_coppia_e_fino_a_una_data():
    import math

    a = _rend(400, lambda i: math.sin(i))
    b = {d: (v if d < date(2025, 9, 1) else -v) for d, v in a.items()}   # cambia segno a settembre
    assert ms.correlazione_coppia(a, b, 60) == -1.0
    assert ms.correlazione_coppia(a, b, 60, fino_a=date(2025, 8, 1)) == 1.0


def test_l_endpoint_delle_correlazioni(client):
    with patch.object(mds, "get_detail", side_effect=lambda s, r: _dettaglio(s) if s in ("^GSPC", "GC=F") else None):
        ms.CACHE_CORRELAZIONI[60].svuota()
        d = client.get("/api/markets/correlazioni?sedute=60").json()
    assert [s["symbol"] for s in d["simboli"]] == ["^GSPC", "GC=F"]
    assert d["matrice"][0][0] == 1.0 and d["matrice"][0][1] == d["matrice"][1][0]
    assert client.get("/api/markets/correlazioni?sedute=33").status_code == 422
