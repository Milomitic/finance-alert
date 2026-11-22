"""Le operazioni dei fondi nell'ultimo trimestre, per spostamento di peso."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import Institutional, InstitutionalFiling, InstitutionalHolding
from app.services import operazioni_fondi_service as svc

TRIM = date.today() - timedelta(days=40)
PREC = date.today() - timedelta(days=130)


def _fondo(db: Session, slug: str) -> Institutional:
    r = Institutional(slug=slug, name=slug.upper(), type="superinvestor", source="dataroma")
    db.add(r)
    db.flush()
    return r


def _dich(db: Session, f: Institutional, periodo: date) -> InstitutionalFiling:
    r = InstitutionalFiling(institutional_id=f.id, period_end_date=periodo)
    db.add(r)
    db.flush()
    return r


def _riga(db, d, ticker, pct, action=None, qoq=None, valore=1_000_000):
    db.add(InstitutionalHolding(filing_id=d.id, ticker=ticker, company_name=ticker, shares=100,
                                value_usd=valore, portfolio_pct=pct, action=action, qoq_change_pct=qoq))
    db.flush()


def test_ordina_per_spostamento_di_peso_non_per_dollari(db: Session) -> None:
    grande = _fondo(db, "indice")
    p = _dich(db, grande, PREC)
    _riga(db, p, "NVDA", 6.00)
    c = _dich(db, grande, TRIM)
    _riga(db, c, "NVDA", 6.02, "add", 0.5, valore=400_000_000_000)

    concentrato = _fondo(db, "concentrato")
    p2 = _dich(db, concentrato, PREC)
    _riga(db, p2, "OXY", 4.0)
    _riga(db, p2, "KO", 9.0)
    c2 = _dich(db, concentrato, TRIM)
    _riga(db, c2, "OXY", 12.0, "add", 150.0, valore=5_000_000)
    _riga(db, c2, "AAPL", 3.0, "new", valore=1_000_000)
    _riga(db, c2, "KO", 0.0, "sold_out", -100.0, valore=0)

    r = svc.operazioni_ultimo_trimestre(db)
    assert r.trimestre == TRIM
    assert r.fondi == 2
    assert [(o.ticker, o.delta_pp) for o in r.operazioni] == [
        ("KO", -9.0), ("OXY", 8.0), ("AAPL", 3.0), ("NVDA", 0.02),
    ]
    ko = r.operazioni[0]
    assert (ko.peso_prima, ko.peso_dopo, ko.action) == (9.0, 0.0, "sold_out")


def test_senza_riga_precedente_il_peso_prima_si_stima_dal_cambio_di_quote(db: Session) -> None:
    f = _fondo(db, "dataroma")
    _dich(db, f, PREC)
    c = _dich(db, f, TRIM)
    _riga(db, c, "MSFT", 6.0, "add", 50.0)
    o = svc.operazioni_ultimo_trimestre(db).operazioni[0]
    assert o.peso_prima == 4.0
    assert o.delta_pp == 2.0


def test_un_fondo_senza_dichiarazione_precedente_non_entra(db: Session) -> None:
    f = _fondo(db, "primo")
    c = _dich(db, f, TRIM)
    _riga(db, c, "AMD", 20.0, "new")
    r = svc.operazioni_ultimo_trimestre(db)
    assert r.operazioni == []


def test_solo_il_trimestre_piu_recente(db: Session) -> None:
    f = _fondo(db, "uno")
    vecchia = _dich(db, f, PREC - timedelta(days=90))
    _riga(db, vecchia, "X", 1.0)
    p = _dich(db, f, PREC)
    _riga(db, p, "X", 30.0, "add", 100.0)
    c = _dich(db, f, TRIM)
    _riga(db, c, "Y", 2.0, "new")
    r = svc.operazioni_ultimo_trimestre(db)
    assert [o.ticker for o in r.operazioni] == ["Y"]


def test_vuoto_senza_dichiarazioni(db: Session) -> None:
    r = svc.operazioni_ultimo_trimestre(db)
    assert (r.trimestre, r.fondi, r.operazioni) == (None, 0, [])

