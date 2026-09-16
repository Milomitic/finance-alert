"""Il prefiltro della maturazione non cambia NESSUN esito: cambia cosa si carica.

Misurato il 2026-09-16: 3.724 alert in attesa su 932 titoli, e oltre 900 titoli
`_load_stock_closes` legge l'intera `ohlcv_daily` (2,48M righe) a ogni fine
scansione per scoprire, alert per alert, che l'orizzonte non e' trascorso.
`_maturable_alert_ids` dice la stessa condizione di `_label` in SQL.

L'affermazione da difendere e' l'EQUIVALENZA, quindi il test principale esegue
la maturazione due volte sullo stesso database — col prefiltro e senza — e
pretende righe identiche, confini compresi.
"""
import json
import random
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import Alert, OhlcvDaily, SignalOutcome, Stock
from app.services import signal_outcome_service as sos

H = 5
_CAMPI = ("alert_id", "signal_date", "horizon_days", "entry_close", "forward_close",
          "fwd_return", "universe_mean_fwd", "mkt_neutral_excess", "abs_hit",
          "mkt_neutral_hit", "regime_at_signal")


def _feriali(inizio: date, n: int) -> list[date]:
    out, d = [], inizio
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


@pytest.fixture
def universo(db, monkeypatch):
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: H)
    monkeypatch.setattr(sos, "_MIN_UNIVERSE_PER_DATE", 2)
    rng = random.Random(20260916)
    giorni = _feriali(date(2026, 6, 1), 40)
    attesi_maturabili = set()
    for k in range(6):
        s = Stock(ticker=f"PF{k}", exchange="NYSE", name=f"PF{k}", country="US")
        db.add(s)
        db.flush()
        # Il titolo 5 ha la serie FERMA a 20 barre: i suoi alert recenti non
        # matureranno mai.
        n_barre = 20 if k == 5 else len(giorni)
        prezzo = 50.0 + k
        for g in giorni[:n_barre]:
            prezzo *= 1 + rng.uniform(-0.03, 0.03)
            db.add(OhlcvDaily(stock_id=s.id, date=g, open=prezzo, high=prezzo,
                              low=prezzo, close=prezzo, volume=1000))
        # Posizioni del trigger: lontano, CONFINE esatto (H+1 barre, maturabile),
        # CONFINE meno uno (H barre, no), ultima barra, e un sabato fra due barre.
        for idx in (3, n_barre - H - 1, n_barre - H, n_barre - 1):
            a = Alert(stock_id=s.id, signal_name="trend_pullback", signal_date=giorni[idx],
                      trigger_price=prezzo,
                      snapshot=json.dumps({"tone": rng.choice(["bull", "bear"])}))
            db.add(a)
            db.flush()
            if n_barre - idx >= H + 1:
                attesi_maturabili.add(a.id)
        sabato = giorni[10] + timedelta(days=(5 - giorni[10].weekday()) % 7)
        a = Alert(stock_id=s.id, signal_name="trend_pullback", signal_date=sabato,
                  trigger_price=prezzo, snapshot=json.dumps({"tone": "bull"}))
        db.add(a)
        db.flush()
        if sum(1 for g in giorni[:n_barre] if g >= sabato) >= H + 1:
            attesi_maturabili.add(a.id)
    db.commit()
    return attesi_maturabili


def _righe(db) -> list[tuple]:
    return sorted(
        tuple(getattr(r, c) for c in _CAMPI)
        for r in db.execute(select(SignalOutcome)).scalars()
    )


def test_gli_esiti_sono_IDENTICI_con_e_senza_prefiltro(db, universo, monkeypatch) -> None:
    con = sos.mature_outcomes(db, commit=False)
    righe_con = _righe(db)
    db.rollback()
    assert _righe(db) == []

    tutti = {a.id for a in db.execute(select(Alert)).scalars()}
    monkeypatch.setattr(sos, "_maturable_alert_ids", lambda _db, _c: tutti)
    senza = sos.mature_outcomes(db, commit=False)
    righe_senza = _righe(db)

    assert con == senza == len(universo)
    assert righe_con == righe_senza
    # Il controllo che rende il confronto non vuoto: ci sono sia esiti sia
    # alert rimasti fuori, compreso il confine esatto.
    assert 0 < con < len(tutti)


def test_il_prefiltro_seleziona_esattamente_il_confine(db, universo) -> None:
    from app.services.signal_outcome_service import _maturable_alert_ids

    condizioni = (Alert.signal_name.is_not(None), Alert.signal_date.is_not(None))
    assert _maturable_alert_ids(db, condizioni) == universo


def test_i_titoli_senza_alert_maturabili_non_si_caricano(db, universo, monkeypatch) -> None:
    caricati: list[set[int]] = []
    originale = sos._load_stock_closes

    def spia(db_, ids):
        caricati.append(set(ids))
        return originale(db_, ids)

    monkeypatch.setattr(sos, "_load_stock_closes", spia)
    ferma = db.execute(select(Stock.id).where(Stock.ticker == "PF5")).scalar_one()
    sos.mature_outcomes(db, commit=False)
    assert len(caricati) == 1
    assert ferma in caricati[0]          # ha alert vecchi che maturano
    db.rollback()

    # Senza nessun alert maturabile, nessuna serie si carica.
    for a in db.execute(select(Alert).where(Alert.id.in_(universo))).scalars():
        db.delete(a)
    db.commit()
    caricati.clear()
    assert sos.mature_outcomes(db) == 0
    assert caricati == []
