"""«Dall'ultima visita» sul cruscotto: il riferimento e il riepilogo."""
import json
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Alert, Position, PriceAlert, Stock, User
from app.services import stock_fundamentals_service
from app.services import ultima_visita_service as uv
from app.services.stock_fundamentals_service import AnalystAction, Fundamentals

T0 = datetime(2026, 9, 29, 8, 0, tzinfo=UTC)


def _min(n: int) -> datetime:
    return T0 + timedelta(minutes=n)


# ─── il riferimento ──────────────────────────────────────────────────────


def test_la_prima_visita_non_ha_riferimento(db: Session) -> None:
    assert uv.registra_apertura(db, T0) is None


def test_una_ricarica_non_sposta_il_riferimento(db: Session) -> None:
    uv.registra_apertura(db, T0)
    assert uv.registra_apertura(db, _min(5)) is None       # stessa sessione
    assert uv.registra_apertura(db, _min(50)) == _min(5)   # pausa di 45': nuova
    assert uv.registra_apertura(db, _min(52)) == _min(5)   # ricarica: resta
    assert uv.registra_apertura(db, _min(70)) == _min(5)   # andirivieni: resta


def test_la_pausa_e_misurata_dall_ultima_apertura(db: Session) -> None:
    """Una sessione lunga di aperture ravvicinate non diventa «una pausa»."""
    uv.registra_apertura(db, T0)
    for m in range(10, 200, 10):
        assert uv.registra_apertura(db, _min(m)) is None
    assert uv.registra_apertura(db, _min(190 + 31)) == _min(190)


def test_il_bordo_della_pausa(db: Session) -> None:
    uv.registra_apertura(db, T0)
    assert uv.registra_apertura(db, T0 + uv.PAUSA - timedelta(seconds=1)) is None
    uv.registra_apertura(db, T0 + 10 * uv.PAUSA)
    assert uv.registra_apertura(db, T0 + 11 * uv.PAUSA) == T0 + 10 * uv.PAUSA


# ─── il riepilogo ────────────────────────────────────────────────────────


@pytest.fixture
def mondo(db: Session) -> dict[str, Stock]:
    stock_fundamentals_service._CACHE.clear()
    out = {}
    for t in ["POS", "ALTRO"]:
        out[t] = Stock(ticker=t, exchange="X", name=t)
        db.add(out[t])
    db.flush()
    prima, dopo = _min(-60), _min(60)
    db.add(Position(stock_id=out["POS"].id, entry_price=Decimal("10")))
    db.add(Position(stock_id=out["ALTRO"].id, entry_price=Decimal("10"),
                    closed_at=dopo, exit_price=Decimal("9"), exit_reason="stop"))
    for stock, quando in [(out["POS"], dopo), (out["ALTRO"], dopo), (out["ALTRO"], prima)]:
        db.add(Alert(stock_id=stock.id, signal_name="volume_breakout", trigger_price=10,
                     snapshot=json.dumps({"tone": "bull"}), emitted_at=quando))
    # Un target di prezzo scattato: non e' un «segnale».
    db.add(Alert(stock_id=out["POS"].id, signal_name=None, trigger_price=11,
                 snapshot="{}", emitted_at=dopo))
    db.add(PriceAlert(stock_id=out["POS"].id, target_price=Decimal("11"), direction="above",
                      triggered_at=dopo))
    db.add(PriceAlert(stock_id=out["POS"].id, target_price=Decimal("20"), direction="above"))
    db.commit()
    stock_fundamentals_service._CACHE["POS"] = Fundamentals(
        ticker="POS", fetched_at=time.time(), analyst_actions=[
            AnalystAction(date="2026-09-29", firm="UBS", to_grade="Buy", from_grade="Hold", action="up"),
            AnalystAction(date="2026-09-20", firm="Citi", to_grade="Buy", from_grade="Hold", action="up"),
        ])
    yield out
    stock_fundamentals_service._CACHE.clear()


def test_il_riepilogo_dal_riferimento(db: Session, mondo, monkeypatch) -> None:
    monkeypatch.setattr(stock_fundamentals_service, "get_fundamentals",
                        lambda *a, **k: pytest.fail("il cruscotto non deve andare in rete"))
    r = uv.riepilogo(db, T0)
    assert (r.segnali, r.segnali_miei, r.target_raggiunti, r.posizioni_chiuse) == (2, 1, 1, 1)
    assert [(n.ticker, n.data) for n in r.novita] == [("POS", date(2026, 9, 29))]


def test_alla_prima_visita_nessun_conteggio(db: Session, mondo) -> None:
    r = uv.riepilogo(db, None)
    assert (r.dal, r.segnali, r.novita) == (None, 0, [])


# ─── l'endpoint ──────────────────────────────────────────────────────────


def test_l_endpoint_registra_e_risponde(db: Session, mondo) -> None:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        c = TestClient(app)
        primo = c.post("/api/cruscotto/visita", json={})
        assert primo.status_code == 200
        assert primo.json()["dal"] is None
        secondo = c.post("/api/cruscotto/visita", json={}).json()
        assert secondo["dal"] is None       # stessa sessione
        assert set(secondo) == {"dal", "segnali", "segnali_miei", "target_raggiunti",
                                "posizioni_chiuse", "novita"}
    finally:
        app.dependency_overrides.clear()
