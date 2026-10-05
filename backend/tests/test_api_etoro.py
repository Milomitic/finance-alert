"""API, job e notifica del portafoglio eToro (FA-124)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.core.errors import UpstreamUnavailable
from app.main import app
from app.models import Position, User
from app.models.etoro import EtoroPosizione
from app.scheduler.jobs import sincronizza_etoro as job
from app.services import etoro_client, notifier_service
from app.services import etoro_portafoglio_service as svc
from tests.test_etoro_portafoglio import FintoEtoro, posizione, strumento


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def etoro(monkeypatch: pytest.MonkeyPatch) -> FintoEtoro:
    monkeypatch.setattr(settings, "etoro_api_key", "a")
    monkeypatch.setattr(settings, "etoro_user_key", "b")
    finto = FintoEtoro()
    monkeypatch.setattr(etoro_client, "get", finto.get)
    return finto


@pytest.fixture
def portafoglio(db: Session, etoro: FintoEtoro):
    from app.models import Stock

    aapl = Stock(ticker="AAPL", exchange="NASDAQ", name="Apple Inc.", currency="USD")
    db.add_all([aapl, Stock(ticker="RR", exchange="NASDAQ", name="Richtech Robotics Inc.")])
    db.commit()
    etoro.anagrafica[1001] = strumento(1001, "AAPL", "Apple")
    etoro.anagrafica[2002] = strumento(2002, "RR", "Rolls-Royce Holdings")
    etoro.posizioni = [
        posizione(1, 1001, apertura=100.0, stop=90.0, pnl=50.0, margine=200.0),
        posizione(2, 2002),
    ]
    svc.sincronizza(db)
    return aapl


def test_senza_chiavi_il_portafoglio_dice_non_configurato(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "etoro_api_key", "")
    body = client.get("/api/etoro/portafoglio").json()
    assert body == {
        "configurato": False, "conto": None, "aperte": [], "chiuse": [], "da_decidere": [],
        "preferiti_da_etoro": 0, "watchlist_fuori_catalogo": 0, "watchlist_da_confermare": [],
    }


def test_il_portafoglio_porta_i_numeri_a_leva(client: TestClient, portafoglio) -> None:
    body = client.get("/api/etoro/portafoglio").json()
    assert body["configurato"] is True
    # L'abbinamento incerto viaggia nella stessa risposta, col suo candidato.
    assert [(s["simbolo"], s["candidato_ticker"]) for s in body["da_decidere"]] == [("RR", "RR")]
    p = {r["position_id"]: r for r in body["aperte"]}[1]
    assert (p["ticker"], p["valuta"], p["leva"], p["regolamento"]) == ("AAPL", "USD", 5, "cfd")
    assert p["pnl_pct_margine"] == pytest.approx(25.0)
    # Stop a -10% del prezzo con leva 5: -50% del margine.
    assert p["stop_pct_margine"] == pytest.approx(-50.0)
    # Lo strumento da confermare compare, ma senza ticker.
    assert {r["position_id"]: r for r in body["aperte"]}[2]["ticker"] is None
    assert body["conto"]["valuta"] == "USD"


def test_un_doppione_con_una_posizione_manuale_si_segnala(client: TestClient, db: Session, portafoglio) -> None:
    db.add(Position(stock_id=portafoglio.id, side="long", entry_price=100.0))
    db.commit()
    p = {r["position_id"]: r for r in client.get("/api/etoro/portafoglio").json()["aperte"]}[1]
    assert p["anche_manuale"] is True


def test_le_chiuse_recenti_e_non_le_vecchie(client: TestClient, db: Session, portafoglio) -> None:
    db.get(EtoroPosizione, 2).chiusa_il = datetime.now(UTC) - timedelta(days=60)
    db.get(EtoroPosizione, 1).chiusa_il = datetime.now(UTC) - timedelta(days=1)
    db.commit()
    body = client.get("/api/etoro/portafoglio").json()
    assert [r["position_id"] for r in body["chiuse"]] == [1]
    assert body["aperte"] == []


def test_gli_strumenti_da_confermare_vengono_prima(client: TestClient, portafoglio) -> None:
    righe = client.get("/api/etoro/strumenti").json()
    assert righe[0]["abbinamento"] == "da_confermare"
    assert (righe[0]["simbolo"], righe[0]["candidato_ticker"]) == ("RR", "RR")
    assert righe[-1]["ticker"] == "AAPL"


def test_confermare_un_abbinamento(client: TestClient, portafoglio) -> None:
    r = client.put("/api/etoro/strumenti/2002", json={"ticker": None})
    assert r.status_code == 200 and r.json()["abbinamento"] == "manuale"
    assert client.put("/api/etoro/strumenti/2002", json={"ticker": "NONESISTE"}).status_code == 422
    assert client.put("/api/etoro/strumenti/9999", json={"ticker": "AAPL"}).status_code == 404


def test_sincronizzare_a_richiesta(client: TestClient, portafoglio, etoro: FintoEtoro) -> None:
    body = client.post("/api/etoro/sincronizza", json={}).json()
    assert (body["aperte"], body["nuove"], body["saltata"]) == (2, 0, None)
    etoro.pnl_rotto = True
    r = client.post("/api/etoro/sincronizza", json={})
    assert r.status_code == 502 and "clientPortfolio" in r.json()["detail"]


# ─── Job e notifica ─────────────────────────────────────────────────────────


def test_il_job_senza_chiavi_non_chiama_niente(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "etoro_api_key", "")
    monkeypatch.setattr(etoro_client, "get", lambda *a, **k: pytest.fail("chiamata"))
    job.run_sincronizza_etoro()


def test_il_job_sopravvive_a_un_errore_di_etoro(db: Session, etoro: FintoEtoro, monkeypatch) -> None:
    def rotto(*a, **k):
        raise UpstreamUnavailable("giu'", source="etoro", op="portafoglio")

    monkeypatch.setattr(etoro_client, "get", rotto)
    job.run_sincronizza_etoro()


def _chiudi_aapl(etoro: FintoEtoro) -> None:
    etoro.posizioni = [p for p in etoro.posizioni if p["positionID"] != 1]
    etoro.storico = [{"positionId": 1, "closeRate": 130.0, "closeTimestamp": datetime.now(UTC).isoformat(),
                      "netProfit": 145.0, "takeProfitRate": 130.0, "stopLossRate": 90.0}]


def test_il_job_manda_la_chiusura_e_la_segna(db: Session, etoro: FintoEtoro, portafoglio, monkeypatch) -> None:
    _chiudi_aapl(etoro)
    mandati: list[str] = []
    monkeypatch.setattr(notifier_service, "_telegram_enabled", lambda: True)
    monkeypatch.setattr(notifier_service, "_send_telegram", lambda text, what: mandati.append(text) or True)
    job.run_sincronizza_etoro()
    assert len(mandati) == 1
    testo = mandati[0]
    assert "AAPL" in testo and "×5" in testo and "a target" in testo and "+145.00 USD" in testo
    assert "+72.5% sul margine" in testo
    db.expire_all()
    assert db.get(EtoroPosizione, 1).notificata is True
    # Il giro dopo non la rimanda.
    job.run_sincronizza_etoro()
    assert len(mandati) == 1


def test_un_invio_fallito_si_riprova(db: Session, etoro: FintoEtoro, portafoglio, monkeypatch) -> None:
    _chiudi_aapl(etoro)
    monkeypatch.setattr(notifier_service, "_telegram_enabled", lambda: True)
    monkeypatch.setattr(notifier_service, "_send_telegram", lambda text, what: False)
    job.run_sincronizza_etoro()
    db.expire_all()
    assert db.get(EtoroPosizione, 1).notificata is False


def test_senza_telegram_le_chiusure_si_segnano_lo_stesso(db: Session, etoro: FintoEtoro, portafoglio, monkeypatch) -> None:
    """Accendere Telegram dopo non deve rovesciare in chat le chiusure vecchie."""
    _chiudi_aapl(etoro)
    monkeypatch.setattr(notifier_service, "_telegram_enabled", lambda: False)
    job.run_sincronizza_etoro()
    db.expire_all()
    assert db.get(EtoroPosizione, 1).notificata is True


def test_la_notifica_di_uno_strumento_fuori_catalogo_usa_il_simbolo(monkeypatch) -> None:
    from types import SimpleNamespace as NS

    pos = NS(lato="short", leva=2, regolamento="crypto_margine", motivo_chiusura="non_trovata",
             prezzo_apertura=60000.0, prezzo_chiusura=None, profitto_netto_usd=None,
             margine_usd=None, importo_usd=100.0)
    strum = NS(simbolo="BTC", instrument_id=100000)
    mandati: list[str] = []
    monkeypatch.setattr(notifier_service, "_telegram_enabled", lambda: True)
    monkeypatch.setattr(notifier_service, "_send_telegram", lambda text, what: mandati.append(text) or True)
    assert notifier_service.notify_etoro_chiuse([(pos, strum, None)]).sent is True
    assert "BTC" in mandati[0] and "Short ×2" in mandati[0] and "non trovata" in mandati[0]
    assert notifier_service.notify_etoro_chiuse([]).reason == "no_alerts"


# ─── I job delle watchlist e dello storico (FA-125, FA-127) ─────────────────


def test_i_job_senza_chiavi_non_chiamano_niente(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "etoro_api_key", "")
    monkeypatch.setattr(etoro_client, "get", lambda *a, **k: pytest.fail("chiamata"))
    job.run_sincronizza_watchlist_etoro()
    job.run_recupera_storico_etoro()


def test_il_job_delle_watchlist_crea_i_preferiti(db: Session, etoro: FintoEtoro, portafoglio) -> None:
    from app.models.preferito import Preferito

    etoro.watchlist = {"watchlists": [{"name": "Tech", "watchlistType": "Static", "totalItems": 1,
                                       "items": [{"itemId": 1001, "itemType": "Instrument"}]}]}
    job.run_sincronizza_watchlist_etoro()
    db.expire_all()
    assert db.get(Preferito, portafoglio.id).origine == "etoro"


def test_il_job_delle_watchlist_sopravvive_a_un_errore(db: Session, etoro: FintoEtoro) -> None:
    etoro.watchlist = {"senza": "watchlists"}
    job.run_sincronizza_watchlist_etoro()


def test_il_job_dello_storico_salva_i_giorni(db: Session, etoro: FintoEtoro) -> None:
    from app.models.etoro import EtoroPatrimonioGiorno

    ieri = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
    etoro.saldi = {"snapshots": [{"date": ieri, "accountSnapshots": [
        {"accountType": "Trading", "displayTotal": 100.0, "displayCash": 1.0, "displayPnl": 2.0}]}]}
    job.run_recupera_storico_etoro()
    db.expire_all()
    assert len(db.query(EtoroPatrimonioGiorno).all()) == 1


def test_il_job_dello_storico_sopravvive_a_un_errore(db: Session, etoro: FintoEtoro, monkeypatch) -> None:
    def giu(*a, **k):
        raise UpstreamUnavailable("giu'", source="etoro", op="patrimonio")

    monkeypatch.setattr(etoro_client, "get", giu)
    job.run_recupera_storico_etoro()
