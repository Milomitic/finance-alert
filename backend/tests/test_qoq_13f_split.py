"""Uno split fra due 13F non e' un acquisto (CRWD 4:1, giugno 2026)."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Institutional, InstitutionalFiling, InstitutionalHolding, OhlcvDaily, Stock
from app.scripts import ricalcola_qoq_13f
from app.services import institutional_service as svc

PRIMA = date(2026, 3, 31)
DOPO = date(2026, 6, 30)


def _barra(db: Session, stock: Stock, giorno: date, close: float) -> None:
    db.add(OhlcvDaily(stock_id=stock.id, date=giorno, open=close, high=close, low=close, close=close, volume=1))


def _scenario(db: Session, *, chiusura_prima: float, chiusura_dopo: float | None):
    s = Stock(ticker="CRWD", exchange="NASDAQ", name="CrowdStrike")
    f = Institutional(slug="blk", name="BlackRock", type="institutional", source="sec_13f")
    db.add_all([s, f])
    db.flush()
    # Barre RETTIFICATE: dopo uno split il prezzo di prima e' gia' diviso.
    _barra(db, s, PRIMA, chiusura_prima)
    if chiusura_dopo is not None:
        _barra(db, s, DOPO, chiusura_dopo)
    d1 = InstitutionalFiling(institutional_id=f.id, period_end_date=PRIMA)
    d2 = InstitutionalFiling(institutional_id=f.id, period_end_date=DOPO)
    db.add_all([d1, d2])
    db.flush()
    # 13F: 100 quote a 400 $ prima, 410 quote a 100 $ dopo.
    db.add(InstitutionalHolding(filing_id=d1.id, ticker="CRWD", shares=100, value_usd=40_000, portfolio_pct=0.3))
    h = InstitutionalHolding(filing_id=d2.id, ticker="CRWD", shares=410, value_usd=41_000, portfolio_pct=0.36)
    db.add(h)
    db.flush()
    return f, d2, h


def test_lo_split_non_e_un_acquisto(db: Session) -> None:
    f, d2, h = _scenario(db, chiusura_prima=100.0, chiusura_dopo=100.0)
    svc.compute_qoq_deltas(db, f, d2)
    assert h.qoq_change_pct == pytest.approx(2.5)   # 410 contro 400, non contro 100
    assert h.action == "add"
    assert h.qoq_change_shares == 10


def test_un_crollo_vero_non_e_uno_split(db: Session) -> None:
    # Le barre rettificate dicono che il titolo e' sceso davvero da 400 a 100.
    f, d2, h = _scenario(db, chiusura_prima=400.0, chiusura_dopo=100.0)
    svc.compute_qoq_deltas(db, f, d2)
    assert h.qoq_change_pct == pytest.approx(310.0)


def test_senza_barre_non_si_corregge(db: Session) -> None:
    f, d2, h = _scenario(db, chiusura_prima=100.0, chiusura_dopo=None)
    svc.compute_qoq_deltas(db, f, d2)
    assert h.qoq_change_pct == pytest.approx(310.0)


def test_il_ricalcolo_ripara_l_archivio_ed_e_idempotente(db: Session) -> None:
    f, d2, h = _scenario(db, chiusura_prima=100.0, chiusura_dopo=100.0)
    # L'archivio com'era: lo split letto come acquisto, piu' un'uscita fantasma.
    h.action, h.qoq_change_pct = "add", 310.0
    db.add(InstitutionalHolding(filing_id=d2.id, ticker="OLD", shares=0, value_usd=0, action="sold_out"))
    db.commit()
    cambi = ricalcola_qoq_13f.ricalcola(db, applica=True)
    assert cambi[("add", "add")] == 1
    righe = db.execute(select(InstitutionalHolding).where(InstitutionalHolding.filing_id == d2.id)).scalars().all()
    assert [(r.ticker, r.qoq_change_pct) for r in righe] == [("CRWD", pytest.approx(2.5))]
    # Un secondo giro non duplica niente e non cambia niente.
    assert sum(ricalcola_qoq_13f.ricalcola(db, applica=True).values()) == 0
    assert len(db.execute(select(InstitutionalHolding).where(InstitutionalHolding.filing_id == d2.id)).all()) == 1


def test_il_rapporto_non_scrive(db: Session) -> None:
    f, d2, h = _scenario(db, chiusura_prima=100.0, chiusura_dopo=100.0)
    h.action, h.qoq_change_pct = "add", 310.0
    db.commit()
    cambi = ricalcola_qoq_13f.ricalcola(db, applica=False)
    assert cambi[("add", "add")] == 1
    db.expire_all()
    assert db.get(InstitutionalHolding, h.id).qoq_change_pct == pytest.approx(310.0)


def test_il_fattore_riconosce_anche_il_raggruppamento() -> None:
    prima = InstitutionalHolding(shares=1000, value_usd=10_000)   # 10 $
    dopo = InstitutionalHolding(shares=100, value_usd=10_000)     # 100 $, raggruppamento 1:10
    assert svc._fattore_split(prima, dopo, 100.0, 100.0) == pytest.approx(0.1)
    assert svc._fattore_split(prima, dopo, None, 100.0) == 1.0


def test_il_comando_stampa_il_rapporto_senza_scrivere(db: Session, monkeypatch, capsys) -> None:
    import contextlib
    import sys

    import app.core.db as core_db

    f, d2, h = _scenario(db, chiusura_prima=100.0, chiusura_dopo=100.0)
    h.action, h.qoq_change_pct = "add", 310.0
    db.commit()
    monkeypatch.setattr(core_db, "SessionLocal", lambda: contextlib.nullcontext(db))
    monkeypatch.setattr(sys, "argv", ["ricalcola_qoq_13f"])
    ricalcola_qoq_13f.main()
    out = capsys.readouterr().out
    assert "add -> add: 1" in out
    assert "solo rapporto" in out
