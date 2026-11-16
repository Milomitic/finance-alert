"""Il ricalcolo manuale del punteggio Qualita' usa il metodo della scansione
(2026-11-16): mediane di settore del catalogo, lisciamento una volta al giorno.

Prima il pulsante usava le mediane fisse di ripiego e si lisciava contro il
proprio risultato precedente: ogni clic copriva il 60% della distanza da un
numero che la scansione non avrebbe dato (5 punti di scarto mediano, fino a 11).
"""
import json
from datetime import UTC, datetime, timedelta

import pytest

from app.models import Stock, StockScore
from app.services import stock_fundamentals_service as sfs
from app.services.score_service import bundle_dalla_cache
from app.services.score_service.build import _apply_turnover_control, _ComputedScore


def _cs(stock_id, composite):
    return _ComputedScore(stock_id=stock_id, composite=composite, sub_scores={}, risk_tier="moderate",
                          breakdown={}, computed_at=datetime.now(UTC))


def _salva(db, stock_id, composite, *, quando, prior=None, cold=False):
    turnover = {"cold_start": True} if cold else ({"prior_composite": prior} if prior is not None else {})
    db.merge(StockScore(stock_id=stock_id, composite=composite, risk_tier="moderate", computed_at=quando,
                        breakdown=json.dumps({"_meta_global": {"turnover": turnover}})))
    db.commit()


@pytest.fixture
def titolo(db):
    s = Stock(ticker="SC", exchange="X", name="Sc")
    db.add(s)
    db.commit()
    return s


def test_il_clic_ripetuto_nello_stesso_giorno_da_lo_stesso_numero(db, titolo):
    ieri = datetime.now(UTC) - timedelta(days=1)
    _salva(db, titolo.id, 50.0, quando=ieri)
    valori = []
    for _ in range(5):
        cs = _cs(titolo.id, 70.0)
        _apply_turnover_control(db, cs, ancora_del_giorno=True)
        valori.append(cs.composite)
        _salva(db, titolo.id, cs.composite, quando=datetime.now(UTC),
               prior=cs.breakdown["_meta_global"]["turnover"]["prior_composite"])
    assert valori == [62.0] * 5      # 0,6 x 70 + 0,4 x 50, sempre


def test_senza_ancora_del_giorno_il_clic_deriva_come_prima(db, titolo):
    """Il comportamento della scansione resta quello di sempre."""
    _salva(db, titolo.id, 50.0, quando=datetime.now(UTC), prior=40.0)
    cs = _cs(titolo.id, 70.0)
    _apply_turnover_control(db, cs)
    assert cs.composite == 62.0      # contro la riga salvata, non contro l'ancora


def test_una_riga_di_oggi_nata_a_freddo_non_si_liscia(db, titolo):
    _salva(db, titolo.id, 55.0, quando=datetime.now(UTC), cold=True)
    cs = _cs(titolo.id, 70.0)
    _apply_turnover_control(db, cs, ancora_del_giorno=True)
    assert cs.composite == 70.0 and cs.breakdown["_meta_global"]["turnover"] == {"cold_start": True}


def test_le_mediane_dalla_sola_cache_per_settore(db, monkeypatch):
    righe = [("A1", "Tech", "equity"), ("A2", "Tech", "equity"), ("F1", "Tech", "etf"),
             ("B1", "Banks", "equity"), ("ERR", "Banks", "equity"), ("NOC", "Banks", "equity")]
    for t, settore, tipo in righe:
        db.add(Stock(ticker=t, exchange="X", name=t, sector=settore, instrument_type=tipo))
    db.commit()
    for t in ("A1", "A2", "F1", "B1"):
        monkeypatch.setitem(sfs._CACHE, t, sfs.Fundamentals(ticker=t))
    monkeypatch.setitem(sfs._CACHE, "ERR", sfs.Fundamentals(ticker="ERR", error="404"))
    gruppi = {}

    def finto(by_sector):
        gruppi.update({k: sorted(f.ticker for f in v) for k, v in by_sector.items()})
        return "bundle"
    monkeypatch.setattr("app.services.score_service.sector_stats.sector_stats_service.compute", finto)
    assert bundle_dalla_cache(db) == "bundle"
    assert gruppi == {"Tech": ["A1", "A2"], "Banks": ["B1"]}     # niente ETF, errori o assenti


def test_il_pulsante_usa_le_mediane_e_l_ancora(db, monkeypatch):
    from fastapi.testclient import TestClient

    from app.api.deps import get_current_user, get_db
    from app.main import app
    from app.models import User
    from app.services import score_service

    s = Stock(ticker="BTN", exchange="X", name="Btn", instrument_type="equity")
    u = User(username="b", password_hash="x")
    db.add_all([s, u])
    db.commit()
    visti = {}

    def finto(_db, stock, **kw):
        visti.update(kw)
        return StockScore(stock_id=stock.id, composite=60.0, risk_tier="moderate",
                          computed_at=datetime.now(UTC), breakdown="{}")
    monkeypatch.setattr(score_service, "bundle_dalla_cache", lambda d: "mediane")
    monkeypatch.setattr(score_service, "compute_score", finto)
    monkeypatch.setattr("app.api.scores.stock_fundamentals_service.get_fundamentals", lambda *a, **k: None)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: u
    try:
        r = TestClient(app).post("/api/stocks/BTN/score/recompute", json={})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    assert visti == {"sector_stats": "mediane", "ancora_del_giorno": True}
    assert "_xs" in json.loads(db.get(StockScore, s.id).breakdown)     # la seconda passata e' girata
