"""Negoziabile su eToro, e quanto costa (FA-126).

Le risposte finte hanno la forma letta dal pod il 2026-10-06: `symbols` sulla
lista degli strumenti, e un preventivo che porta l'importo in `value` (non in
`amount` come la specifica) con l'overnight di ENI.MI in EUR.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.core.errors import UpstreamUnavailable
from app.main import app
from app.models import Alert, Stock, User
from app.models.etoro import EtoroCatalogo
from app.scheduler.jobs import sincronizza_etoro as job
from app.services import etoro_catalogo_service as cat
from app.services import etoro_client, fx_service
from tests.test_etoro_portafoglio import FintoEtoro, strumento

ADESSO = datetime(2026, 10, 6, 9, 0, tzinfo=UTC)


@pytest.fixture
def etoro(monkeypatch: pytest.MonkeyPatch) -> FintoEtoro:
    monkeypatch.setattr(settings, "etoro_api_key", "a")
    monkeypatch.setattr(settings, "etoro_user_key", "b")
    finto = FintoEtoro()
    monkeypatch.setattr(etoro_client, "get", finto.get)
    cat.svuota_cache()
    return finto


@pytest.fixture
def catalogo(db: Session, etoro: FintoEtoro) -> dict[str, Stock]:
    out = {}
    for t, n in [("SOXL", "Direxion Semi Bull 3X"), ("LABU", "Direxion Biotech Bull 3X"),
                 ("ENI.MI", "Eni S.p.A."), ("BRK-B", "Berkshire Hathaway"), ("ZZZZ", "Non su eToro")]:
        s = Stock(ticker=t, exchange="X", name=n)
        db.add(s)
        out[t] = s
    db.commit()
    etoro.anagrafica.update({
        3226: strumento(3226, "SOXL", "Direxion Daily Semiconductor Bull 3X ETF", tipo="ETF"),
        3199: strumento(3199, "LABU.US", "Direxion Daily S&P Biotech Bull 3X ETF", tipo="ETF"),
        1283: strumento(1283, "ENI.MI", "Eni SpA"),
        1111: strumento(1111, "BRK.B", "Berkshire Hathaway Inc"),
    })
    return out


def test_le_varianti_di_simbolo() -> None:
    assert cat.varianti("SOXL") == ["SOXL", "SOXL.US"]
    assert cat.varianti("brk-b") == ["BRK-B", "BRK.B"]
    # Un suffisso di borsa resta com'e': ENI.MI su eToro e' ENI.MI.
    assert cat.varianti("ENI.MI") == ["ENI.MI"]


def test_l_aggiornamento_trova_i_titoli_con_le_loro_varianti(db: Session, etoro: FintoEtoro, catalogo) -> None:
    trovati, cercati = cat.aggiorna(db, adesso=ADESSO)
    assert (trovati, cercati) == (4, 5)
    righe = {r.stock_id: r.simbolo for r in db.query(EtoroCatalogo).all()}
    assert righe == {
        catalogo["SOXL"].id: "SOXL", catalogo["LABU"].id: "LABU.US",
        catalogo["ENI.MI"].id: "ENI.MI", catalogo["BRK-B"].id: "BRK.B",
    }
    # Una variante per chiamata, a lotti: tutte le richieste portano simboli.
    assert all("symbols" in p for _, p in etoro.chiamate)


def test_la_variante_esatta_vince(db: Session, etoro: FintoEtoro, catalogo) -> None:
    etoro.anagrafica[9999] = strumento(9999, "SOXL.US", "doppione", tipo="ETF")
    cat.aggiorna(db, adesso=ADESSO)
    assert db.get(EtoroCatalogo, catalogo["SOXL"].id).instrument_id == 3226


def test_un_errore_non_svuota_la_tabella(db: Session, etoro: FintoEtoro, catalogo, monkeypatch) -> None:
    cat.aggiorna(db, adesso=ADESSO)

    def giu(*a, **k):
        raise UpstreamUnavailable("giu'", source="etoro", op="strumenti")

    monkeypatch.setattr(etoro_client, "get", giu)
    with pytest.raises(UpstreamUnavailable):
        cat.aggiorna(db, adesso=ADESSO)
    assert len(db.query(EtoroCatalogo).all()) == 4


def test_il_filtro_della_lista_segnali(db: Session, etoro: FintoEtoro, catalogo) -> None:
    from app.services import alert_service

    cat.aggiorna(db, adesso=ADESSO)
    for t in ("SOXL", "ZZZZ"):
        db.add(Alert(signal_name="volume_breakout", stock_id=catalogo[t].id, trigger_price=1.0, snapshot="{}"))
    db.commit()
    _, tutti, _ = alert_service.list_alerts(db, limit=50)
    _, solo, _ = alert_service.list_alerts(db, limit=50, solo_etoro=True)
    assert (tutti, solo) == (2, 1)


# ─── I costi ────────────────────────────────────────────────────────────────


@pytest.fixture
def preventivo(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    corpi: list[dict] = []

    def finto(percorso, corpo, *, op):
        assert percorso == "/api/v2/trading/info/costs"
        corpi.append(corpo)
        valuta_notte = "EUR" if corpo["instrumentId"] == 1283 else "USD"
        return {"instrumentId": corpo["instrumentId"], "symbol": "X", "lastUpdated": "2026-10-05T16:46:34Z",
                "costs": [{"costType": "transactionFee", "currency": "USD", "value": 3.75},
                          {"costType": "markup", "currency": "USD", "value": 0.0},
                          {"costType": "marketSpread", "currency": "USD", "value": 0.77},
                          {"costType": "overnightFee", "currency": valuta_notte, "value": 0.71}]}

    monkeypatch.setattr(etoro_client, "post_lettura", finto)
    monkeypatch.setattr(fx_service, "to_usd", lambda v, c: v * 1.17 if c == "EUR" else None)
    return corpi


def test_il_preventivo_somma_apertura_e_legge_value(db: Session, etoro, catalogo, preventivo) -> None:
    cat.aggiorna(db, adesso=ADESSO)
    c = cat.costi(db, "SOXL", lato="long", leva=5, importo=500, stop=40.0)
    assert c.apertura_usd == pytest.approx(4.52)
    assert c.notte_usd == pytest.approx(0.71)
    assert c.weekend_usd == 0.0
    corpo = preventivo[0]
    assert (corpo["transaction"], corpo["leverage"], corpo["stopLossRate"], corpo["instrumentId"]) == ("buy", 5, 40.0, 3226)


def test_l_overnight_in_euro_si_converte(db: Session, etoro, catalogo, preventivo) -> None:
    cat.aggiorna(db, adesso=ADESSO)
    c = cat.costi(db, "ENI.MI", lato="short", leva=5, importo=500, stop=20.0)
    assert c.notte_usd == pytest.approx(0.71 * 1.17)
    assert preventivo[0]["transaction"] == "sellShort"


def test_un_cambio_ignoto_non_diventa_dollari(db: Session, etoro, catalogo, preventivo, monkeypatch) -> None:
    cat.aggiorna(db, adesso=ADESSO)
    monkeypatch.setattr(fx_service, "to_usd", lambda v, c: None)
    c = cat.costi(db, "ENI.MI", lato="long", leva=5, importo=500, stop=20.0)
    assert c.notte_usd is None
    assert [v.valuta for v in c.voci if v.tipo == "overnightFee"] == ["EUR"]


def test_il_preventivo_si_tiene_un_ora(db: Session, etoro, catalogo, preventivo) -> None:
    cat.aggiorna(db, adesso=ADESSO)
    orologio = [0.0]
    for _ in range(3):
        cat.costi(db, "SOXL", lato="long", leva=5, importo=500, stop=40.0, ora=lambda: orologio[0])
    assert len(preventivo) == 1
    orologio[0] += 3601
    cat.costi(db, "SOXL", lato="long", leva=5, importo=500, stop=40.0, ora=lambda: orologio[0])
    assert len(preventivo) == 2


def test_un_titolo_non_su_etoro_non_chiede_niente(db: Session, etoro, catalogo, preventivo) -> None:
    cat.aggiorna(db, adesso=ADESSO)
    assert cat.costi(db, "ZZZZ", lato="long", leva=5, importo=500, stop=1.0) is None
    assert preventivo == []


# ─── API e job ──────────────────────────────────────────────────────────────


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_gli_endpoint(client: TestClient, db: Session, etoro, catalogo, preventivo) -> None:
    cat.aggiorna(db, adesso=ADESSO)
    assert client.get("/api/etoro/disponibile/SOXL").json() == {"disponibile": True, "simbolo": "SOXL", "tipo": "ETF"}
    assert client.get("/api/etoro/disponibile/ZZZZ").json()["disponibile"] is False
    c = client.get("/api/etoro/costi", params={"ticker": "SOXL", "leva": 5, "importo": 500, "stop": 40}).json()
    assert c["disponibile"] is True and c["apertura_usd"] == pytest.approx(4.52)
    assert client.get("/api/etoro/costi", params={"ticker": "ZZZZ"}).json()["disponibile"] is False
    assert client.get("/api/etoro/costi", params={"ticker": "SOXL", "lato": "boh"}).status_code == 422
    r = client.get("/api/alerts", params={"solo_etoro": "true"})
    assert r.status_code == 200


def test_i_costi_con_eToro_giu_sono_502(client: TestClient, db: Session, etoro, catalogo, monkeypatch) -> None:
    cat.aggiorna(db, adesso=ADESSO)

    def giu(*a, **k):
        raise UpstreamUnavailable("giu'", source="etoro", op="costi")

    monkeypatch.setattr(etoro_client, "post_lettura", giu)
    assert client.get("/api/etoro/costi", params={"ticker": "SOXL", "stop": 40}).status_code == 502


def test_i_costi_senza_chiavi(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "etoro_api_key", "")
    assert client.get("/api/etoro/costi", params={"ticker": "SOXL"}).json()["disponibile"] is False


def test_il_job_settimanale(db: Session, etoro, catalogo) -> None:
    job.run_aggiorna_catalogo_etoro()
    db.expire_all()
    assert len(db.query(EtoroCatalogo).all()) == 4


def test_il_job_settimanale_senza_chiavi_e_con_eToro_giu(db: Session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "etoro_api_key", "")
    job.run_aggiorna_catalogo_etoro()
    monkeypatch.setattr(settings, "etoro_api_key", "a")
    monkeypatch.setattr(settings, "etoro_user_key", "b")

    def giu(*a, **k):
        raise UpstreamUnavailable("giu'", source="etoro", op="strumenti")

    monkeypatch.setattr(etoro_client, "get", giu)
    job.run_aggiorna_catalogo_etoro()


def test_il_dettaglio_del_titolo_porta_su_etoro(client: TestClient, db: Session, etoro, catalogo, monkeypatch) -> None:
    """Nella stessa risposta del dettaglio: un'etichetta arrivata dopo andrebbe
    a capo e sposterebbe l'intestazione."""
    from app.services import live_quote_service

    monkeypatch.setattr(live_quote_service, "get_quote", lambda *a, **k: None, raising=True)
    cat.aggiorna(db, adesso=ADESSO)
    soxl = client.get("/api/stocks/SOXL/detail")
    zzzz = client.get("/api/stocks/ZZZZ/detail")
    assert soxl.status_code == 200, soxl.text
    assert soxl.json()["su_etoro"] is True
    assert zzzz.json()["su_etoro"] is False
