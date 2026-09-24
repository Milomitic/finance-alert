"""L'archivio puntuale dei dati non-prezzo (fase 4).

Il valore dell'archivio sta tutto nel TEMPO: una riga dice cosa si sapeva di
un titolo il giorno in cui il dato e' stato scaricato. I test fissano quindi
tre cose — che l'istante sia quello dello scaricamento, che la stessa copia non
si archivi due volte, e che una copia nuova si' — piu' il riassunto delle
catene di opzioni.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from app.models import OhlcvDaily, Stock
from app.models.archivio_non_prezzo import (
    FONTE_FONDAMENTALI,
    FONTE_OPZIONI,
    FONTI,
    ArchivioNonPrezzo,
)
from app.services import archivio_non_prezzo_service as svc
from app.services import stock_fundamentals_service as fs

_SABATO = datetime(2026, 9, 19, 9, 30, tzinfo=UTC)


def _fondamentali(ticker: str, quando: datetime, **campi) -> fs.Fundamentals:
    f = fs.Fundamentals(ticker=ticker, fetched_at=quando.timestamp())
    f.micro.recommendation_mean = 2.1
    f.micro.short_percent_of_float = 0.034
    f.analyst_actions = [
        fs.AnalystAction(date="2026-09-10", firm="Recente", action="up", from_grade="Hold", to_grade="Buy"),
        fs.AnalystAction(date="2025-01-10", firm="Vecchia", action="down", from_grade="Buy", to_grade="Hold"),
    ]
    for k, v in campi.items():
        setattr(f.micro, k, v)
    return f


@pytest.fixture
def titolo(db):
    s = Stock(ticker="ARCH", exchange="NASDAQ", name="Archivio", country="US")
    db.add(s)
    db.commit()
    return s


def _righe(db, fonte: str) -> list[ArchivioNonPrezzo]:
    return db.query(ArchivioNonPrezzo).filter_by(fonte=fonte).order_by(ArchivioNonPrezzo.id).all()


def test_la_riga_porta_l_istante_dello_SCARICAMENTO(db, titolo, monkeypatch) -> None:
    monkeypatch.setitem(fs._CACHE, "ARCH", _fondamentali("ARCH", _SABATO))
    assert svc.archivia_fondamentali(db, adesso=_SABATO + timedelta(days=2)) == 1
    (r,) = _righe(db, FONTE_FONDAMENTALI)
    assert r.giorno == date(2026, 9, 19)
    osservato = r.osservato_il if r.osservato_il.tzinfo else r.osservato_il.replace(tzinfo=UTC)
    assert osservato == _SABATO
    dati = json.loads(r.dati)
    assert dati["versione"] == svc.VERSIONE_FONDAMENTALI
    assert dati["recommendation_mean"] == 2.1 and dati["short_percent_of_float"] == 0.034
    # Solo le azioni recenti: le vecchie stanno gia' nelle righe precedenti.
    assert [a["firm"] for a in dati["analyst_actions"]] == ["Recente"]
    # E nessun dato che venga dai prezzi.
    assert "trailing_pe" not in dati and "price_to_book" not in dati


def test_la_stessa_copia_non_si_archivia_due_volte_una_nuova_si(db, titolo, monkeypatch) -> None:
    monkeypatch.setitem(fs._CACHE, "ARCH", _fondamentali("ARCH", _SABATO))
    svc.archivia_fondamentali(db)
    assert svc.archivia_fondamentali(db) == 0
    monkeypatch.setitem(fs._CACHE, "ARCH", _fondamentali("ARCH", _SABATO + timedelta(days=7),
                                                         recommendation_mean=1.8))
    assert svc.archivia_fondamentali(db) == 1
    righe = _righe(db, FONTE_FONDAMENTALI)
    assert [json.loads(r.dati)["recommendation_mean"] for r in righe] == [2.1, 1.8]


def test_una_cache_in_errore_o_assente_non_si_archivia(db, titolo, monkeypatch) -> None:
    rotta = _fondamentali("ARCH", _SABATO)
    rotta.error = "429"
    monkeypatch.setitem(fs._CACHE, "ARCH", rotta)
    assert svc.archivia_fondamentali(db) == 0
    fs._CACHE.pop("ARCH", None)
    assert svc.archivia_fondamentali(db) == 0


def test_i_nan_diventano_null_e_il_json_e_valido(db, titolo, monkeypatch) -> None:
    monkeypatch.setitem(fs._CACHE, "ARCH", _fondamentali("ARCH", _SABATO, short_ratio=float("nan")))
    svc.archivia_fondamentali(db)
    (r,) = _righe(db, FONTE_FONDAMENTALI)
    assert json.loads(r.dati)["short_ratio"] is None
    assert "NaN" not in r.dati


# ─── opzioni ───────────────────────────────────────────────────────────────

def _catena(strike_iv: list[tuple[float, float]], volume: float, oi: float) -> pd.DataFrame:
    return pd.DataFrame([{"strike": k, "impliedVolatility": iv, "volume": volume, "openInterest": oi}
                         for k, iv in strike_iv])


def test_il_riassunto_prende_lo_strike_piu_vicino_al_prezzo() -> None:
    calls = _catena([(90, 0.50), (100, 0.30), (110, 0.40)], volume=10, oi=100)
    puts = _catena([(95, 0.35), (105, 0.45)], volume=30, oi=50)
    d = svc.estrai_opzioni(calls, puts, prezzo=101.0, scadenza="2026-10-16", oggi=date(2026, 9, 24))
    assert d["iv_atm_call"] == 0.30 and d["iv_atm_put"] == 0.45
    assert d["put_call_volume"] == pytest.approx(60 / 30)
    assert d["put_call_oi"] == pytest.approx(100 / 300)
    assert d["giorni"] == 22 and d["open_interest"] == 400


def test_una_catena_senza_volume_non_divide_per_zero() -> None:
    vuota = _catena([(100, 0.0)], volume=0, oi=0)
    d = svc.estrai_opzioni(vuota, vuota, prezzo=100.0, scadenza="2026-10-16", oggi=date(2026, 9, 24))
    assert d["iv_atm_call"] is None and d["put_call_volume"] is None and d["put_call_oi"] is None


def test_solo_titoli_usa() -> None:
    assert svc.e_usa("AAPL") and svc.e_usa("BRK-B")
    assert not svc.e_usa("BP.L") and not svc.e_usa("0700.HK") and not svc.e_usa("^GSPC")


def _con_barra(db, ticker: str) -> Stock:
    s = Stock(ticker=ticker, exchange="NASDAQ" if "." not in ticker else "LSE", name=ticker, country="US")
    db.add(s)
    db.flush()
    db.add(OhlcvDaily(stock_id=s.id, date=date(2026, 9, 23), open=100, high=101, low=99, close=100.0,
                      volume=1000))
    db.commit()
    return s


def test_le_opzioni_si_archiviano_una_volta_al_giorno_e_solo_usa(db) -> None:
    _con_barra(db, "OPTA")
    _con_barra(db, "OPTB.L")
    chiesti = []

    def finta(ticker, oggi):
        chiesti.append(ticker)
        c = _catena([(100, 0.3)], volume=5, oi=10)
        return "2026-10-16", c, c

    adesso = datetime(2026, 9, 24, 20, 15, tzinfo=UTC)
    assert svc.archivia_opzioni(db, adesso=adesso, pausa_s=0, catena=finta) == 1
    assert chiesti == ["OPTA"]
    assert svc.archivia_opzioni(db, adesso=adesso, pausa_s=0, catena=finta) == 0
    assert chiesti == ["OPTA"]   # gia' fatto oggi: niente seconda chiamata
    (r,) = _righe(db, FONTE_OPZIONI)
    assert json.loads(r.dati)["iv_atm_call"] == 0.3


def test_una_limitazione_di_yahoo_ferma_il_giro(db) -> None:
    for t in ("OPTC", "OPTD", "OPTE"):
        _con_barra(db, t)
    chiesti = []

    def limitata(ticker, oggi):
        chiesti.append(ticker)
        raise RuntimeError("429 Too Many Requests")

    assert svc.archivia_opzioni(db, pausa_s=0, catena=limitata) == 0
    assert len(chiesti) == 1


def test_le_fonti_entrano_nella_colonna() -> None:
    lunghezza = ArchivioNonPrezzo.__table__.c["fonte"].type.length
    assert all(len(f) <= lunghezza for f in FONTI)


def test_i_job_non_sollevano(monkeypatch) -> None:
    from app.scheduler.jobs import archivio_non_prezzo as job
    from app.services import scan_lock

    def rotta(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(svc, "archivia_fondamentali", rotta)
    monkeypatch.setattr(svc, "archivia_opzioni", rotta)
    monkeypatch.setattr(scan_lock, "is_running", lambda: False)
    job.run_archivia_fondamentali()
    job.run_archivia_opzioni()
    monkeypatch.setattr(scan_lock, "is_running", lambda: True)
    job.run_archivia_opzioni()


def test_ogni_campo_archiviato_esiste_davvero_nella_cache() -> None:
    """⚠️ Un nome sbagliato non solleva: `asdict(...).get(nome)` rende None, e
    l'archivio registrerebbe per sempre un campo vuoto con l'aria di un dato
    assente. E' il primo errore commesso scrivendo questo modulo — quattordici
    campi cercati sul `Fundamentals` invece che su `micro`."""
    import dataclasses

    campi = {f.name for f in dataclasses.fields(fs.Fundamentals)}
    micro = {f.name for f in dataclasses.fields(fs.MicroData)}
    assert set(svc._CAMPI_FONDAMENTALI) <= campi
    assert set(svc._CAMPI_MICRO) <= micro


def test_la_catena_sceglie_la_prima_scadenza_ad_almeno_sette_giorni(monkeypatch) -> None:
    from types import SimpleNamespace

    chieste = []

    class Finto:
        def __init__(self, ticker):
            self.options = ["2026-09-25", "2026-10-02", "2026-10-16"]

        def option_chain(self, scadenza):
            chieste.append(scadenza)
            c = _catena([(100, 0.3)], volume=1, oi=1)
            return SimpleNamespace(calls=c, puts=c)

    monkeypatch.setattr("yfinance.Ticker", Finto)
    scadenza, calls, _ = svc._catena("OPTX", date(2026, 9, 24))
    assert scadenza == "2026-10-02" == chieste[0]
    assert len(calls) == 1

    class SoloVicine(Finto):
        def __init__(self, ticker):
            self.options = ["2026-09-25"]

    monkeypatch.setattr("yfinance.Ticker", SoloVicine)
    assert svc._catena("OPTX", date(2026, 9, 24)) is None
