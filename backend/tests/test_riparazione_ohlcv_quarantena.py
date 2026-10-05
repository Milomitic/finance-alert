"""Il job di riparazione rispetta la quarantena dei ticker morti.

Prima la applicava solo la scansione: un titolo delistato con storia restava
«indietro» per sempre e si riscaricava dodici volte al giorno."""
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core import db as core_db
from app.models import Stock
from app.models.ohlcv import OhlcvDaily
from app.scheduler.jobs import repair_ohlcv_gaps as job
from app.services.ohlcv_service import FetchResult

OGGI = date.today()


def _titolo(db: Session, ticker: str, ultima: date, *, streak: int = 0, ultimo_vuoto: date | None = None) -> Stock:
    s = Stock(ticker=ticker, exchange="NYSE", name=ticker, ohlcv_nodata_streak=streak,
              ohlcv_last_nodata_at=ultimo_vuoto)
    db.add(s)
    db.flush()
    db.add(OhlcvDaily(stock_id=s.id, date=ultima, open=1, high=1, low=1, close=1, volume=1))
    db.commit()
    return s


@pytest.fixture
def chiesti(db: Session, monkeypatch) -> list[str]:
    out: list[str] = []

    def finto(_db, chunk, period=None, start=None):
        out.extend(s.ticker for s in chunk)
        return FetchResult(stocks_succeeded=len(chunk))

    monkeypatch.setattr(core_db, "SessionLocal", lambda: db)
    monkeypatch.setattr(job, "fetch_and_upsert", finto)
    monkeypatch.setattr(job.yfinance_health, "is_open", lambda lane: False)
    monkeypatch.setattr(job.app_metrics, "refresh_basis_breaks_gauge", lambda _db: 0)
    return out


def test_un_morto_in_quarantena_non_si_riscarica(db: Session, chiesti) -> None:
    _titolo(db, "VIVO", OGGI)
    _titolo(db, "INDIETRO", OGGI - timedelta(days=20))
    _titolo(db, "MORTO", OGGI - timedelta(days=90), streak=410, ultimo_vuoto=OGGI)
    job.run_repair_ohlcv_gaps()
    assert chiesti == ["INDIETRO"]


def test_il_risondaggio_settimanale_resta(db: Session, chiesti) -> None:
    """Controllo negativo: un morto non sondato da una settimana si riprova,
    perche' un ticker puo' tornare vivo."""
    _titolo(db, "VIVO", OGGI)
    _titolo(db, "MORTO", OGGI - timedelta(days=90), streak=410, ultimo_vuoto=OGGI - timedelta(days=8))
    job.run_repair_ohlcv_gaps()
    assert chiesti == ["MORTO"]
