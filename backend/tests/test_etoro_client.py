"""Il client eToro: spento senza chiavi, solo lettura, 429 riprovato, chiavi mai nei log (FA-123)."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
import requests

from app.core.config import settings
from app.core.errors import RateLimitError, UpstreamTimeout, UpstreamUnavailable
from app.services import etoro_client
from app.services.etoro_client import EtoroAccessoNegato, EtoroNonConfigurato, _Limitatore

CHIAVE_APP = "app-chiave-di-prova"
CHIAVE_UTENTE = "utente-chiave-di-prova"


class _Risposta:
    def __init__(self, status: int, corpo=None, headers=None) -> None:
        self.status_code = status
        self._corpo = corpo
        self.headers = headers or {}

    def json(self):
        if isinstance(self._corpo, Exception):
            raise self._corpo
        return self._corpo


@pytest.fixture
def chiavi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "etoro_api_key", CHIAVE_APP)
    monkeypatch.setattr(settings, "etoro_user_key", CHIAVE_UTENTE)
    # Il limitatore vero non serve qui e non deve far dormire i test.
    monkeypatch.setattr(etoro_client, "_limitatore", _Limitatore(1000, 60.0))
    monkeypatch.setattr(etoro_client.time, "sleep", lambda s: None)


class _Registro(list):
    """Le richieste fatte, in ordine; `risposte` sono quelle da restituire."""

    def __init__(self) -> None:
        super().__init__()
        self.risposte: list[_Risposta] = []


@pytest.fixture
def chiamate(monkeypatch: pytest.MonkeyPatch, chiavi) -> _Registro:
    registro = _Registro()

    def finta(metodo, url, headers=None, timeout=None, **kw):
        registro.append({"metodo": metodo, "url": url, "headers": headers, **kw})
        return registro.risposte.pop(0)

    monkeypatch.setattr(etoro_client.requests, "request", finta)
    return registro


def test_senza_chiavi_e_spento_e_lo_dice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "etoro_api_key", "")
    monkeypatch.setattr(settings, "etoro_user_key", "x")
    assert etoro_client.configurato() is False
    with pytest.raises(EtoroNonConfigurato):
        etoro_client.get("/api/v1/watchlists", op="watchlist")


def test_una_chiave_di_soli_spazi_non_conta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "etoro_api_key", "   ")
    monkeypatch.setattr(settings, "etoro_user_key", CHIAVE_UTENTE)
    assert etoro_client.configurato() is False


def test_le_intestazioni_sono_quelle_della_documentazione(chiamate) -> None:
    chiamate.risposte.append(_Risposta(200, {"ok": True}))
    assert etoro_client.get("/api/v1/me", op="identita") == {"ok": True}
    h = chiamate[0]["headers"]
    assert h["x-api-key"] == CHIAVE_APP
    assert h["x-user-key"] == CHIAVE_UTENTE
    assert len(h["x-request-id"]) == 36
    assert chiamate[0]["url"] == "https://public-api.etoro.com/api/v1/me"


def test_ogni_richiesta_ha_un_id_nuovo(chiamate) -> None:
    chiamate.risposte.extend([_Risposta(200, {}), _Risposta(200, {})])
    etoro_client.get("/api/v1/me", op="identita")
    etoro_client.get("/api/v1/me", op="identita")
    assert chiamate[0]["headers"]["x-request-id"] != chiamate[1]["headers"]["x-request-id"]


def test_un_429_si_riprova_e_poi_passa(chiamate) -> None:
    chiamate.risposte.extend([_Risposta(429, headers={"Retry-After": "1"}), _Risposta(200, {"n": 1})])
    assert etoro_client.get("/api/v1/me", op="identita") == {"n": 1}
    assert len(chiamate) == 2


def test_un_429_che_non_passa_diventa_rate_limit(chiamate) -> None:
    chiamate.risposte.extend([_Risposta(429)] * (etoro_client._TENTATIVI_429 + 1))
    with pytest.raises(RateLimitError):
        etoro_client.get("/api/v1/me", op="identita")
    assert len(chiamate) == etoro_client._TENTATIVI_429 + 1


@pytest.mark.parametrize("status", [401, 403])
def test_accesso_negato_spiega_le_cause_senza_la_chiave(chiamate, status: int) -> None:
    chiamate.risposte.append(_Risposta(status))
    with pytest.raises(EtoroAccessoNegato) as e:
        etoro_client.get("/api/v1/me", op="identita")
    assert "IP non ammesso" in str(e.value)
    assert CHIAVE_APP not in str(e.value) and CHIAVE_UTENTE not in str(e.value)


def test_un_errore_del_server_e_upstream_unavailable(chiamate) -> None:
    chiamate.risposte.append(_Risposta(503))
    with pytest.raises(UpstreamUnavailable):
        etoro_client.get("/api/v1/me", op="identita")


def test_una_risposta_non_json_e_un_errore_non_un_vuoto(chiamate) -> None:
    chiamate.risposte.append(_Risposta(200, ValueError("non json")))
    with pytest.raises(UpstreamUnavailable):
        etoro_client.get("/api/v1/me", op="identita")


def test_il_timeout_e_tipizzato(monkeypatch: pytest.MonkeyPatch, chiavi) -> None:
    def lento(*a, **k):
        raise requests.Timeout("lento")

    monkeypatch.setattr(etoro_client.requests, "request", lento)
    with pytest.raises(UpstreamTimeout):
        etoro_client.get("/api/v1/me", op="identita")


# ─── Sola lettura ───────────────────────────────────────────────────────────


def test_un_post_fuori_elenco_non_parte(chiamate) -> None:
    with pytest.raises(ValueError, match="non scrive"):
        etoro_client.post_lettura("/api/v2/trading/execution/orders", {"x": 1}, op="ordine")
    assert chiamate == []


def test_un_post_di_lettura_parte(chiamate) -> None:
    chiamate.risposte.append(_Risposta(200, {"costs": []}))
    etoro_client.post_lettura("/api/v2/trading/info/costs", {"action": "open"}, op="costi")
    assert chiamate[0]["metodo"] == "POST"
    assert chiamate[0]["json"] == {"action": "open"}


def test_nessun_post_di_lettura_tocca_l_esecuzione() -> None:
    """L'elenco non deve mai contenere un percorso di esecuzione o di modifica."""
    for p in etoro_client.POST_DI_LETTURA:
        assert "/execution/" not in p and "/positions/" not in p, p


def test_il_modulo_non_usa_altri_verbi() -> None:
    """Il solo verbo HTTP del modulo e' quello passato da `get` e `post_lettura`.
    Guarda la SORGENTE: un `requests.post` aggiunto altrove sarebbe invisibile a
    qualunque test di comportamento che non lo chiami."""
    sorgente = Path(inspect.getsourcefile(etoro_client)).read_text(encoding="utf-8")
    albero = ast.parse(sorgente)
    verbi = set()
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute):
            if isinstance(nodo.func.value, ast.Name) and nodo.func.value.id == "requests":
                verbi.add(nodo.func.attr)
        if isinstance(nodo, ast.Constant) and nodo.value in {"PUT", "PATCH", "DELETE"}:
            verbi.add(nodo.value)
    assert verbi == {"request"}, verbi
    letterali = {n.value for n in ast.walk(albero) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert {"GET", "POST"} <= letterali


# ─── Limitatore ─────────────────────────────────────────────────────────────


def test_il_limitatore_aspetta_quando_la_finestra_e_piena() -> None:
    orologio = [0.0]
    attese: list[float] = []

    def dormi(s: float) -> None:
        attese.append(s)
        orologio[0] += s

    lim = _Limitatore(3, 60.0, ora=lambda: orologio[0], dormi=dormi)
    for _ in range(3):
        lim.acquisisci()
    assert attese == []
    lim.acquisisci()  # la quarta aspetta che la prima esca dalla finestra
    assert attese and sum(attese) == pytest.approx(60.0)


def test_il_limite_resta_sotto_quello_di_etoro() -> None:
    assert etoro_client.LIMITE_AL_MINUTO < 60
