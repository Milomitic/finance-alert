"""Il pre-market: la scheda della home e l'intestazione della pagina titolo (FA-107).

Sette funzioni del modulo non erano mai state eseguite da un test. Il primo
giro ha trovato un difetto su entrambe le superfici: la lettura prendeva
l'ultima barra di pre-market di QUALUNQUE giorno dei cinque scaricati. Un
titolo che oggi non ha ancora scambiato entrava cosi' nella classifica con la
variazione di una seduta prima, sotto l'etichetta «seduta <oggi>».

Misurato sul pool vero il 2026-09-27, a pre-market di venerdi' concluso:
5 titoli su 136 avevano l'ultima barra di un giorno precedente — IT di lunedi'
21, quattro sedute prima. Nella prima ora di pre-market, quando quasi nessuno
ha ancora scambiato, la quota e' molto piu' alta. Sulla pagina titolo lo
stesso difetto mostrava «PRE» il prezzo di ieri.
"""
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest
from sqlalchemy.orm import Session

from app.models import Stock
from app.models.market_snapshot import MarketSnapshot
from app.services import premarket_service as p

ET = p._ET
VEN = date(2026, 9, 25)
LUN = date(2026, 9, 28)


def _ts(giorno: date, hh: int, mm: int) -> pd.Timestamp:
    return pd.Timestamp(datetime(giorno.year, giorno.month, giorno.day, hh, mm), tz=ET)


def _frame(barre: list[tuple[pd.Timestamp, float, float | None]]) -> pd.DataFrame:
    """Un frame 5m come quello di yfinance: indice con fuso, in UTC."""
    idx = pd.DatetimeIndex([b[0] for b in barre]).tz_convert("UTC")
    return pd.DataFrame(
        {"Close": [b[1] for b in barre], "Volume": [b[2] for b in barre]}, index=idx,
    )


def _seduta(giorno: date, chiusura: float) -> list:
    """Una seduta regolare ridotta a tre barre, l'ultima alle 15:55."""
    return [
        (_ts(giorno, 9, 30), chiusura - 1, 5000),
        (_ts(giorno, 12, 0), chiusura - 0.5, 5000),
        (_ts(giorno, 15, 55), chiusura, 9000),
    ]


def _premarket(giorno: date, prezzi: list[float], vol: float | None = 100) -> list:
    return [(_ts(giorno, 4 + i, 0), px, vol) for i, px in enumerate(prezzi)]


# ── _premarket_from_frame ─────────────────────────────────────────────────


def test_la_lettura_di_base() -> None:
    r = p._premarket_from_frame(_frame(_seduta(VEN, 100.0) + _premarket(LUN, [101.0, 103.0])))
    assert (r.price, r.prev_close, r.volume, r.session) == (103.0, 100.0, 200, LUN)


def test_il_riferimento_e_la_chiusura_regolare_non_il_post_market() -> None:
    """Le barre dopo le 16:00 sono post-market: il denominatore di Yahoo e'
    la chiusura della seduta regolare."""
    barre = _seduta(VEN, 100.0) + [(_ts(VEN, 19, 55), 110.0, 50)] + _premarket(LUN, [102.0])
    r = p._premarket_from_frame(_frame(barre))
    assert r.prev_close == 100.0


def test_il_volume_somma_solo_il_pre_market_della_sessione() -> None:
    """Il pre-market di venerdi' e' nel frame (5 giorni), ma non e' di oggi."""
    barre = _premarket(VEN, [99.0, 99.5], vol=7000) + _seduta(VEN, 100.0) + _premarket(LUN, [101.0], vol=300)
    assert p._premarket_from_frame(_frame(barre)).volume == 300


def test_volume_assente_non_e_zero() -> None:
    barre = _seduta(VEN, 100.0) + _premarket(LUN, [101.0], vol=float("nan"))
    assert p._premarket_from_frame(_frame(barre)).volume is None
    senza = _frame(_seduta(VEN, 100.0) + _premarket(LUN, [101.0])).drop(columns="Volume")
    assert p._premarket_from_frame(senza).volume is None


def test_chiusure_vuote_o_nulle_si_saltano() -> None:
    barre = _seduta(VEN, 100.0) + _premarket(LUN, [101.0, float("nan"), 0.0])
    assert p._premarket_from_frame(_frame(barre)).price == 101.0


def test_la_sessione_e_quella_dell_ultima_barra_di_pre_market() -> None:
    """Il difetto trovato: la lettura NON sa se la barra e' di oggi, e deve
    dirlo — chi la usa decide."""
    vecchia = _seduta(VEN - timedelta(days=1), 98.0) + _premarket(VEN, [99.0]) + _seduta(VEN, 100.0)
    assert p._premarket_from_frame(_frame(vecchia)).session == VEN


@pytest.mark.parametrize(
    "frame",
    [
        None,
        pd.DataFrame(),
        _frame(_seduta(VEN, 100.0)),                         # nessuna barra di pre-market
        _frame(_premarket(LUN, [101.0])),                    # nessuna chiusura prima
        _frame(_seduta(VEN, 100.0) + _premarket(LUN, [1.0])).drop(columns="Close"),
        _frame(_seduta(VEN, 100.0) + _premarket(LUN, [1.0])).tz_localize(None),
    ],
    ids=["none", "vuoto", "senza-pm", "senza-riferimento", "senza-close", "senza-fuso"],
)
def test_nessuna_lettura(frame) -> None:
    assert p._premarket_from_frame(frame) is None


# ── _recompute: la scheda della home ──────────────────────────────────────


@pytest.fixture
def stato(monkeypatch):
    """Lo stato del modulo e' globale: ogni test parte pulito e lo rimette."""
    monkeypatch.setattr(p, "_STATE", {
        "as_of": None, "computed_at": None, "gainers": [], "losers": [],
        "refreshing": False, "progress_done": 0, "progress_total": 0, "last_error": None,
    })
    monkeypatch.setattr(p, "_nasdaq_premarket_volume", lambda t: None)
    return p._STATE


def _pool(monkeypatch, frames: dict[str, pd.DataFrame], tipi: dict[str, str] | None = None):
    def candidati(db):
        p._NAME_BY_TICKER.clear()
        p._TYPE_BY_TICKER.clear()
        for t in frames:
            p._NAME_BY_TICKER[t] = f"{t} Inc."
            p._TYPE_BY_TICKER[t] = (tipi or {}).get(t, "equity")
        return list(frames)

    def scarica(chunk, **_kw):
        if len(chunk) == 1:
            return frames[chunk[0]]
        return pd.concat({t: frames[t] for t in chunk}, axis=1, sort=True)

    monkeypatch.setattr(p, "_candidate_us_tickers", candidati)
    monkeypatch.setattr("yfinance.download", scarica)


def _titolo(chiusura: float, pm: float, giorno: date = LUN) -> pd.DataFrame:
    precedente = giorno - timedelta(days=3 if giorno.weekday() == 0 else 1)
    return _frame(_seduta(precedente, chiusura) + _premarket(giorno, [pm]))


def test_la_classifica(monkeypatch, stato) -> None:
    _pool(monkeypatch, {
        "UP5": _titolo(100.0, 105.0), "UP2": _titolo(50.0, 51.0), "FLAT": _titolo(20.0, 20.0),
        "DN3": _titolo(10.0, 9.7), "LEV": _titolo(10.0, 13.0),
    }, tipi={"LEV": "etf"})
    p._recompute(None)

    assert [r["ticker"] for r in stato["gainers"]] == ["LEV", "UP5", "UP2"]
    assert [r["ticker"] for r in stato["losers"]] == ["DN3"]
    up5 = stato["gainers"][1]
    assert (up5["price"], up5["prev_close"], up5["change_pct"], up5["name"]) == (105.0, 100.0, 5.0, "UP5 Inc.")
    assert stato["gainers"][0]["instrument_type"] == "etf"
    assert (stato["as_of"], stato["refreshing"], stato["last_error"]) == ("2026-09-28", False, None)
    assert stato["progress_done"] == stato["progress_total"]


def test_un_titolo_senza_pre_market_oggi_non_entra(monkeypatch, stato) -> None:
    """Il difetto trovato. STALE ha scambiato in pre-market venerdi' e oggi
    no: la sua variazione di venerdi' finiva fra i rialzi di lunedi'."""
    _pool(monkeypatch, {
        "OGGI": _titolo(100.0, 102.0),
        "STALE": _frame(_seduta(VEN - timedelta(days=1), 50.0) + _premarket(VEN, [60.0]) + _seduta(VEN, 55.0)),
    })
    p._recompute(None)
    assert [r["ticker"] for r in stato["gainers"]] == ["OGGI"]
    assert stato["as_of"] == "2026-09-28"


def test_la_seduta_dichiarata_e_quella_dei_dati(monkeypatch, stato) -> None:
    """Alle 03:55 ET, prima dell'apertura, ogni barra e' della seduta prima:
    la classifica e' quella, e l'etichetta deve dirlo invece di dire oggi."""
    _pool(monkeypatch, {"A": _titolo(100.0, 103.0, VEN), "B": _titolo(10.0, 9.0, VEN)})
    p._recompute(None)
    assert stato["as_of"] == "2026-09-25"
    assert len(stato["gainers"]) == 1 and len(stato["losers"]) == 1


def test_il_volume_di_nasdaq_sostituisce_quello_di_yahoo(monkeypatch, stato) -> None:
    _pool(monkeypatch, {"A": _titolo(100.0, 103.0), "B": _titolo(100.0, 101.0)})
    monkeypatch.setattr(p, "_nasdaq_premarket_volume", lambda t: 777 if t == "A" else None)
    p._recompute(None)
    vol = {r["ticker"]: r["volume"] for r in stato["gainers"]}
    assert vol == {"A": 777, "B": 100}


def test_al_massimo_dieci_per_lato(monkeypatch, stato) -> None:
    _pool(monkeypatch, {f"T{i:02d}": _titolo(100.0, 100.0 + i) for i in range(1, 15)})
    p._recompute(None)
    assert len(stato["gainers"]) == p._TOP_N
    assert stato["gainers"][0]["ticker"] == "T14"


def test_se_ogni_scaricamento_fallisce_la_cache_resta(monkeypatch, stato) -> None:
    _pool(monkeypatch, {"A": _titolo(100.0, 103.0)})
    stato.update({"as_of": "2026-09-25", "gainers": [{"ticker": "OLD"}]})

    def rotto(chunk, **_kw):
        raise RuntimeError("yahoo giu'")

    monkeypatch.setattr("yfinance.download", rotto)
    p._recompute(None)
    assert stato["last_error"] == "all chunk fetches failed"
    assert (stato["as_of"], stato["gainers"], stato["refreshing"]) == ("2026-09-25", [{"ticker": "OLD"}], False)


def test_senza_candidati_lo_dice(monkeypatch, stato) -> None:
    monkeypatch.setattr(p, "_candidate_us_tickers", lambda db: [])
    p._recompute(None)
    assert stato["last_error"] == "no US candidate pool (run a scan first)"
    assert stato["refreshing"] is False


def test_refresh_non_lascia_la_scheda_in_aggiornamento(monkeypatch, stato) -> None:
    def esplode(db):
        stato["refreshing"] = True
        raise RuntimeError("boom")

    monkeypatch.setattr(p, "_recompute", esplode)
    p.refresh(None)
    assert (stato["refreshing"], stato["last_error"]) == (False, "boom")


# ── il pool dei candidati ─────────────────────────────────────────────────


def test_i_candidati_mettono_prima_i_movers_e_solo_gli_usa(db: Session) -> None:
    for t, paese, cap in [("AAPL", "US", 3_000), ("MSFT", "US", 2_900), ("SAP.DE", "DE", 5_000),
                          ("MOVR", "US", 1), ("SPY", "US", None)]:
        db.add(Stock(ticker=t, exchange="X", name=f"{t} nome", country=paese, market_cap=cap,
                     instrument_type="etf" if t == "SPY" else "equity"))
    import json
    db.add(MarketSnapshot(
        id=1, computed_at=datetime.now(UTC), stocks_total=5, stocks_with_data=5,
        payload=json.dumps({"movers": {"top_volume": [{"ticker": "SPY"}], "gainers": [{"ticker": "MOVR"}],
                                       "losers": [{"ticker": "SAP.DE"}]}}),
    ))
    db.commit()

    assert p._candidate_us_tickers(db) == ["SPY", "MOVR", "AAPL", "MSFT"]
    assert p._NAME_BY_TICKER["AAPL"] == "AAPL nome"
    assert p._TYPE_BY_TICKER["SPY"] == "etf"


def test_senza_catalogo_nessun_candidato(db: Session) -> None:
    assert p._candidate_us_tickers(db) == []


# ── premarket_quote: l'intestazione della pagina titolo ───────────────────


@pytest.fixture
def quote(monkeypatch):
    p._SINGLE_CACHE.clear()
    yield
    p._SINGLE_CACHE.clear()


def _a_due_livelli(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """yfinance 1.3 rende (campo, ticker) anche per un titolo solo."""
    out = df.copy()
    out.columns = pd.MultiIndex.from_product([df.columns, [ticker]])
    return out


def test_la_quotazione_della_pagina_titolo(monkeypatch, quote) -> None:
    monkeypatch.setattr("yfinance.download", lambda *a, **k: _a_due_livelli(_titolo(100.0, 104.0), "AAPL"))
    assert p.premarket_quote("AAPL", oggi_et=LUN) == (104.0, 100.0)


def test_la_quotazione_di_un_altro_giorno_non_e_pre_market(monkeypatch, quote) -> None:
    """Il difetto sulla pagina titolo: lunedi' mattina, prima che il titolo
    scambi, l'ultima barra di pre-market e' di venerdi'. Mostrarla come «PRE»
    di oggi e' mostrare un prezzo vecchio di tre giorni come fresco."""
    monkeypatch.setattr("yfinance.download", lambda *a, **k: _a_due_livelli(_titolo(100.0, 104.0, VEN), "AAPL"))
    assert p.premarket_quote("AAPL", oggi_et=LUN) is None


def test_la_quotazione_si_tiene_un_minuto(monkeypatch, quote) -> None:
    chiamate = []

    def scarica(*a, **k):
        chiamate.append(1)
        return _a_due_livelli(_titolo(100.0, 104.0), "AAPL")

    monkeypatch.setattr("yfinance.download", scarica)
    p.premarket_quote("AAPL", oggi_et=LUN)
    p.premarket_quote("AAPL", oggi_et=LUN)
    assert len(chiamate) == 1


def test_un_errore_di_rete_non_e_una_quotazione(monkeypatch, quote) -> None:
    def rotto(*a, **k):
        raise RuntimeError("timeout")

    monkeypatch.setattr("yfinance.download", rotto)
    assert p.premarket_quote("AAPL", oggi_et=LUN) is None


# ── get_state: quando la scheda si vede ───────────────────────────────────


@pytest.mark.parametrize(
    ("aperto", "eta_ore", "dati", "visibile"),
    [
        (False, 1, True, True),
        (True, 1, True, False),      # a mercato aperto il pre-market non esiste
        (False, 19, True, False),    # oltre le 18 ore e' la seduta di ieri
        (False, 1, False, False),    # niente da mostrare
    ],
)
def test_quando_la_scheda_si_vede(monkeypatch, stato, aperto, eta_ore, dati, visibile) -> None:
    monkeypatch.setattr(p, "us_market_open_now", lambda: aperto)
    stato.update({
        "computed_at": (datetime.now(UTC) - timedelta(hours=eta_ore)).isoformat(),
        "gainers": [{"ticker": "A"}] if dati else [],
        "progress_done": 3, "progress_total": 4,
    })
    s = p.get_state()
    assert (s["available"], s["market_open"], s["progress_pct"]) == (visibile, aperto, 75)


@pytest.mark.parametrize(
    ("ora_et", "aperto"),
    [
        (datetime(2026, 9, 28, 9, 29), False),
        (datetime(2026, 9, 28, 9, 30), True),
        (datetime(2026, 9, 28, 15, 59), True),
        (datetime(2026, 9, 28, 16, 0), False),
        (datetime(2026, 9, 26, 12, 0), False),   # sabato
    ],
)
def test_la_seduta_regolare(ora_et, aperto) -> None:
    assert p.us_market_open_now(ora_et.replace(tzinfo=ET)) is aperto


# ── gli endpoint della scheda ─────────────────────────────────────────────


@pytest.fixture
def client(db: Session):
    from fastapi.testclient import TestClient

    from app.api.deps import get_current_user, get_db
    from app.main import app
    from app.models import User

    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_l_endpoint_rende_la_classifica_della_cache(monkeypatch, stato, client) -> None:
    _pool(monkeypatch, {"UP": _titolo(100.0, 103.0), "DN": _titolo(100.0, 98.0)})
    p._recompute(None)
    monkeypatch.setattr(p, "us_market_open_now", lambda: False)

    r = client.get("/api/dashboard/premarket-movers")
    assert r.status_code == 200
    d = r.json()
    assert (d["available"], d["as_of"], d["progress_pct"]) == (True, "2026-09-28", 100)
    assert [g["ticker"] for g in d["gainers"]] == ["UP"]
    assert d["losers"][0] == {
        "ticker": "DN", "name": "DN Inc.", "price": 98.0, "prev_close": 100.0,
        "change_pct": -2.0, "volume": 100, "instrument_type": "equity",
    }


@pytest.mark.parametrize(("in_corso", "chiamate"), [(False, 1), (True, 0)])
def test_il_bottone_non_avvia_un_secondo_aggiornamento(monkeypatch, stato, client, in_corso, chiamate) -> None:
    fatte = []
    monkeypatch.setattr(p, "refresh", lambda db: fatte.append(db))
    stato["refreshing"] = in_corso

    r = client.post("/api/dashboard/premarket-movers/refresh")
    assert (r.status_code, r.json()) == (202, {"accepted": True})
    assert len(fatte) == chiamate
