"""Dopo una riparazione di base lo script ricalcola da solo il punteggio
tecnico: prima lo chiedeva a chi lo eseguiva, e per un titolo tagliato sotto
le 30 barre il punteggio vecchio restava per sempre (CTVA, 2026-10-06)."""
from datetime import date, timedelta

from sqlalchemy import delete, select

from app.models import OhlcvDaily, Stock
from app.models.technical_score import TechnicalScore
from app.scripts.repair_price_basis import _ricalcola_tecnico
from app.services import technical_score_service


def _titolo(db, ticker: str, barre: int) -> Stock:
    s = Stock(ticker=ticker, exchange="NYSE", name=ticker, country="US")
    db.add(s)
    db.flush()
    inizio = date.today() - timedelta(days=barre)
    for i in range(barre):
        p = 50.0 + i * 0.3
        db.add(OhlcvDaily(stock_id=s.id, date=inizio + timedelta(days=i),
                          open=p, high=p + 1, low=p - 1, close=p, volume=1000.0))
    db.commit()
    return s


def test_ricalcola_chi_ha_storia_e_toglie_chi_non_ne_ha(db, capsys) -> None:
    sano = _titolo(db, "SANO", 150)
    corto = _titolo(db, "CORTO", 150)
    # Il punteggio vecchio, calcolato sulla storia lunga; poi la storia si
    # accorcia a tre barre, come CTVA dopo il taglio.
    assert technical_score_service.recompute_one(db, corto.id) is not None
    tieni = date.today() - timedelta(days=3)
    db.execute(delete(OhlcvDaily).where(OhlcvDaily.stock_id == corto.id, OhlcvDaily.date < tieni))
    db.commit()

    _ricalcola_tecnico(db, [sano, corto])

    righe = {sid for (sid,) in db.execute(select(TechnicalScore.stock_id))}
    assert sano.id in righe
    assert corto.id not in righe
    out = capsys.readouterr().out
    assert "SANO" in out and "tolto: storia troppo corta" in out


def test_un_errore_su_un_titolo_non_ferma_gli_altri(db, capsys, monkeypatch) -> None:
    a, b = _titolo(db, "AAA", 150), _titolo(db, "BBB", 150)
    vero = technical_score_service.recompute_one

    def finto(db_, sid):
        if sid == a.id:
            raise RuntimeError("boom")
        return vero(db_, sid)

    monkeypatch.setattr(technical_score_service, "recompute_one", finto)
    _ricalcola_tecnico(db, [a, b])
    out = capsys.readouterr().out
    assert "non ricalcolato: boom" in out
    assert db.execute(select(TechnicalScore).where(TechnicalScore.stock_id == b.id)).first() is not None
