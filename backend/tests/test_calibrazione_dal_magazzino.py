"""La Calibrazione legge il magazzino degli esiti, TUTTO.

Segnalato dall'utente il 2026-09-16: Diagnostica diceva «esiti maturati: 3»
mentre `signal_outcomes` ne conteneva 4.830. Il pannello ricalcolava i
rendimenti solo sugli alert NON ARCHIVIATI, e l'archiviazione segue l'eta' come
la maturazione: e' il filtro che il 2026-09-05 nascondeva 4.861 esiti su 4.880
agli altri tre consumatori del magazzino.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.models import Alert, SignalOutcome, Stock
from app.services import rule_performance_service as rps


def _esito(db: Session, i: int, *, archiviato: bool, horizon: int = 21, strength: int = 72,
           mkt_hit: int | None = 1, abs_hit: int = 1, detector: str = "trend_pullback",
           fwd: float = 0.03, orizzonte_dichiarato: str = "medium") -> None:
    s = Stock(ticker=f"C{i}", exchange="NASDAQ", name=f"C{i}", country="US")
    db.add(s)
    db.flush()
    a = Alert(
        stock_id=s.id, signal_name=detector, signal_date=date(2026, 6, 1),
        trigger_price=10.0,
        snapshot=json.dumps({"tone": "bull", "strength": strength, "horizon": orizzonte_dichiarato}),
        archived_at=datetime(2026, 7, 1, tzinfo=UTC) if archiviato else None,
    )
    db.add(a)
    db.flush()
    db.add(SignalOutcome(
        alert_id=a.id, stock_id=s.id, detector=detector, signal_date=date(2026, 6, 1),
        tone="bull", horizon_days=horizon, entry_close=10.0, forward_close=10.0 * (1 + fwd),
        fwd_return=fwd, universe_mean_fwd=0.0, mkt_neutral_excess=fwd,
        abs_hit=abs_hit, mkt_neutral_hit=mkt_hit, regime_at_signal="bull",
        strength=strength, probability=50,
    ))
    db.commit()


def test_gli_esiti_di_alert_archiviati_si_contano(db: Session) -> None:
    for i in range(9):
        _esito(db, i, archiviato=True)
    _esito(db, 99, archiviato=False)

    c = rps.compute_calibration(db, window=21)
    # Col vecchio filtro sarebbe stato 1.
    assert c.total == 10
    assert sum(b.count for b in c.by_confidence) == 10


def test_l_hit_e_market_neutral_non_assoluto(db: Session) -> None:
    # Salito in assoluto, ma meno dell'universo: per l'app NON e' un colpo.
    _esito(db, 1, archiviato=False, abs_hit=1, mkt_hit=0)
    c = rps.compute_calibration(db, window=21)
    fascia = next(b for b in c.by_confidence if b.label == "70-79")
    assert fascia.hit_rate == 0.0


def test_un_esito_senza_benchmark_conta_ma_non_e_un_fallimento(db: Session) -> None:
    _esito(db, 1, archiviato=False, mkt_hit=1)
    _esito(db, 2, archiviato=False, mkt_hit=None)
    fascia = next(b for b in rps.compute_calibration(db, window=21).by_confidence
                  if b.label == "70-79")
    assert fascia.count == 2
    assert fascia.hit_rate == 1.0


def test_l_orizzonte_si_aggancia_a_quelli_del_magazzino(db: Session) -> None:
    _esito(db, 1, archiviato=False, horizon=21)
    _esito(db, 2, archiviato=False, horizon=5)
    assert rps.snap_horizon(20) == 21
    assert rps.snap_horizon(10) == 5
    c = rps.compute_calibration(db, window=20)
    assert (c.window, c.total) == (21, 1)


def test_natura_orizzonte_e_rendimento_in_percento(db: Session) -> None:
    _esito(db, 1, archiviato=False, detector="candle_reversal", fwd=0.05, orizzonte_dichiarato="short")
    c = rps.compute_calibration(db, window=21)
    inversione = next(b for b in c.by_nature if b.label == "inversione")
    breve = next(b for b in c.by_horizon if b.label == "short")
    assert inversione.count == 1 and breve.count == 1
    assert round(inversione.mean_pct, 6) == 5.0
