"""Le watchlist eToro diventano preferiti (FA-125).

La forma della risposta e' quella letta dal pod il 2026-10-06: 23 watchlist,
«Recently Invested» tagliata a 100 su 111, le altre complete, elementi di tipo
«Instrument» e «User».
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.errors import UpstreamUnavailable
from app.main import app
from app.models import Stock, User
from app.models.etoro import EtoroStrumento
from app.models.preferito import Preferito, PreferitoEscluso
from app.services import etoro_watchlist_service as wl
from app.services import preferiti_service as pref
from tests.test_etoro_portafoglio import FintoEtoro, strumento

ADESSO = datetime(2026, 10, 6, 9, 0, tzinfo=UTC)


@pytest.fixture
def etoro(monkeypatch: pytest.MonkeyPatch) -> FintoEtoro:
    from app.core.config import settings
    from app.services import etoro_client

    monkeypatch.setattr(settings, "etoro_api_key", "a")
    monkeypatch.setattr(settings, "etoro_user_key", "b")
    finto = FintoEtoro()
    monkeypatch.setattr(etoro_client, "get", finto.get)
    return finto


@pytest.fixture
def catalogo(db: Session) -> dict[str, Stock]:
    out = {}
    for t, n in [("AAPL", "Apple Inc."), ("SOXL", "Direxion Daily Semiconductor Bull 3X Shares"),
                 ("MU", "Micron Technology"), ("NVDA", "NVIDIA Corporation"), ("GE", "GE Aerospace")]:
        s = Stock(ticker=t, exchange="NASDAQ", name=n)
        db.add(s)
        out[t] = s
    db.commit()
    return out


def lista(nome: str, ids: list[int], tipo: str = "Static", totale: int | None = None) -> dict:
    return {
        "watchlistId": nome, "name": nome, "watchlistType": tipo,
        "totalItems": len(ids) if totale is None else totale,
        "items": [{"itemId": i, "itemType": "Instrument", "itemRank": k} for k, i in enumerate(ids)],
    }


@pytest.fixture
def watchlist(etoro: FintoEtoro, catalogo) -> FintoEtoro:
    etoro.anagrafica.update({
        1001: strumento(1001, "AAPL", "Apple"),
        3226: strumento(3226, "SOXL", "Direxion Daily Semiconductor Bull 3X ETF", tipo="ETF"),
        1130: strumento(1130, "MU", "Micron Technology, Inc."),
        1137: strumento(1137, "NVDA", "NVIDIA Corporation"),
        1600: strumento(1600, "GE", "General Electric Co"),
        100000: strumento(100000, "BTC", "Bitcoin", tipo="Crypto"),
    })
    etoro.watchlist = {"watchlists": [
        lista("Recently Invested", [1137], tipo="RecentlyInvested", totale=111),
        lista("My Watchlist", [1001, 3226], tipo="Default"),
        lista("Tech", [1130, 1600, 100000]),
        {"watchlistId": "p", "name": "Persone", "watchlistType": "Static", "totalItems": 1,
         "items": [{"itemId": 55, "itemType": "User"}]},
    ]}
    return etoro


def _origini(db: Session) -> dict[str, str]:
    return {
        t: o for t, o in db.execute(
            select(Stock.ticker, Preferito.origine).join(Preferito, Preferito.stock_id == Stock.id)
        ).all()
    }


def test_le_watchlist_diventano_preferiti_tranne_recently_invested(db: Session, watchlist) -> None:
    e = wl.sincronizza_watchlist(db, adesso=ADESSO)
    # NVDA e' solo in «Recently Invested»; GE non si abbina (nome diverso); BTC fuori catalogo.
    assert _origini(db) == {"AAPL": "etoro", "SOXL": "etoro", "MU": "etoro"}
    assert (e.watchlist, e.strumenti, e.abbinati, e.aggiunti, e.completa) == (3, 5, 3, 3, True)
    assert db.get(EtoroStrumento, 1600).in_watchlist is True
    assert db.get(EtoroStrumento, 1600).abbinamento == "da_confermare"


def test_una_stella_manuale_non_si_tocca_mai(db: Session, watchlist, catalogo) -> None:
    pref.aggiungi(db, "NVDA")
    pref.aggiungi(db, "AAPL")  # anche nella watchlist: resta manuale
    wl.sincronizza_watchlist(db, adesso=ADESSO)
    watchlist.watchlist["watchlists"] = [lista("Tech", [1130])]
    wl.sincronizza_watchlist(db, adesso=ADESSO + timedelta(hours=1))
    assert _origini(db) == {"NVDA": "manuale", "AAPL": "manuale", "MU": "etoro"}


def test_un_titolo_tolto_da_eToro_sparisce_dai_preferiti(db: Session, watchlist) -> None:
    wl.sincronizza_watchlist(db, adesso=ADESSO)
    watchlist.watchlist["watchlists"] = [lista("Tech", [1130])]
    e = wl.sincronizza_watchlist(db, adesso=ADESSO + timedelta(hours=1))
    assert e.tolti == 2 and _origini(db) == {"MU": "etoro"}


def test_una_lettura_incompleta_aggiunge_ma_non_toglie(db: Session, watchlist) -> None:
    wl.sincronizza_watchlist(db, adesso=ADESSO)
    watchlist.watchlist["watchlists"] = [lista("Tech", [1130], totale=40)]
    e = wl.sincronizza_watchlist(db, adesso=ADESSO + timedelta(hours=1))
    assert e.completa is False and e.tolti == 0
    assert set(_origini(db)) == {"AAPL", "SOXL", "MU"}


def test_watchlist_vuote_non_cancellano_niente(db: Session, watchlist) -> None:
    wl.sincronizza_watchlist(db, adesso=ADESSO)
    watchlist.watchlist["watchlists"] = []
    e = wl.sincronizza_watchlist(db, adesso=ADESSO + timedelta(hours=1))
    assert e.completa is False and len(_origini(db)) == 3


def test_una_risposta_senza_watchlists_e_un_errore(db: Session, watchlist) -> None:
    watchlist.watchlist = {"status": 200}
    with pytest.raises(UpstreamUnavailable):
        wl.sincronizza_watchlist(db, adesso=ADESSO)


def test_senza_chiavi_non_fa_niente(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "etoro_api_key", "")
    assert wl.sincronizza_watchlist(db).saltata == "non configurato"


def test_una_stella_tolta_a_mano_resta_tolta(db: Session, watchlist) -> None:
    wl.sincronizza_watchlist(db, adesso=ADESSO)
    pref.togli(db, "SOXL")
    wl.sincronizza_watchlist(db, adesso=ADESSO + timedelta(hours=1))
    assert "SOXL" not in _origini(db)
    # Rimessa a mano: torna, manuale, e l'esclusione sparisce.
    pref.aggiungi(db, "SOXL")
    assert _origini(db)["SOXL"] == "manuale"
    assert db.execute(select(PreferitoEscluso)).scalars().all() == []


def test_l_esclusione_decade_quando_il_titolo_esce_dalle_watchlist(db: Session, watchlist, catalogo) -> None:
    wl.sincronizza_watchlist(db, adesso=ADESSO)
    pref.togli(db, "SOXL")
    watchlist.watchlist["watchlists"] = [lista("Tech", [1130])]
    wl.sincronizza_watchlist(db, adesso=ADESSO + timedelta(hours=1))
    assert db.get(PreferitoEscluso, catalogo["SOXL"].id) is None


def test_togliere_una_stella_manuale_non_crea_esclusioni(db: Session, catalogo) -> None:
    pref.aggiungi(db, "AAPL")
    pref.togli(db, "AAPL")
    assert db.execute(select(PreferitoEscluso)).scalars().all() == []


def test_le_stelle_manuali_vengono_prima_nell_elenco(db: Session, watchlist) -> None:
    wl.sincronizza_watchlist(db, adesso=ADESSO)
    pref.aggiungi(db, "NVDA")
    elenco = pref.elenco(db)
    assert elenco[0][0].ticker == "NVDA" and elenco[0][2] == "manuale"


def test_confermare_uno_strumento_della_watchlist_crea_subito_il_preferito(db: Session, watchlist) -> None:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        wl.sincronizza_watchlist(db, adesso=ADESSO)
        client = TestClient(app)
        body = client.get("/api/etoro/portafoglio").json()
        assert [s["simbolo"] for s in body["watchlist_da_confermare"]] == ["GE"]
        assert (body["preferiti_da_etoro"], body["watchlist_fuori_catalogo"]) == (3, 1)
        assert client.put("/api/etoro/strumenti/1600", json={"ticker": "GE"}).status_code == 200
        assert _origini(db)["GE"] == "etoro"
        # Gia' preferito: una seconda conferma non ne crea un altro.
        s = db.get(EtoroStrumento, 1600)
        assert wl.preferito_da_conferma(db, s) is False
        # E il preferito si legge con la sua origine.
        assert {p["ticker"]: p["origine"] for p in client.get("/api/preferiti").json()}["GE"] == "etoro"
    finally:
        app.dependency_overrides.clear()


def test_le_origini_entrano_nella_colonna() -> None:
    assert max(map(len, pref.ORIGINI)) <= Preferito.__table__.c["origine"].type.length
