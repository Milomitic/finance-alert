"""L'andamento di un settore (2026-10-11): indice a pesi uguali, rendimenti,
ampiezza, e il blocco che la pagina di dettaglio ne riceve."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Alert, OhlcvDaily, Stock, StockScore, TechnicalScore, User
from app.services import sector_performance_service as sp

OGGI = date(2026, 9, 15)
NOW = datetime(2026, 9, 15, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _cache_vuota():
    sp._CACHE.clear()
    yield
    sp._CACHE.clear()


def _feriali(fine: date, n: int) -> list[date]:
    out, g = [], fine
    while len(out) < n:
        if g.weekday() < 5:
            out.append(g)
        g -= timedelta(days=1)
    return out[::-1]


def _stock(db: Session, ticker: str, *, sector: str = "Energy", tipo: str = "equity") -> Stock:
    s = Stock(ticker=ticker, exchange="NYSE", name=f"{ticker} Corp", sector=sector, industry="Oil",
              country="US", market_cap=1e10, instrument_type=tipo)
    db.add(s)
    db.flush()
    return s


def _barre(db: Session, s: Stock, giorni: list[date], prezzi: list[float]) -> None:
    for g, p in zip(giorni, prezzi, strict=True):
        db.add(OhlcvDaily(stock_id=s.id, date=g, open=p, high=p, low=p, close=p, volume=1000))


def _crescita(p0: float, passo: float, n: int) -> list[float]:
    return [p0 * (1 + passo) ** i for i in range(n)]


# ── l'indice ──────────────────────────────────────────────────────────────


def test_indice_a_pesi_uguali_e_base_100(db: Session) -> None:
    giorni = _feriali(OGGI, 4)
    a, b, c = (_stock(db, t) for t in ("AAA", "BBB", "CCC"))
    # Rendimenti giornalieri +10%, 0%, −4%: la media e' +2% al giorno.
    _barre(db, a, giorni, _crescita(100, 0.10, 4))
    _barre(db, b, giorni, [50, 50, 50, 50])
    _barre(db, c, giorni, _crescita(10, -0.04, 4))
    db.commit()
    r = sp.calcola(db, {a.id: "AAA", b.id: "BBB", c.id: "CCC"}, oggi=OGGI)
    valori = [v for _, v in r.indice]
    assert valori[0] == 100.0
    assert valori[-1] == pytest.approx(100 * 1.02 ** 3, abs=1e-3)
    assert [d for d, _ in r.indice] == giorni


def test_un_giorno_a_meta_non_conta_e_il_movimento_non_si_perde(db: Session) -> None:
    giorni = _feriali(OGGI, 6)
    ids = {}
    for i in range(8):
        s = _stock(db, f"T{i}")
        ids[s.id] = s.ticker
        if i < 3:
            # Tre su otto scambiano anche il giorno festivo per gli altri (il
            # quarto): abbastanza per la soglia minima, non per meta' settore.
            # T0 fa +10% proprio quel giorno, poi resta fermo.
            _barre(db, s, giorni, [100, 100, 100, 110 if i == 0 else 100, 110 if i == 0 else 100,
                                   110 if i == 0 else 100])
        else:
            _barre(db, s, giorni[:3] + giorni[4:], [100, 100, 100, 100, 100])
    db.commit()
    r = sp.calcola(db, ids, oggi=OGGI)
    date_indice = [d for d, _ in r.indice]
    assert giorni[3] not in date_indice  # una mezza giornata non e' un giorno del settore
    # Il +10% di T0 e' entrato il giorno dopo, come un ottavo del settore: +1,25%.
    # Contato quel giorno con i soli tre titoli aperti, sarebbe stato +3,3%.
    assert r.indice[-1][1] == pytest.approx(101.25, abs=1e-3)


def test_un_artefatto_oltre_il_45_per_cento_si_scarta(db: Session) -> None:
    giorni = _feriali(OGGI, 3)
    ids = {}
    for i, prezzi in enumerate([[100, 50, 50], [100, 100, 100], [100, 100, 100]]):
        s = _stock(db, f"S{i}")
        ids[s.id] = s.ticker
        _barre(db, s, giorni, prezzi)
    db.commit()
    r = sp.calcola(db, ids, oggi=OGGI)
    # Il −50% di uno split 2:1 non assorbito non trascina il settore del −16,7%.
    assert r.indice[-1][1] == pytest.approx(100.0)
    s0 = next(t for t in r.titoli if t.ticker == "S0")
    assert s0.r_1g == pytest.approx(0.0)


def test_senza_barre_l_andamento_e_vuoto(db: Session) -> None:
    s = _stock(db, "NIL")
    db.commit()
    assert sp.calcola(db, {s.id: "NIL"}, oggi=OGGI).indice == []
    assert sp.calcola(db, {}, oggi=OGGI).indice == []


# ── rendimenti, confronti, ampiezza ───────────────────────────────────────


def _settore_lungo(db: Session) -> tuple[dict[int, str], list[date]]:
    giorni = _feriali(OGGI, 300)
    ids = {}
    for i, passo in enumerate([0.002, 0.001, -0.001]):
        s = _stock(db, f"L{i}")
        ids[s.id] = s.ticker
        _barre(db, s, giorni, _crescita(100, passo, 300))
    spy = _stock(db, "SPY", sector="Financials", tipo="etf")
    _barre(db, spy, giorni, _crescita(400, 0.0005, 300))
    xle = _stock(db, "XLE", tipo="etf")
    _barre(db, xle, giorni, _crescita(80, 0.0015, 300))
    db.commit()
    return ids, giorni


def test_rendimenti_su_finestre_di_calendario_e_confronti(db: Session) -> None:
    ids, giorni = _settore_lungo(db)
    r = sp.calcola(db, ids, etf_ticker="XLE", oggi=OGGI)
    assert set(r.rendimenti) == {"1s", "1m", "3m", "6m", "ytd", "1a"}
    # Un mese di calendario: l'ultima chiusura a 30 giorni fa o prima.
    base = max(g for g in giorni if g <= OGGI - timedelta(days=30))
    sedute = len([g for g in giorni if g > base])
    atteso = ((1.002 ** sedute + 1.001 ** sedute + 0.999 ** sedute) / 3)
    # La media dei rendimenti giornalieri, concatenata, non e' la media dei
    # rendimenti del mese: vicino, non uguale.
    assert r.rendimenti["1m"] == pytest.approx((atteso - 1) * 100, abs=0.05)
    assert r.rendimenti_spy["1m"] == pytest.approx((1.0005 ** sedute - 1) * 100, abs=1e-6)
    assert r.etf_ticker == "XLE"
    assert r.rendimenti_etf["1a"] > r.rendimenti_spy["1a"]
    # Le tre serie hanno base 100 sullo stesso giorno.
    assert r.indice[0][0] == r.spy[0][0] == r.etf[0][0]
    assert r.spy[0][1] == r.etf[0][1] == 100.0


def test_una_finestra_piu_lunga_della_storia_non_ha_rendimento(db: Session) -> None:
    giorni = _feriali(OGGI, 10)
    ids = {}
    for i in range(3):
        s = _stock(db, f"C{i}")
        ids[s.id] = s.ticker
        _barre(db, s, giorni, _crescita(100, 0.01, 10))
    db.commit()
    r = sp.calcola(db, ids, oggi=OGGI)
    assert r.rendimenti["1s"] is not None
    assert r.rendimenti["1a"] is None
    # Senza SPY nel catalogo il confronto resta vuoto invece di inventarlo.
    assert r.spy == [] and r.rendimenti_spy == {}


def test_ampiezza_con_il_suo_denominatore(db: Session) -> None:
    ids, _ = _settore_lungo(db)
    corto = _stock(db, "NEW")
    _barre(db, corto, _feriali(OGGI, 60), _crescita(10, 0.003, 60))
    ids[corto.id] = "NEW"
    db.commit()
    r = sp.calcola(db, ids, oggi=OGGI)
    # La EMA200 si conta solo con 200 barre: il titolo nuovo resta fuori dal
    # denominatore invece di contare come «sotto».
    assert r.sopra_ema200 == (2, 3)
    assert r.sopra_ema50 == (3, 4)
    assert r.vicino_massimi == (3, 4)  # tre in salita sul massimo, piu' il nuovo
    assert r.vicino_minimi == (1, 4)  # quello che scende sta sul minimo
    assert r.in_rialzo == (3, 4)
    l2 = next(t for t in r.titoli if t.ticker == "L2")
    assert l2.r_1a is not None and l2.r_1a < 0
    assert l2.dal_massimo < 0 and l2.dal_minimo == pytest.approx(0.0)


def test_la_cache_risponde_senza_ricalcolare(db: Session, monkeypatch) -> None:
    chiamate: list = []

    def finto(db, titoli, *, etf_ticker=None, oggi=None):
        chiamate.append(titoli)
        return sp.Andamento(indice=[])

    monkeypatch.setattr(sp, "calcola", finto)
    sp.calcola_in_cache(db, "Energy", {1: "A"}, etf_ticker="XLE")
    sp.calcola_in_cache(db, "Energy", {1: "A"}, etf_ticker="XLE")
    sp.calcola_in_cache(db, "Energy", {1: "A", 2: "B"}, etf_ticker="XLE")
    assert len(chiamate) == 2


# ── la pagina di dettaglio ────────────────────────────────────────────────


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_il_dettaglio_porta_andamento_segnali_e_rendimenti_per_titolo(client: TestClient, db: Session) -> None:
    ids, _ = _settore_lungo(db)
    for sid in ids:
        db.add(StockScore(stock_id=sid, composite=60.0, risk_tier="moderate", breakdown="{}", computed_at=NOW))
    primo = next(iter(ids))
    db.add(TechnicalScore(stock_id=primo, composite=71.5, posture="Forte", breakdown="{}", computed_at=NOW))
    for giorni_fa, tono in [(2, "bull"), (5, "bear"), (40, "bull")]:
        db.add(Alert(stock_id=primo, signal_name="trend_pullback", signal_date=date.today() - timedelta(days=giorni_fa),
                     trigger_price=100.0, snapshot=json.dumps({"tone": tono})))
    db.commit()

    body = client.get("/api/sectors/Energy/detail").json()
    a = body["andamento"]
    assert a["etf_ticker"] == "XLE"
    assert a["serie"][0]["settore"] == a["serie"][0]["spy"] == a["serie"][0]["etf"] == 100.0
    assert [x["finestra"] for x in a["rendimenti"]] == ["1s", "1m", "3m", "6m", "ytd", "1a"]
    assert a["sopra_ema200"] == {"n": 2, "su": 3}
    assert a["aggiornato_al"] == OGGI.isoformat()
    righe = {r["ticker"]: r for r in body["stocks"]}
    assert righe["L0"]["technical"] == 71.5 and righe["L1"]["technical"] is None
    assert righe["L0"]["r_1m"] > 0 and righe["L2"]["r_1a"] < 0
    assert righe["L2"]["sopra_ema200"] is False
    seg = body["segnali"]
    # Trenta giorni: quello di 40 giorni fa resta fuori.
    assert (seg["totale"], seg["rialzisti"], seg["ribassisti"]) == (2, 1, 1)
    assert seg["recenti"][0]["tone"] == "bull" and seg["recenti"][0]["ticker"] == "L0"


def test_se_l_andamento_fallisce_la_pagina_resta_in_piedi(client: TestClient, db: Session, monkeypatch) -> None:
    _stock(db, "ONE")
    db.commit()

    def rotto(*a, **k):
        raise RuntimeError("barre illeggibili")

    monkeypatch.setattr(sp, "calcola_in_cache", rotto)
    r = client.get("/api/sectors/Energy/detail")
    assert r.status_code == 200
    assert r.json()["andamento"] is None
    assert r.json()["stocks"][0]["r_1m"] is None


def test_i_rendimenti_di_tutti_i_settori_con_lo_spy(client: TestClient, db: Session) -> None:
    ids, _ = _settore_lungo(db)
    altro = _stock(db, "UTL", sector="Utilities")
    _barre(db, altro, _feriali(OGGI, 2), [10, 11])  # due sole barre: nessuna media
    db.commit()
    body = client.get("/api/sectors/performance").json()
    nomi = [s["name"] for s in body["settori"]]
    assert "Energy" in nomi
    energy = next(s for s in body["settori"] if s["name"] == "Energy")
    assert energy["stock_count"] == 3 and energy["etf_ticker"] == "XLE"
    assert energy["sopra_ema200"] == {"n": 2, "su": 3}
    assert [r["finestra"] for r in energy["rendimenti"]] == ["1s", "1m", "3m", "6m", "ytd", "1a"]
    assert energy["ultimo_giorno"] is not None
    # Lo SPY e' la riga di riferimento, e non compare fra i settori.
    assert body["spy"][1]["finestra"] == "1m" and body["spy"][1]["settore"] is not None
    assert "Financials" not in nomi
    assert body["aggiornato_al"] == OGGI.isoformat()


def test_un_settore_che_fallisce_non_abbatte_gli_altri(client: TestClient, db: Session, monkeypatch) -> None:
    _settore_lungo(db)
    altro = _stock(db, "UTL", sector="Utilities")
    _barre(db, altro, _feriali(OGGI, 3), [10, 11, 12])
    db.commit()
    vero = sp.calcola_in_cache

    def a_volte(db, settore, titoli, *, etf_ticker):
        if settore == "Utilities":
            raise RuntimeError("rotto")
        return vero(db, settore, titoli, etf_ticker=etf_ticker)

    monkeypatch.setattr(sp, "calcola_in_cache", a_volte)
    body = client.get("/api/sectors/performance").json()
    assert [s["name"] for s in body["settori"]] == ["Energy"]


# ── la cache non fa aspettare ─────────────────────────────────────────────


class _Ctx:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, *a):
        return False


class _ThreadSubito:
    """Un thread che gira subito, nel test, al posto di uno vero."""
    avviati: list = []

    def __init__(self, target, args=(), **kw):
        self.target, self.args = target, args

    def start(self):
        _ThreadSubito.avviati.append(self.args[0])
        self.target(*self.args)


def test_a_cache_scaduta_risponde_subito_e_ricalcola_dietro(db: Session, monkeypatch) -> None:
    import app.core.db as core_db

    versioni = iter([sp.Andamento(indice=[(OGGI, 100.0)]), sp.Andamento(indice=[(OGGI, 120.0)])])
    monkeypatch.setattr(sp, "calcola", lambda db, titoli, *, etf_ticker=None, oggi=None: next(versioni))
    monkeypatch.setattr(core_db, "SessionLocal", lambda: _Ctx(db))
    monkeypatch.setattr(sp.threading, "Thread", _ThreadSubito)
    _ThreadSubito.avviati = []

    assert sp.calcola_in_cache(db, "Energy", {1: "A"}, etf_ticker=None).indice[0][1] == 100.0
    chiave = next(iter(sp._CACHE))
    sp._CACHE[chiave] = (sp._CACHE[chiave][0] - sp._TTL - 1, sp._CACHE[chiave][1])
    # Scaduta: risponde col valore di prima, e il ricalcolo parte dietro.
    assert sp.calcola_in_cache(db, "Energy", {1: "A"}, etf_ticker=None).indice[0][1] == 100.0
    assert _ThreadSubito.avviati == [chiave]
    assert sp.calcola_in_cache(db, "Energy", {1: "A"}, etf_ticker=None).indice[0][1] == 120.0
    assert chiave not in sp._IN_CORSO


def test_un_ricalcolo_fallito_lascia_il_valore_vecchio(db: Session, monkeypatch) -> None:
    import app.core.db as core_db

    def rotto(*a, **k):
        raise RuntimeError("barre illeggibili")

    monkeypatch.setattr(core_db, "SessionLocal", lambda: _Ctx(db))
    monkeypatch.setattr(sp, "calcola", rotto)
    chiave = ("Energy", None, (1,))
    vecchio = sp.Andamento(indice=[(OGGI, 100.0)])
    sp._CACHE[chiave] = (0.0, vecchio)
    sp._IN_CORSO.add(chiave)
    sp._ricalcola(chiave, {1: "A"}, None)
    assert sp._CACHE[chiave][1] is vecchio
    assert chiave not in sp._IN_CORSO


def test_il_precalcolo_riempie_le_stesse_chiavi_della_pagina(db: Session, monkeypatch) -> None:
    import app.core.db as core_db

    ids, _ = _settore_lungo(db)
    doppio = Stock(ticker="L0", exchange="LSE", name="L0 bis", sector="Energy", instrument_type="equity",
                   country="US")
    db.add(doppio)
    db.commit()
    monkeypatch.setattr(core_db, "SessionLocal", lambda: _Ctx(db))
    per = sp.titoli_per_settore(db)
    # Un ticker, un id: il doppione quotato altrove non entra due volte.
    assert sorted(per["Energy"].values()) == ["L0", "L1", "L2"]
    assert "Financials" not in per  # lo SPY e' un ETF
    assert sp.precalcola({"Energy": "XLE"}) == 1
    a = sp.calcola_in_cache(db, "Energy", per["Energy"], etf_ticker="XLE")
    assert a.etf_ticker == "XLE" and a.indice
