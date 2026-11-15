"""Giornate di mercato (FA-152): un giorno con cento segnali nello stesso verso
e' il mercato, non cento notizie. La lista dell'universo lo comprime."""
import json
from datetime import UTC, date, datetime, timedelta

from app.models import Alert, Stock
from app.services import alert_service, rilevanza_service
from app.services import giornate_mercato_service as gm

OGGI = date(2026, 11, 13)          # venerdi'


def _feriali(n, fino=OGGI):
    out, d = [], fino
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


def _base(per_giorno=40):
    giorni = _feriali(70)
    c = {}
    for i, g in enumerate(giorni):
        c[(g, "bull")] = per_giorno + (i % 7)       # 40-46
        c[(g, "bear")] = 30
    return c, giorni[0]


def test_la_soglia_e_sul_verso_non_sul_totale():
    c, inizio = _base()
    c[(OGGI, "bear")] = 90          # ribassisti: giornata di mercato
    c[(OGGI, "bull")] = 46          # rialzisti normali; totale alto ma non conta
    out = gm.giornate(c, dal=OGGI, prima_storia=inizio)
    assert [(g.giorno, g.tono, g.segnali) for g in out] == [(OGGI, "bear", 90)]
    assert out[0].soglia == gm.MINIMO


def test_sotto_soglia_niente_e_il_minimo_protegge_i_giorni_tranquilli():
    c, inizio = _base(per_giorno=5)
    c[(OGGI, "bull")] = 50          # dieci volte il solito, ma sotto il minimo
    assert gm.giornate(c, dal=OGGI, prima_storia=inizio) == []


def test_la_soglia_segue_la_storia():
    c, inizio = _base()
    for g in _feriali(60, fino=OGGI - timedelta(days=1)):
        c[(g, "bull")] = 100        # periodo affollato: 101 non e' anomalo
    c[(OGGI, "bull")] = 101
    out = gm.giornate(c, dal=OGGI, prima_storia=inizio)
    assert out and out[0].soglia == 100   # 101 > 100: appena sopra
    c[(OGGI, "bull")] = 100
    assert gm.giornate(c, dal=OGGI, prima_storia=inizio) == []


def test_senza_storia_sufficiente_non_si_comprime():
    c = {(OGGI, "bull"): 500}
    assert gm.giornate(c, dal=OGGI, prima_storia=OGGI - timedelta(days=10)) == []


def _alert(db, s, tono, quando):
    a = Alert(stock_id=s.id, signal_name="trend_pullback", trigger_price=1.0,
              triggered_at=quando, snapshot=json.dumps({"tone": tono} if tono else {}))
    db.add(a)
    db.flush()
    return a


def test_la_lista_toglie_il_verso_della_giornata_ma_non_i_miei_titoli(db, monkeypatch):
    mio, altro = Stock(ticker="MIO", exchange="X", name="Mio"), Stock(ticker="ALTRO", exchange="X", name="Altro")
    db.add_all([mio, altro])
    db.flush()
    t = datetime(2026, 11, 13, 22, 0, tzinfo=UTC)
    tolto = _alert(db, altro, "bear", t)
    resta_verso = _alert(db, altro, "bull", t)
    resta_mio = _alert(db, mio, "bear", t)
    resta_prezzo = _alert(db, altro, None, t)
    resta_ieri = _alert(db, altro, "bear", t - timedelta(days=1))
    db.commit()
    monkeypatch.setattr(gm, "recenti", lambda d: [gm.Giornata(OGGI, "bear", 90, 60)])
    monkeypatch.setattr(rilevanza_service, "titoli_rilevanti", lambda d: {mio.id: "posizione"})
    monkeypatch.setattr(rilevanza_service, "filtro_rilevanti", lambda col: col.in_([mio.id]))
    ids = {i["id"] for i in alert_service.list_alerts(db, archived=None, comprimi_giornate=True)[0]}
    assert tolto.id not in ids
    assert {resta_verso.id, resta_mio.id, resta_prezzo.id, resta_ieri.id} <= ids
    tutti = {i["id"] for i in alert_service.list_alerts(db, archived=None)[0]}
    assert tolto.id in tutti


def test_recenti_legge_il_database(db):
    s = Stock(ticker="S", exchange="X", name="S")
    db.add(s)
    db.flush()
    for g in _feriali(40, fino=OGGI - timedelta(days=1)):
        _alert(db, s, "bull", datetime.combine(g, datetime.min.time(), UTC) + timedelta(hours=22))
    for _ in range(gm.MINIMO + 1):
        _alert(db, s, "bull", datetime(2026, 11, 13, 22, tzinfo=UTC))
    db.commit()
    gm._cache.clear()
    out = gm.recenti(db, oggi=OGGI)
    assert [(g.giorno, g.tono, g.segnali) for g in out] == [(OGGI, "bull", gm.MINIMO + 1)]


def test_nel_digest_la_giornata_e_una_riga(db, monkeypatch):
    from app.services import notifier_service

    s = Stock(ticker="ZZZ", exchange="X", name="Zeta")
    altro = Stock(ticker="YYY", exchange="X", name="Ypsilon")
    db.add_all([s, altro])
    db.flush()
    t = datetime(2026, 11, 13, 22, 0, tzinfo=UTC)
    giu = _alert(db, s, "bear", t)
    su = _alert(db, altro, "bull", t)
    db.commit()
    monkeypatch.setattr(gm, "recenti", lambda d: [gm.Giornata(OGGI, "bear", 90, 60)])
    monkeypatch.setattr(rilevanza_service, "titoli_rilevanti", lambda d: {})
    testo = notifier_service.build_digest_message(db, [giu, su])
    assert "Giornata di mercato: 1 segnale ribassista" in testo
    assert "ZZZ" not in testo and "YYY" in testo
    # Un guasto delle giornate non toglie il digest.
    monkeypatch.setattr(gm, "recenti", lambda d: 1 / 0)
    assert "ZZZ" in notifier_service.build_digest_message(db, [giu, su])


def test_l_endpoint_elenca_le_giornate_piu_recenti_prima(db, monkeypatch):
    from fastapi.testclient import TestClient

    from app.api.deps import get_current_user, get_db
    from app.main import app
    from app.models import User

    user = User(username="t", password_hash="x")
    db.add(user)
    db.commit()
    monkeypatch.setattr(gm, "recenti", lambda d: [
        gm.Giornata(date(2026, 11, 5), "bear", 104, 74),
        gm.Giornata(date(2026, 11, 13), "bull", 90, 70),
    ])
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        r = TestClient(app).get("/api/alerts/giornate-di-mercato")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    assert [(g["giorno"], g["tono"]) for g in r.json()] == [("2026-11-13", "bull"), ("2026-11-05", "bear")]
