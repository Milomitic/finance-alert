"""Il riempimento all'indietro delle variabili dell'ingresso.

Due rami, e la differenza e' il punto: un alert mai rivisto porta ancora lo
snapshot della nascita, quindi Forza e fattori si copiano; per uno rivisto NON
si ricavano — sarebbero l'uscita del codice di oggi spacciata per quella di
allora. Il contesto invece si calcola per tutti, dalle sole barre fino alla
prima emissione.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import Alert, OhlcvDaily, Stock
from app.scripts.backfill_variabili_emissione import riempi


def _titolo(db: Session) -> Stock:
    s = Stock(ticker="VAR", exchange="NASDAQ", name="Var Corp", country="US")
    db.add(s)
    db.flush()
    return s


def _barre(db: Session, s: Stock, prima: date, chiusure: list[float]) -> None:
    for i, c in enumerate(chiusure):
        db.add(OhlcvDaily(stock_id=s.id, date=prima + timedelta(days=i), open=c,
                          high=c * 1.01, low=c * 0.99, close=c, volume=1000))
    db.flush()


def _alert(db: Session, s: Stock, *, nascita: date, snap: dict) -> Alert:
    snap = {"tone": "bull", "first_emitted_at": f"{nascita.isoformat()}T23:30:00+00:00", **snap}
    a = Alert(stock_id=s.id, signal_name="structure_break", signal_date=nascita,
              triggered_at=datetime.combine(nascita, datetime.min.time(), tzinfo=UTC),
              trigger_price=100.0, snapshot=json.dumps(snap))
    db.add(a)
    db.flush()
    return a


_PRIMA = date(2026, 1, 1)


def test_un_alert_mai_rivisto_copia_forza_fattori_e_provenienza(db: Session) -> None:
    s = _titolo(db)
    _barre(db, s, _PRIMA, [100.0 + i for i in range(40)])
    _alert(db, s, nascita=_PRIMA + timedelta(days=30),
           snap={"strength": 72, "factors": {"break_decisiveness": 0.4},
                 "provenance": {"regole": "x"}})

    rapporto = riempi(db)

    snap = json.loads(db.query(Alert).one().snapshot)
    assert snap["first_strength"] == 72
    assert snap["first_factors"] == {"break_decisiveness": 0.4}
    assert snap["first_provenance"] == {"regole": "x"}
    assert rapporto["forza_fattori_copiati"] == 1


def test_un_alert_rivisto_NON_riceve_la_forza_di_oggi(db: Session) -> None:
    """⚠️ Il ramo che conta. La Forza di un alert rivisto e' quella dell'ultima
    revisione: copiarla la spaccerebbe per quella dell'ingresso, cioe' il
    difetto che i campi esistono per chiudere."""
    s = _titolo(db)
    _barre(db, s, _PRIMA, [100.0 + i for i in range(40)])
    _alert(db, s, nascita=_PRIMA + timedelta(days=30),
           snap={"strength": 88, "factors": {"x": 1.0}, "amend_count": 5})

    rapporto = riempi(db)

    snap = json.loads(db.query(Alert).one().snapshot)
    assert "first_strength" not in snap
    assert "first_factors" not in snap
    # Il contesto invece si': e' una funzione delle barre.
    assert "first_contesto" in snap
    assert rapporto["rivisti_senza_forza"] == 1


def test_il_contesto_guarda_solo_le_barre_fino_alla_nascita(db: Session) -> None:
    """Niente dal futuro: dopo la nascita il titolo raddoppia, e il contesto
    non deve saperlo."""
    s = _titolo(db)
    chiusure = [100.0] * 30 + [101.0] + [200.0] * 10
    _barre(db, s, _PRIMA, chiusure)
    _alert(db, s, nascita=_PRIMA + timedelta(days=30), snap={"strength": 60})

    riempi(db)

    ctx = json.loads(db.query(Alert).one().snapshot)["first_contesto"]
    # L'ultima barra vista e' quella a 101: +1% sul giorno prima.
    assert ctx["ret_1"] == pytest.approx(0.01, rel=1e-4)


def test_i_campi_gia_presenti_non_vengono_toccati(db: Session) -> None:
    """Idempotente: un alert nato dopo lo scan nuovo, o gia' riempito, resta
    com'e' — e una seconda passata non scrive niente."""
    s = _titolo(db)
    _barre(db, s, _PRIMA, [100.0 + i for i in range(40)])
    _alert(db, s, nascita=_PRIMA + timedelta(days=30),
           snap={"strength": 72, "first_strength": 41, "first_factors": {"a": 1},
                 "first_contesto": {"versione": "1", "ret_1": 0.5}})

    rapporto = riempi(db)

    snap = json.loads(db.query(Alert).one().snapshot)
    assert snap["first_strength"] == 41
    assert snap["first_contesto"] == {"versione": "1", "ret_1": 0.5}
    assert rapporto["forza_fattori_copiati"] == 0
    assert rapporto["contesto_calcolato"] == 0


def test_la_sola_lettura_non_scrive(db: Session, monkeypatch) -> None:
    """Il monkeypatch di SessionLocal non e' una formalita': lo script lo importa
    al caricamento, quindi senza scriverebbe nel database di SVILUPPO."""
    from app.core import db as db_module
    from app.scripts import backfill_variabili_emissione

    s = _titolo(db)
    _barre(db, s, _PRIMA, [100.0 + i for i in range(40)])
    _alert(db, s, nascita=_PRIMA + timedelta(days=30), snap={"strength": 72})
    db.commit()

    monkeypatch.setattr(backfill_variabili_emissione, "SessionLocal", db_module.SessionLocal)
    backfill_variabili_emissione.run(applica=False)

    assert "first_strength" not in json.loads(db.query(Alert).one().snapshot)


def test_con_applica_scrive(db: Session, monkeypatch) -> None:
    from app.core import db as db_module
    from app.scripts import backfill_variabili_emissione

    s = _titolo(db)
    _barre(db, s, _PRIMA, [100.0 + i for i in range(40)])
    _alert(db, s, nascita=_PRIMA + timedelta(days=30), snap={"strength": 72})
    db.commit()

    monkeypatch.setattr(backfill_variabili_emissione, "SessionLocal", db_module.SessionLocal)
    backfill_variabili_emissione.run(applica=True)

    snap = json.loads(db.query(Alert).one().snapshot)
    assert snap["first_strength"] == 72
    assert "first_contesto" in snap


def test_main_inoltra_il_flag(monkeypatch) -> None:
    """Un `--applica` non inoltrato produce uno script che gira, stampa un
    rapporto, esce con zero e non scrive MAI."""
    import sys

    from app.scripts import backfill_variabili_emissione

    visti: list[bool] = []
    monkeypatch.setattr(backfill_variabili_emissione, "run",
                        lambda applica=False: visti.append(applica))
    monkeypatch.setattr(sys, "argv", ["backfill_variabili_emissione"])
    backfill_variabili_emissione.main()
    monkeypatch.setattr(sys, "argv", ["backfill_variabili_emissione", "--applica"])
    backfill_variabili_emissione.main()
    assert visti == [False, True]
