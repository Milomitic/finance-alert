"""`_fetch_active_alerts` viene ESEGUITA, non solo scritta.

⚠️ Il cancello del codice morto l'ha trovata mai eseguita, e aveva ragione a
fermare la pipeline. La funzione e' la cucitura di rete che porta le ANNOTAZIONI
degli alert — cioe' la differenza fra «KubePodCrashLooping» e «il pod app
riavvia da 12 minuti». Ogni test della scheda inietta un finto al suo posto,
quindi la sua analisi del payload non girava da nessuna parte: un refuso in
`data["alerts"]` avrebbe fatto tornare `None` per sempre e la scheda avrebbe
mostrato il solo nome — il degrado PREVISTO dal contratto, indistinguibile da
un guasto. Nessun errore, nessun log, nessuno che se ne accorge.

⚠️ E' anche l'unica funzione del modulo che apre un socket: se la sua analisi
fosse sbagliata, la conferma richiederebbe un cluster. Qui l'unico pezzo finto
e' `urlopen`; tutto il resto — costruzione dell'URL, guardia sullo schema,
decodifica, controlli di forma — e' il codice vero.
"""

import io
import json
import urllib.error
import urllib.request

import pytest

from app.services import infra_health_service as ihs


def _risposta(corpo: object) -> object:
    """Un finto abbastanza fedele: `urlopen` torna un gestore di contesto."""
    dati = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()

    class _R(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.close()
            return False

    return _R(dati)


@pytest.fixture
def chiamate(monkeypatch):
    """Registra gli URL richiesti, cosi' si puo' verificare COSA viene chiesto."""
    visti: list[str] = []

    def _finto(url, timeout=None):
        visti.append(url)
        return _risposta(_finto.corpo)

    _finto.corpo = {"status": "success", "data": {"alerts": []}}
    monkeypatch.setattr(urllib.request, "urlopen", _finto)
    return visti, _finto


def test_interroga_alerts_e_non_query(chiamate):
    """⚠️ L'endpoint giusto e' meta' del valore della funzione.

    `/api/v1/query` sulla serie `ALERTS` porta solo le ETICHETTE: da li' si sa
    il nome di un alert, non che cosa dice. `summary` e `description` sono
    annotazioni e vivono solo su `/api/v1/alerts`.
    """
    visti, finto = chiamate
    finto.corpo = {
        "status": "success",
        "data": {"alerts": [
            {"labels": {"alertname": "KubePodCrashLooping", "severity": "warning"},
             "annotations": {"summary": "Il pod app riavvia in ciclo"},
             "activeAt": "2026-09-13T00:00:00Z"},
        ]},
    }
    fuori = ihs._fetch_active_alerts()
    assert len(visti) == 1
    assert visti[0].endswith("/api/v1/alerts"), visti[0]
    assert fuori is not None
    assert fuori[0]["annotations"]["summary"] == "Il pod app riavvia in ciclo"


@pytest.mark.parametrize("corpo", [
    {"status": "error", "data": {"alerts": []}},   # Prometheus dice di no
    {"status": "success", "data": []},             # data non e' un oggetto
    {"status": "success", "data": {}},             # manca la chiave alerts
    {"status": "success", "data": {"alerts": {}}}, # alerts non e' una lista
    [],                                            # envelope non e' un oggetto
    b"{non json",                                  # corpo illeggibile
])
def test_un_payload_inatteso_diventa_None_e_non_una_lista_vuota(chiamate, corpo):
    """⚠️ Assente non e' zero, ed e' la regola che questa funzione applica.

    Una lista vuota significa «nessun alert attivo», cioe' tutto bene. Se un
    payload malformato producesse quella, un guasto del monitoraggio si
    leggerebbe sulla scheda come salute — la stessa inversione che CLAUDE.md
    impone di evitare ovunque un valore possa mancare.
    """
    _, finto = chiamate
    finto.corpo = corpo
    assert ihs._fetch_active_alerts() is None


def test_un_guasto_di_rete_non_propaga(chiamate, monkeypatch):
    def _rotto(url, timeout=None):
        raise urllib.error.URLError("connessione rifiutata")

    monkeypatch.setattr(urllib.request, "urlopen", _rotto)
    assert ihs._fetch_active_alerts() is None


def test_uno_schema_non_http_non_apre_nessun_socket(monkeypatch):
    """⚠️ La guardia sullo schema va provata PRIMA della rete, non dopo.

    `prometheus_url` arriva dalla configurazione. Con `file://` — o con un
    valore vuoto che collassa a qualcosa senza host — `urlopen` leggerebbe il
    filesystem del pod. Il test lo verifica per ASSENZA di chiamata, non per
    valore di ritorno: entrambi i rami tornano None, quindi solo il contatore
    distingue «rifiutato» da «tentato e fallito».
    """
    monkeypatch.setattr(ihs.settings, "prometheus_url", "file:///etc/passwd", raising=False)
    tentativi: list[str] = []
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda url, timeout=None: tentativi.append(url) or _risposta({}),
    )
    assert ihs._fetch_active_alerts() is None
    assert tentativi == [], f"e' stato aperto un socket verso {tentativi}"
