"""Il ricalcolo del prezzo di prima emissione sugli alert storici."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

from app.models import Alert, OhlcvDaily, Stock
from app.scripts.backfill_first_price import CHIAVE, MARCATORE_VECCHIO, riempi


def _titolo(db: Session, ticker: str = "AAA") -> Stock:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=f"{ticker} Corp", country="US")
    db.add(s)
    db.flush()
    return s


def _barre(db: Session, s: Stock, righe: list[tuple[str, float]]) -> None:
    for d, cl in righe:
        db.add(OhlcvDaily(stock_id=s.id, date=date.fromisoformat(d),
                          open=cl, high=cl, low=cl, close=cl, volume=1000))
    db.flush()


def _alert(db: Session, s: Stock, *, prima_emissione: str | None,
           scattato: str, prezzo: float, extra: dict | None = None) -> Alert:
    snap: dict = {"tone": "bull", **(extra or {})}
    if prima_emissione:
        snap["first_emitted_at"] = f"{prima_emissione}T23:30:00+00:00"
    a = Alert(stock_id=s.id, signal_name="gap_and_go",
              signal_date=date.fromisoformat(scattato),
              triggered_at=datetime.fromisoformat(scattato).replace(tzinfo=UTC),
              trigger_price=prezzo, snapshot=json.dumps(snap))
    db.add(a)
    db.flush()
    return a


def test_il_prezzo_ricostruito_e_la_chiusura_alla_prima_emissione(db: Session) -> None:
    """Il caso FICO: il box mostrava la chiusura dell'11 accanto a una data
    segnale del 4."""
    s = _titolo(db)
    _barre(db, s, [("2026-09-03", 1118.93), ("2026-09-04", 932.26),
                   ("2026-09-11", 985.39), ("2026-09-14", 1001.50)])
    _alert(db, s, prima_emissione="2026-09-04", scattato="2026-09-14", prezzo=985.39)

    riempiti, saltati, _ = riempi(db)
    assert (riempiti, saltati) == (1, 0)
    snap = json.loads(db.query(Alert).one().snapshot)
    assert snap[CHIAVE] == pytest.approx(932.26)
    assert MARCATORE_VECCHIO not in snap


def test_un_first_price_gia_presente_NON_viene_toccato(db: Session) -> None:
    """⚠️ Quelli veri, fissati dal motore alla creazione, non si sovrascrivono
    con una ricostruzione: sarebbe rimpiazzare una misura con una stima."""
    s = _titolo(db)
    _barre(db, s, [("2026-09-04", 932.26)])
    _alert(db, s, prima_emissione="2026-09-04", scattato="2026-09-14",
           prezzo=985.39, extra={CHIAVE: 777.0})

    assert riempi(db)[0] == 0
    snap = json.loads(db.query(Alert).one().snapshot)
    assert snap[CHIAVE] == pytest.approx(777.0)
    assert MARCATORE_VECCHIO not in snap


def test_senza_first_emitted_at_si_ripiega_su_triggered_at(db: Session) -> None:
    s = _titolo(db)
    _barre(db, s, [("2026-09-04", 932.26), ("2026-09-11", 985.39)])
    _alert(db, s, prima_emissione=None, scattato="2026-09-11", prezzo=985.39)

    assert riempi(db)[0] == 1
    assert json.loads(db.query(Alert).one().snapshot)[CHIAVE] == pytest.approx(985.39)


def test_senza_una_barra_utile_si_salta_invece_di_inventare(db: Session) -> None:
    s = _titolo(db)
    _barre(db, s, [("2026-09-11", 985.39)])   # tutte DOPO la prima emissione
    _alert(db, s, prima_emissione="2026-09-04", scattato="2026-09-14", prezzo=985.39)

    riempiti, saltati, _ = riempi(db)
    assert (riempiti, saltati) == (0, 1)
    assert CHIAVE not in json.loads(db.query(Alert).one().snapshot)


def test_trigger_price_non_viene_MAI_toccato(db: Session) -> None:
    """Sono due numeri diversi: `trigger_price` descrive il segnale VIVO ed e'
    giusto che sia avanzato."""
    s = _titolo(db)
    _barre(db, s, [("2026-09-04", 932.26), ("2026-09-11", 985.39)])
    a = _alert(db, s, prima_emissione="2026-09-04", scattato="2026-09-14", prezzo=985.39)

    riempi(db)
    assert float(a.trigger_price) == pytest.approx(985.39)


def test_la_sola_lettura_non_scrive(db: Session, monkeypatch) -> None:
    from app.core import db as db_module
    from app.scripts import backfill_first_price

    s = _titolo(db)
    _barre(db, s, [("2026-09-04", 932.26)])
    _alert(db, s, prima_emissione="2026-09-04", scattato="2026-09-14", prezzo=985.39)
    db.commit()

    monkeypatch.setattr(backfill_first_price, "SessionLocal", db_module.SessionLocal)
    backfill_first_price.run(applica=False)

    assert CHIAVE not in json.loads(db.query(Alert).one().snapshot)


def test_con_applica_scrive(db: Session, monkeypatch) -> None:
    from app.core import db as db_module
    from app.scripts import backfill_first_price

    s = _titolo(db)
    _barre(db, s, [("2026-09-04", 932.26)])
    _alert(db, s, prima_emissione="2026-09-04", scattato="2026-09-14", prezzo=985.39)
    db.commit()

    monkeypatch.setattr(backfill_first_price, "SessionLocal", db_module.SessionLocal)
    backfill_first_price.run(applica=True)

    assert json.loads(db.query(Alert).one().snapshot)[CHIAVE] == pytest.approx(932.26)


def test_main_inoltra_il_flag(monkeypatch) -> None:
    import sys

    from app.scripts import backfill_first_price

    visti: list[bool] = []
    monkeypatch.setattr(backfill_first_price, "run", lambda applica=False: visti.append(applica))
    monkeypatch.setattr(sys, "argv", ["backfill_first_price"])
    backfill_first_price.main()
    monkeypatch.setattr(sys, "argv", ["backfill_first_price", "--applica"])
    backfill_first_price.main()
    assert visti == [False, True]


def test_il_vecchio_marcatore_viene_TOLTO_dove_c_e(db: Session) -> None:
    """La base non porta piu' la distinzione fra un prezzo fissato dal motore e
    uno ricalcolato: una passata ripulisce gli snapshot che la portano ancora.

    ⚠️ Il controllo negativo e' il conteggio: senza, un `pop` che non trova
    niente e un `pop` che non viene mai eseguito sono indistinguibili.
    """
    s = _titolo(db)
    _barre(db, s, [("2026-09-04", 932.26)])
    _alert(db, s, prima_emissione="2026-09-04", scattato="2026-09-14",
           prezzo=985.39, extra={CHIAVE: 932.26, MARCATORE_VECCHIO: True})

    riempiti, _, ripuliti = riempi(db)
    assert (riempiti, ripuliti) == (0, 1)
    snap = json.loads(db.query(Alert).one().snapshot)
    assert MARCATORE_VECCHIO not in snap
    assert snap[CHIAVE] == pytest.approx(932.26)   # il valore resta
