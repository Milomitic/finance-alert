"""I titoli fermi del catalogo, nella Diagnostica, e la verifica sulla fonte."""
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Index, OhlcvDaily, Position, Stock, StockIndex, User
from app.models.preferito import Preferito
from app.services import catalogo_fermi_service as cf
from app.services.ohlcv_service import QUARANTINE_STREAK


@pytest.fixture
def catalogo_db(db: Session) -> dict[str, Stock]:
    out = {}
    specs = [
        # ticker, streak, ultima barra, settore, capitalizzazione
        ("FERMO", QUARANTINE_STREAK + 5, date(2026, 5, 7), "Energy", 10),
        ("MAIVISTO", QUARANTINE_STREAK, None, None, None),
        ("VIVO", 0, date(2026, 9, 28), "Tech", None),
        ("QUASI", QUARANTINE_STREAK - 1, date(2026, 9, 20), "", 5),
    ]
    for t, streak, ultima, settore, cap in specs:
        s = Stock(ticker=t, exchange="NASDAQ", name=f"{t} Inc.", ohlcv_nodata_streak=streak,
                  ohlcv_last_nodata_at=datetime(2026, 9, 29, 6, tzinfo=UTC) if streak else None,
                  sector=settore, market_cap=cap)
        db.add(s)
        db.flush()
        out[t] = s
        if ultima:
            for i in range(3):
                d = ultima - timedelta(days=i)
                db.add(OhlcvDaily(stock_id=s.id, date=d, open=1, high=1, low=1, close=1, volume=1))
    idx = Index(code="SP500", name="S&P 500")
    db.add(idx)
    db.flush()
    db.add(StockIndex(stock_id=out["FERMO"].id, index_id=idx.id))
    db.add(Preferito(stock_id=out["FERMO"].id))
    db.add(Position(stock_id=out["MAIVISTO"].id, entry_price=Decimal("1")))
    db.commit()
    return out


def test_l_elenco_dei_fermi(db: Session, catalogo_db) -> None:
    c = cf.catalogo(db)
    assert [f.ticker for f in c.fermi] == ["MAIVISTO", "FERMO"]   # senza barre per primo
    mai, fermo = c.fermi
    assert (fermo.ultima_barra, fermo.tentativi, fermo.indici, fermo.preferito, fermo.in_posizione) == (
        date(2026, 5, 7), QUARANTINE_STREAK + 5, ["SP500"], True, False)
    assert fermo.ultimo_tentativo == date(2026, 9, 29)
    assert (mai.ultima_barra, mai.in_posizione) == (None, True)


def test_i_dati_mancanti_del_catalogo(db: Session, catalogo_db) -> None:
    c = cf.catalogo(db)
    assert (c.totale, c.senza_settore, c.senza_capitalizzazione) == (4, 2, 2)


def test_la_soglia_e_quella_della_scansione(db: Session, catalogo_db) -> None:
    """Lo stesso predicato che fa saltare il titolo alla scansione (FA-071):
    un tentativo in meno della soglia non e' «fermo»."""
    assert "QUASI" not in {f.ticker for f in cf.catalogo(db).fermi}


# ─── la verifica sulla fonte ─────────────────────────────────────────────


def _yahoo(monkeypatch, *, barre: int, risultati: list[dict], rompi: str | None = None) -> None:
    import yfinance

    class Ticker:
        def __init__(self, t):
            self.t = t

        def history(self, **_):
            if rompi == "storia":
                raise RuntimeError("possibly delisted")
            giorni = pd.date_range("2026-09-01", periods=barre, freq="D")
            return pd.DataFrame({"Close": [1.0] * barre}, index=giorni)

    def cerca(q, **_):
        if rompi == "ricerca":
            raise RuntimeError("429")
        return SimpleNamespace(quotes=risultati)

    monkeypatch.setattr(yfinance, "Ticker", Ticker)
    monkeypatch.setattr(yfinance, "Search", cerca)


def test_la_verifica_riporta_cio_che_yahoo_dice(monkeypatch) -> None:
    _yahoo(monkeypatch, barre=0, risultati=[
        {"symbol": "EA", "exchange": "NMS", "quoteType": "EQUITY", "shortname": "Electronic Arts"},
        {"symbol": "ERT.MU", "exchDisp": "Munich", "quoteType": "EQUITY", "shortname": "ELECTRONIC ARTS"},
    ])
    v = cf.verifica("EA", "Electronic Arts")
    assert (v.barre_recenti, v.ultima_barra_fonte, v.errore) == (0, None, None)
    assert [(c.simbolo, c.borsa) for c in v.candidati] == [("ERT.MU", "Munich")]  # non se stesso


def test_se_la_fonte_ha_di_nuovo_barre_lo_dice(monkeypatch) -> None:
    _yahoo(monkeypatch, barre=5, risultati=[])
    v = cf.verifica("BK", "BNY Mellon")
    assert (v.barre_recenti, v.ultima_barra_fonte) == (5, date(2026, 9, 5))


@pytest.mark.parametrize("rompi", ["storia", "ricerca"])
def test_un_errore_della_fonte_si_dice_e_non_solleva(monkeypatch, rompi) -> None:
    _yahoo(monkeypatch, barre=2, risultati=[{"symbol": "X"}], rompi=rompi)
    v = cf.verifica("BK", "BNY Mellon")
    assert v.errore and v.errore.startswith(rompi)


def test_l_endpoint(db: Session, catalogo_db, monkeypatch) -> None:
    _yahoo(monkeypatch, barre=0, risultati=[{"symbol": "FERMO2", "quoteType": "EQUITY"}])
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        c = TestClient(app)
        assert c.post("/api/catalogo/fermi/NONCE/verifica", json={}).status_code == 404
        r = c.post("/api/catalogo/fermi/FERMO/verifica", json={})
        assert r.status_code == 200
        assert r.json()["candidati"] == [{"simbolo": "FERMO2", "borsa": None, "tipo": "EQUITY", "nome": None}]
    finally:
        app.dependency_overrides.clear()
