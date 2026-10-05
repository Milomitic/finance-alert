"""Il diario delle operazioni chiuse, legato ai segnali (FA-128)."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Alert, PlanOutcome, Stock, User
from app.models.etoro import EtoroOperazione, EtoroStrumento
from app.services import etoro_diario_service as dia

APERTA = datetime(2026, 9, 10, 14, 0, tzinfo=UTC)


@pytest.fixture
def base(db: Session) -> dict:
    soxl = Stock(ticker="SOXL", exchange="NYSE Arca", name="Direxion Semi Bull 3X")
    mu = Stock(ticker="MU", exchange="NASDAQ", name="Micron")
    db.add_all([soxl, mu])
    db.commit()
    db.add_all([
        EtoroStrumento(instrument_id=3226, simbolo="SOXL", nome="SOXL ETF", tipo="ETF", stock_id=soxl.id,
                       abbinamento="automatico", aggiornato_il=APERTA),
        EtoroStrumento(instrument_id=1130, simbolo="MU", nome="Micron", tipo="Stocks", stock_id=mu.id,
                       abbinamento="automatico", aggiornato_il=APERTA),
        EtoroStrumento(instrument_id=100000, simbolo="BTC", nome="Bitcoin", tipo="Crypto",
                       abbinamento="assente", aggiornato_il=APERTA),
    ])
    db.commit()
    return {"soxl": soxl, "mu": mu}


def _segnale(db: Session, stock: Stock, tono: str, emesso: datetime, nome: str = "trend_pullback") -> Alert:
    a = Alert(signal_name=nome, stock_id=stock.id, trigger_price=30.0, emitted_at=emesso,
              triggered_at=emesso, snapshot=json.dumps({"tone": tono}))
    db.add(a)
    db.commit()
    return a


def _piano(db: Session, a: Alert, entry: float, stop: float, r_multiple: float, esito: str = "tp1") -> None:
    db.add(PlanOutcome(alert_id=a.id, stock_id=a.stock_id, detector=a.signal_name, signal_date=date(2026, 9, 9),
                       tone="bull", horizon_days=21, entry_date=date(2026, 9, 9), entry=entry, stop=stop, tp1=entry + 2,
                       r=abs(entry - stop), esito=esito, resolved_date=date(2026, 9, 20), bars_to_outcome=8,
                       r_multiple=r_multiple, mae_r=-0.3, mfe_r=1.8, tp2_reached=False))
    db.commit()


def _op(db: Session, pid: int, iid: int, profitto: float, *, lato="long", aperta=APERTA,
        chiusa=APERTA + timedelta(days=6), apertura=30.0, chiusura=33.0, investimento=500.0) -> None:
    db.add(EtoroOperazione(position_id=pid, instrument_id=iid, aperta_il=aperta, chiusa_il=chiusa, lato=lato, leva=5,
                           prezzo_apertura=apertura, prezzo_chiusura=chiusura, investimento_usd=investimento,
                           profitto_netto_usd=profitto, commissioni_usd=2.0))
    db.commit()


def _cambi(serie: dict[date, float]):
    return lambda dal: serie


def test_un_segnale_che_precede_lega_l_operazione_e_dice_l_R(db: Session, base) -> None:
    a = _segnale(db, base["soxl"], "bull", APERTA - timedelta(days=1))
    _piano(db, a, entry=30.0, stop=28.0, r_multiple=1.5)
    _op(db, 1, 3226, 150.0, apertura=30.0, chiusura=33.0)
    d = dia.diario(db, cambi=_cambi({}))
    v = d.voci[0]
    assert (v.ticker, v.alert_id, v.detector) == ("SOXL", a.id, "trend_pullback")
    # Movimento +3 su un rischio del piano di 2: +1,5 R, come il piano.
    assert (v.r_reale, v.r_piano, v.esito_piano) == (1.5, 1.5, "tp1")
    assert v.pct_investimento == pytest.approx(30.0)
    assert v.giorni == pytest.approx(6.0)


def test_il_verso_conta(db: Session, base) -> None:
    _segnale(db, base["soxl"], "bear", APERTA - timedelta(hours=2))
    _op(db, 1, 3226, 50.0)
    assert dia.diario(db, cambi=_cambi({})).voci[0].alert_id is None


def test_un_segnale_troppo_vecchio_o_successivo_non_precede(db: Session, base) -> None:
    _segnale(db, base["soxl"], "bull", APERTA - timedelta(days=6))
    _segnale(db, base["soxl"], "bull", APERTA + timedelta(hours=1))
    _op(db, 1, 3226, 50.0)
    assert dia.diario(db, cambi=_cambi({})).voci[0].alert_id is None


def test_fra_piu_segnali_vince_il_piu_vicino(db: Session, base) -> None:
    _segnale(db, base["soxl"], "bull", APERTA - timedelta(days=3), nome="sr_flip")
    vicino = _segnale(db, base["soxl"], "bull", APERTA - timedelta(hours=5), nome="volume_breakout")
    _op(db, 1, 3226, 50.0)
    assert dia.diario(db, cambi=_cambi({})).voci[0].alert_id == vicino.id


def test_uno_short_si_misura_al_contrario(db: Session, base) -> None:
    a = _segnale(db, base["mu"], "bear", APERTA - timedelta(hours=3))
    _piano(db, a, entry=100.0, stop=104.0, r_multiple=-1.0, esito="stop")
    _op(db, 1, 1130, 80.0, lato="short", apertura=100.0, chiusura=96.0)
    assert dia.diario(db, cambi=_cambi({})).voci[0].r_reale == pytest.approx(1.0)


def test_uno_strumento_fuori_catalogo_resta_senza_segnale(db: Session, base) -> None:
    _op(db, 1, 100000, -40.0)
    v = dia.diario(db, cambi=_cambi({})).voci[0]
    assert (v.ticker, v.simbolo, v.alert_id) == (None, "BTC", None)


def test_il_riepilogo_separa_precedute_e_non(db: Session, base) -> None:
    a = _segnale(db, base["soxl"], "bull", APERTA - timedelta(hours=2))
    _piano(db, a, entry=30.0, stop=28.0, r_multiple=0.5)
    _op(db, 1, 3226, 100.0)
    _op(db, 2, 1130, -50.0, chiusa=APERTA + timedelta(days=2))
    _op(db, 3, 100000, 20.0, chiusa=APERTA + timedelta(days=1))
    d = dia.diario(db, cambi=_cambi({}))
    assert (d.tutte.n, d.tutte.vincenti, d.tutte.profitto_usd) == (3, 2, 70.0)
    assert d.tutte.vincenti_pct == pytest.approx(66.67, abs=0.01)
    assert (d.precedute.n, d.non_precedute.n) == (1, 2)
    # Un tasso su una sola operazione non si mostra.
    assert d.precedute.vincenti_pct is None
    assert (d.con_r, d.r_reale_medio, d.r_piano_medio) == (1, 1.5, 0.5)
    # Ordinate dalla chiusura piu' recente.
    assert [v.position_id for v in d.voci] == [1, 2, 3]


def test_l_anno_in_euro_al_cambio_del_giorno_di_chiusura(db: Session, base) -> None:
    _op(db, 1, 3226, 117.0, chiusa=datetime(2026, 9, 16, 15, tzinfo=UTC))
    # Chiusa di domenica: vale il cambio del venerdi'.
    _op(db, 2, 1130, 58.5, chiusa=datetime(2026, 9, 13, 15, tzinfo=UTC))
    d = dia.diario(db, cambi=_cambi({date(2026, 9, 16): 1.17, date(2026, 9, 11): 1.17}))
    [anno] = d.anni
    assert (anno.anno, anno.n, anno.profitto_usd, anno.commissioni_usd) == (2026, 2, 175.5, 4.0)
    assert anno.profitto_eur == pytest.approx(150.0)


def test_senza_cambio_l_euro_e_ignoto_non_parziale(db: Session, base) -> None:
    _op(db, 1, 3226, 117.0, chiusa=datetime(2026, 9, 16, 15, tzinfo=UTC))
    _op(db, 2, 1130, 10.0, chiusa=datetime(2026, 8, 1, 15, tzinfo=UTC))
    d = dia.diario(db, cambi=_cambi({date(2026, 9, 16): 1.17}))
    assert d.anni[0].profitto_eur is None


def test_un_diario_vuoto(db: Session) -> None:
    d = dia.diario(db, cambi=_cambi({}))
    assert (d.voci, d.tutte, d.anni) == ([], None, [])


def test_la_cache_dei_cambi(monkeypatch) -> None:
    dia.svuota_cache()
    chiamate: list[date] = []

    def scarica(dal):
        chiamate.append(dal)
        return {date(2026, 9, 1): 1.1, date(2026, 9, 30): 1.2}

    orologio = [0.0]
    dia.cambi_eurusd(date(2026, 9, 10), scarica=scarica, ora=lambda: orologio[0])
    dia.cambi_eurusd(date(2026, 9, 10), scarica=scarica, ora=lambda: orologio[0])
    assert len(chiamate) == 1
    # Un giorno prima della serie in cache la rifa'.
    dia.cambi_eurusd(date(2026, 8, 1), scarica=scarica, ora=lambda: orologio[0])
    assert len(chiamate) == 2
    dia.svuota_cache()


def test_lo_scaricamento_senza_rete_rende_vuoto(monkeypatch) -> None:
    import yfinance as yf

    def giu(*a, **k):
        raise OSError("rete")

    monkeypatch.setattr(yf, "download", giu)
    assert dia._scarica_eurusd(date(2026, 9, 1)) == {}


def test_lo_scaricamento_legge_le_chiusure(monkeypatch) -> None:
    import pandas as pd
    import yfinance as yf

    df = pd.DataFrame({"Close": [1.1, float("nan"), 1.2]},
                      index=pd.to_datetime(["2026-09-01", "2026-09-02", "2026-09-03"]))
    monkeypatch.setattr(yf, "download", lambda *a, **k: df)
    assert dia._scarica_eurusd(date(2026, 9, 1)) == {date(2026, 9, 1): 1.1, date(2026, 9, 3): 1.2}
    monkeypatch.setattr(yf, "download", lambda *a, **k: pd.DataFrame())
    assert dia._scarica_eurusd(date(2026, 9, 1)) == {}


def test_l_endpoint(db: Session, base, monkeypatch) -> None:
    monkeypatch.setattr(dia, "cambi_eurusd", lambda dal: {})
    a = _segnale(db, base["soxl"], "bull", APERTA - timedelta(hours=2))
    _piano(db, a, entry=30.0, stop=28.0, r_multiple=0.5)
    _op(db, 1, 3226, 100.0)
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        body = TestClient(app).get("/api/etoro/diario").json()
    finally:
        app.dependency_overrides.clear()
    op = body["operazioni"][0]
    assert (op["ticker"], op["alert_id"], op["r_reale"]) == ("SOXL", a.id, 1.5)
    assert body["tutte"]["n"] == 1 and body["anni"][0]["profitto_eur"] is None
