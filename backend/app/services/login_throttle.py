"""Throttling in-memory dei login falliti (B4-11, versione light).

Dopo `settings.login_max_failed_attempts` fallimenti CONSECUTIVI per uno
username, il login risponde 429 + `Retry-After` finché non passano
`settings.login_lockout_seconds` dall'ULTIMO fallimento (finestra sliding:
ogni nuovo fallimento reale la fa ripartire; un tentativo rifiutato con 429
NON la estende, così un attaccante non può auto-prolungarsi il lockout di
un utente legittimo all'infinito). Un login riuscito azzera il contatore.

Stato process-lifetime BY DESIGN: app local-first a processo singolo — un
riavvio del backend azzera i contatori e va bene così (niente tabella di
lockout persistente, sproporzionata per questo threat model). Il lock serve
solo perché uvicorn serve le richieste su thread diversi.
"""
import math
import threading
import time
from dataclasses import dataclass

from app.core.config import settings


@dataclass
class _FailState:
    failures: int
    last_failure: float  # time.monotonic() dell'ultimo fallimento


_lock = threading.Lock()
_state: dict[str, _FailState] = {}
_MAX_TRACKED_USERS = 4096


def _prune_expired(now: float) -> None:
    expired = [
        username for username, state in _state.items()
        if now - state.last_failure >= settings.login_lockout_seconds
    ]
    for username in expired:
        del _state[username]


def _now() -> float:
    # Seam per i test (monkeypatch): monotonic evita salti da NTP/ora legale.
    return time.monotonic()


def retry_after_seconds(username: str) -> int | None:
    """Secondi di lockout residui (>= 1) se lo username è bloccato, altrimenti
    None. Non muta lo stato — vedi docstring modulo sul perché un 429 non
    estende la finestra."""
    with _lock:
        now = _now()
        if len(_state) >= _MAX_TRACKED_USERS:
            _prune_expired(now)
        st = _state.get(username)
        # Preserve existing lockouts when random usernames fill the table.
        # Unknown accounts wait for capacity instead of evicting a victim.
        if st is None and len(_state) >= _MAX_TRACKED_USERS:
            return max(1, settings.login_lockout_seconds)
        if st is None or st.failures < settings.login_max_failed_attempts:
            return None
        remaining = settings.login_lockout_seconds - (now - st.last_failure)
        if remaining <= 0:
            return None
        return max(1, math.ceil(remaining))


def record_failure(username: str) -> None:
    """Registra un fallimento reale (credenziali sbagliate) e fa scorrere la
    finestra di lockout."""
    with _lock:
        if len(_state) >= _MAX_TRACKED_USERS:
            _prune_expired(_now())
        st = _state.get(username)
        if st is None:
            if len(_state) < _MAX_TRACKED_USERS:
                _state[username] = _FailState(failures=1, last_failure=_now())
        else:
            st.failures += 1
            st.last_failure = _now()


def record_success(username: str) -> None:
    """Login riuscito: azzera il contatore (i fallimenti contano solo se
    consecutivi)."""
    with _lock:
        _state.pop(username, None)


def reset() -> None:
    """Helper per i test: svuota tutto lo stato del throttle."""
    with _lock:
        _state.clear()
