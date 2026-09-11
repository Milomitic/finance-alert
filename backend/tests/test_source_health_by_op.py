"""La sorgente degradata, detta dove il dato si consuma.

Voce 4.4 del piano, audit §7.5. La pagina Salute sapeva che Marketaux era
fuori servizio; la scheda News del dettaglio titolo mostrava semplicemente
meno articoli. Il degrado era visibile solo a chi andava a cercarlo, e
un'assenza inspiegata e peggio di un'assenza spiegata — la stessa distinzione
fra `—` e `0` che il repo applica ai numeri.

⚠️ LA CATENA E FONTE -> TIPO DI DATO -> SCHEDA, E SI FERMA LI. Il catalogo
lega ogni sorgente a un `op`, che e il tipo di dato; una scheda consuma un
tipo di dato. Quello che il contratto NON supporta e un impatto specifico per
titolo: nessuno sa quanti articoli in meno abbia AAPL per via di Marketaux, e
affermarlo sarebbe inventare una misura.

⚠️ IL MOTIVO DELL'ERRORE NON ESCE DA QUI. `last_failure_reason` e una stringa
grezza dell'upstream, troncata a 200 caratteri e non redatta; fra quelle
misurate in produzione l'11 settembre 2026 c'e
`HTTPSConnectionPool(host='finnhub.io', port=443): ...`, cioe una URL che puo
portare un token in query string. Sulla pagina Diagnostica ha senso, la
guarda un operatore. Su una scheda di prodotto e uno stack trace con dentro un
rischio di credenziale.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import User
from app.services import data_source_metrics


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _clean_metrics():
    """I contatori sono un singleton di processo."""
    data_source_metrics.reset()
    yield
    data_source_metrics.reset()


def _fail(source: str, op: str, n: int, reason: str) -> None:
    for _ in range(n):
        data_source_metrics.record_failure(source, op, reason)


def _ok(source: str, op: str, n: int) -> None:
    for _ in range(n):
        data_source_metrics.record_success(source, op)


def _get(client: TestClient, op: str):
    r = client.get(f"/api/platform/source-health?op={op}")
    assert r.status_code == 200, r.text
    return r.json()


def test_una_fonte_in_errore_compare_per_il_suo_tipo_di_dato(client):
    _fail("marketaux", "news", 40, "HTTP 429 — quota/rate-limit")
    got = _get(client, "news")
    assert [x["source"] for x in got] == ["marketaux"]
    assert got[0]["role"] == "fallback"
    assert got[0]["health"] in ("failing", "unavailable", "degraded")
    assert got[0]["label"] == "Marketaux — News"


def test_una_fonte_sana_non_compare(client):
    _ok("yfinance", "news", 50)
    assert _get(client, "news") == []


def test_una_fonte_mai_chiamata_non_e_un_degrado(client):
    """⚠️ `idle` non e un guasto.

    Una riserva mai servita e sana per omissione, e segnalarla metterebbe una
    riga permanente su una scheda che funziona — cioe' rumore che insegna a
    ignorare l'avviso proprio quando diventa vero.
    """
    assert _get(client, "news") == []


def test_il_degrado_di_un_tipo_di_dato_non_sporca_un_altro(client):
    """La catena si ferma al tipo di dato: la scheda News non deve annunciare
    che i fondamentali sono in difficolta."""
    _fail("yfinance", "fundamentals", 60, "Too Many Requests")
    assert _get(client, "news") == []
    assert [x["source"] for x in _get(client, "fundamentals")] == ["yfinance"]


def test_il_motivo_grezzo_non_esce_dall_endpoint(client):
    """Il contratto non ha un campo dove un token possa finire."""
    _fail("marketaux", "news", 40, "HTTPSConnectionPool(host='x', url=/v1?token=SEGRETO)")
    got = _get(client, "news")
    assert got, "serve almeno una riga, altrimenti l'asserzione sotto e vuota"
    for riga in got:
        assert "SEGRETO" not in repr(riga)
        assert "last_failure_reason" not in riga
        assert "reason" not in riga


def test_un_op_sconosciuto_e_un_errore_forte_e_non_una_lista_vuota(client):
    """⚠️ Un refuso nel frontend non deve rendere una scheda muta per sempre.

    Una lista vuota e indistinguibile da «tutto sano», che e la forma esatta
    del test vero di niente: il difetto non si vedrebbe mai.
    """
    r = client.get("/api/platform/source-health?op=nevvs")
    assert r.status_code == 422
    assert "news" in r.text


def test_l_op_e_obbligatorio(client):
    assert client.get("/api/platform/source-health").status_code == 422


def test_una_fonte_plan_gated_non_e_un_incidente(client):
    """⚠️ `unavailable` = tutti i fallimenti sono HTTP 403: il piano gratuito
    non comprende quell'endpoint.

    E un fatto di configurazione permanente, e l'app lo aveva gia deciso:
    `DataSourcesCard` lo colloca sotto `stale` nella gerarchia e lo dipinge
    slate con la nota «non un incidente». Trattarlo come degrado qui darebbe
    due significati allo stesso stato su due schermi — la forma esatta del
    difetto delle due tavolozze — e su una scheda sarebbe una riga permanente.
    Misurato in produzione: `finnhub/upgrades` ha 0 successi su 1272 chiamate.
    """
    _fail("finnhub", "upgrades", 300, "HTTP 403")
    stati = {s.source: s.health for s in __import__(
        "app.services.source_catalog", fromlist=["x"]).full_snapshot() if s.op == "upgrades"}
    assert stati["finnhub"] == "unavailable", f"il presupposto del test non regge: {stati}"
    assert _get(client, "upgrades") == []


def test_gli_stati_consumabili_sono_esattamente_tre(client):
    """Il confine e una decisione, non un effetto collaterale: se qualcuno lo
    sposta, deve farlo apposta."""
    from app.services.source_catalog import _DEGRADED_STATES
    assert {"degraded", "failing", "stale"} == _DEGRADED_STATES
