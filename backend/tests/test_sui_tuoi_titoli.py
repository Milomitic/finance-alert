"""«Sui tuoi titoli» sul cruscotto (FA-149): solo cache, solo i titoli seguiti."""
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from app.models import Stock
from app.services import analyst_actions_feed, rilevanza_service
from app.services import stock_fundamentals_service as sfs
from app.services import stock_news_service as sns
from app.services import sui_tuoi_titoli_service as stt

ADESSO = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)


def _prepara(db, monkeypatch):
    mio = Stock(ticker="MIO", exchange="X", name="Mio Spa")
    altro = Stock(ticker="ALTRO", exchange="X", name="Altro")
    db.add_all([mio, altro])
    db.commit()
    monkeypatch.setattr(rilevanza_service, "titoli_rilevanti", lambda d: {mio.id: "posizione"})
    oggi = ADESSO.date()
    monkeypatch.setattr(sfs, "next_earnings_cached", lambda t: {
        k: v for k, v in {"MIO": (oggi + timedelta(days=3), "21:00"),
                          "ALTRO": (oggi + timedelta(days=1), None)}.items() if k in t})
    azione = lambda tk, d: SimpleNamespace(ticker=tk, date=d.isoformat(), firm="Banca",  # noqa: E731
                                          action="up", from_grade="Hold", to_grade="Buy")
    monkeypatch.setattr(analyst_actions_feed, "recent_actions", lambda **k: [
        azione("MIO", oggi - timedelta(days=2)), azione("ALTRO", oggi),
        azione("MIO", oggi - timedelta(days=40))])
    notizia = lambda t, h: {"title": t, "link": "u", "publisher": "P",  # noqa: E731
                            "published_at": (ADESSO - timedelta(hours=h)).isoformat(),
                            "sentiment": "neutral"}
    monkeypatch.setitem(sns._CACHE, "MIO", (ADESSO, [notizia(f"n{i}", i) for i in range(5)]
                                            + [notizia("vecchia", 24 * 5)]))
    monkeypatch.setitem(sns._CACHE, "ALTRO", (ADESSO, [notizia("altro", 1)]))
    return mio


def test_solo_i_miei_titoli_e_solo_le_finestre_giuste(db, monkeypatch):
    _prepara(db, monkeypatch)
    out = stt.riepilogo(db, adesso=ADESSO)
    assert out["titoli"] == 1
    assert [(t["ticker"], t["giorni"], t["ora_utc"]) for t in out["trimestrali"]] == [("MIO", 3, "21:00")]
    assert [a["data"] for a in out["analisti"]] == [(ADESSO.date() - timedelta(days=2)).isoformat()]
    # Due notizie al massimo per titolo, le piu' recenti; niente oltre tre giorni.
    assert [n["titolo"] for n in out["notizie"]] == ["n0", "n1"]


def test_senza_titoli_seguiti_lo_dice(db, monkeypatch):
    monkeypatch.setattr(rilevanza_service, "titoli_rilevanti", lambda d: {})
    assert stt.riepilogo(db, adesso=ADESSO) == {"titoli": 0, "trimestrali": [], "analisti": [], "notizie": []}


def test_una_data_illeggibile_non_rompe_la_scheda():
    assert stt._istante("ieri") is None and stt._istante(None) is None
    assert stt._istante("2026-11-16T08:00:00Z").tzinfo is not None
    assert stt._istante("2026-11-16T08:00:00").tzinfo is not None


def test_l_endpoint(db, monkeypatch):
    from fastapi.testclient import TestClient

    from app.api.deps import get_current_user, get_db
    from app.main import app
    from app.models import User

    _prepara(db, monkeypatch)
    monkeypatch.setattr(stt, "datetime", SimpleNamespace(now=lambda tz: ADESSO,
                                                         fromisoformat=datetime.fromisoformat))
    user = User(username="t", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        r = TestClient(app).get("/api/dashboard/sui-tuoi-titoli")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    assert r.json()["titoli"] == 1 and r.json()["trimestrali"][0]["ticker"] == "MIO"
    assert date.fromisoformat(r.json()["trimestrali"][0]["data"])
