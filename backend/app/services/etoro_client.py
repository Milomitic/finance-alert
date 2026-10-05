"""Client della Public API di eToro, in SOLA LETTURA (FA-123).

Una coppia di chiavi generata dall'utente nelle impostazioni del proprio conto
(Impostazioni -> Trading -> API Key Management): `x-api-key` identifica
l'applicazione, `x-user-key` il conto. Ogni richiesta porta anche un
`x-request-id` nuovo. Senza le due chiavi il client e' SPENTO e lo dice
(`configurato()`), non solleva al primo uso: le funzioni che lo usano si
saltano da sole, come FRED senza la sua chiave.

⚠️ Perche' sola lettura, e perche' anche qui oltre che nella chiave. La chiave
dell'app nasce col permesso «Read», e gia' quello basta a eToro per rifiutare
un ordine. Ma una chiave rigenerata per sbaglio con «Write» renderebbe
eseguibile qualunque POST, e il motore di questa app e' un filtro di
attenzione, non un previsore (sette studi nulli, vedi CLAUDE.md): un ordine non
deve poter partire da qui. Quindi il modulo espone `get` e un `post_lettura`
limitato a un ELENCO di percorsi che sono POST solo di forma — un preventivo di
costi, una verifica di negoziabilita' — e nient'altro. Un test fissa che non
esistano altri verbi.

Limiti di eToro: 60 richieste al minuto per chiave sulle letture, su finestra
mobile, con quote CONDIVISE fra gruppi di endpoint. Il limitatore qui tiene
50, cosi' un orologio un po' storto o un'altra chiamata nello stesso minuto
non producono un 429; un 429 comunque si riprova con attesa crescente.
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from typing import Any

import requests
from loguru import logger

from app.core.config import settings
from app.core.errors import RateLimitError, UpstreamTimeout, UpstreamUnavailable
from app.services import data_source_metrics

BASE = "https://public-api.etoro.com"
FONTE = "etoro"
_TIMEOUT = 20.0
_USER_AGENT = "FinanceAlert/0.1 (personal use, read-only)"

#: Sotto i 60/minuto di eToro, di proposito.
LIMITE_AL_MINUTO = 50
_FINESTRA_S = 60.0
#: Tentativi su un 429, con attesa 2, 4, 8 s (o quella che eToro dichiara).
_TENTATIVI_429 = 3
_ATTESA_MASSIMA_S = 30.0

#: I soli POST ammessi: sono letture che eToro espone come POST perche'
#: prendono un corpo. Aggiungerne uno vuol dire leggerne la specifica e
#: verificare che non cambi lo stato del conto.
POST_DI_LETTURA: frozenset[str] = frozenset({
    "/api/v2/trading/info/costs",          # preventivo dei costi di un ordine ipotetico
    "/api/v2/trading/info/eligibility",    # lo strumento si puo' negoziare?
    "/api/v1/trading/info/aggregate-portfolio",  # istantanea filtrata del portafoglio
})


class EtoroNonConfigurato(UpstreamUnavailable):
    """Le due chiavi mancano: la funzione che le cerca e' spenta."""


class EtoroAccessoNegato(UpstreamUnavailable):
    """401/403: chiave scaduta, revocata, IP non ammesso o permesso mancante."""


def configurato() -> bool:
    return bool(settings.etoro_api_key.strip() and settings.etoro_user_key.strip())


class _Limitatore:
    """Finestra mobile di 60 s: al massimo `limite` richieste dentro la finestra.
    `acquisisci` aspetta il primo posto libero; il tempo e' iniettabile per i test."""

    def __init__(self, limite: int, finestra_s: float, *, ora=time.monotonic, dormi=time.sleep) -> None:
        self.limite = limite
        self.finestra_s = finestra_s
        self._ora = ora
        self._dormi = dormi
        self._istanti: deque[float] = deque()
        self._lock = threading.Lock()

    def acquisisci(self) -> None:
        while True:
            with self._lock:
                adesso = self._ora()
                while self._istanti and adesso - self._istanti[0] >= self.finestra_s:
                    self._istanti.popleft()
                if len(self._istanti) < self.limite:
                    self._istanti.append(adesso)
                    return
                attesa = self.finestra_s - (adesso - self._istanti[0])
            self._dormi(max(attesa, 0.05))


_limitatore = _Limitatore(LIMITE_AL_MINUTO, _FINESTRA_S)


def _intestazioni() -> dict[str, str]:
    return {
        "x-request-id": str(uuid.uuid4()),
        "x-api-key": settings.etoro_api_key.strip(),
        "x-user-key": settings.etoro_user_key.strip(),
        "Accept": "application/json",
        "User-Agent": _USER_AGENT,
    }


def _attesa_429(risposta: requests.Response, tentativo: int) -> float:
    dichiarata = risposta.headers.get("Retry-After")
    try:
        if dichiarata is not None:
            return min(float(dichiarata), _ATTESA_MASSIMA_S)
    except ValueError:
        pass
    return min(2.0 ** (tentativo + 1), _ATTESA_MASSIMA_S)


def _richiesta(metodo: str, percorso: str, op: str, **kwargs: Any) -> Any:
    if not configurato():
        raise EtoroNonConfigurato("chiavi eToro non configurate", source=FONTE, op=op)
    url = BASE + percorso
    for tentativo in range(_TENTATIVI_429 + 1):
        _limitatore.acquisisci()
        try:
            r = requests.request(metodo, url, headers=_intestazioni(), timeout=_TIMEOUT, **kwargs)
        except requests.Timeout as e:
            data_source_metrics.record_failure(FONTE, op, reason="timeout")
            raise UpstreamTimeout(f"eToro {percorso}: timeout", source=FONTE, op=op) from e
        except requests.RequestException as e:
            data_source_metrics.record_failure(FONTE, op, reason=type(e).__name__)
            raise UpstreamUnavailable(f"eToro {percorso}: {type(e).__name__}", source=FONTE, op=op) from e

        if r.status_code == 429:
            if tentativo < _TENTATIVI_429:
                attesa = _attesa_429(r, tentativo)
                logger.warning(f"[etoro] 429 su {percorso}, riprovo fra {attesa:.0f}s")
                time.sleep(attesa)
                continue
            data_source_metrics.record_failure(FONTE, op, reason="429")
            raise RateLimitError(f"eToro {percorso}: 429 dopo {_TENTATIVI_429} tentativi", source=FONTE, op=op)
        if r.status_code in (401, 403):
            # ⚠️ Mai il corpo della richiesta nel messaggio: contiene le chiavi
            # solo negli header, ma la regola resta «nessun dato di
            # autenticazione in un log».
            data_source_metrics.record_failure(FONTE, op, reason=str(r.status_code))
            raise EtoroAccessoNegato(
                f"eToro {percorso}: {r.status_code} — chiave scaduta o revocata, IP non "
                "ammesso o permesso mancante",
                source=FONTE, op=op,
            )
        if r.status_code >= 400:
            data_source_metrics.record_failure(FONTE, op, reason=str(r.status_code))
            raise UpstreamUnavailable(f"eToro {percorso}: HTTP {r.status_code}", source=FONTE, op=op)
        try:
            corpo = r.json()
        except ValueError as e:
            data_source_metrics.record_failure(FONTE, op, reason="json")
            raise UpstreamUnavailable(f"eToro {percorso}: risposta non JSON", source=FONTE, op=op) from e
        data_source_metrics.record_success(FONTE, op)
        return corpo
    raise AssertionError("irraggiungibile")  # pragma: no cover


def get(percorso: str, *, op: str, params: dict[str, Any] | None = None) -> Any:
    """GET su un endpoint di eToro. `op` e' l'etichetta della metrica."""
    return _richiesta("GET", percorso, op, params=params)


def post_lettura(percorso: str, corpo: dict[str, Any], *, op: str) -> Any:
    """POST SOLO sugli endpoint di lettura dichiarati in `POST_DI_LETTURA`."""
    if percorso not in POST_DI_LETTURA:
        raise ValueError(f"{percorso} non e' un POST di lettura: questo client non scrive")
    return _richiesta("POST", percorso, op, json=corpo)
