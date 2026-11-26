"""Una risposta sempre pronta: serve l'ultima e la rinfresca dietro (FA-179, fase B).

Il riepilogo della home a freddo impiegava 6,3 s e il paniere dei mercati
1,7 s, e «a freddo» capitava dopo ogni rilascio e dopo un periodo senza
traffico. Con questa cache:

- entro l'eta' massima la risposta esce dalla memoria;
- oltre, esce comunque SUBITO quella che c'e' e un solo thread la ricalcola;
- la prima richiesta in assoluto calcola sul posto (non c'e' niente da
  servire), ma il riscaldamento all'avvio e il job periodico la anticipano.

⚠️ Mai un thread durante i test: un thread lanciato da una richiesta
sopravvive al test e usa la sessione del test successivo (il segfault di
SQLite annotato in CLAUDE.md). Sotto pytest la cache calcola sempre sul
posto e non conserva niente fra una chiamata e l'altra, a meno che il test
non la accenda esplicitamente.
"""
from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from typing import Generic, TypeVar

from loguru import logger

T = TypeVar("T")


def _in_test() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


class CacheFresca(Generic[T]):
    def __init__(self, nome: str, eta_massima_s: float, calcola: Callable[[], T], *, attiva: bool | None = None):
        self.nome = nome
        self.eta_massima_s = eta_massima_s
        self._calcola = calcola
        self._attiva = attiva
        self._valore: T | None = None
        self._quando = 0.0
        self._lock = threading.Lock()
        self._in_corso = False

    def accesa(self) -> bool:
        return self._attiva if self._attiva is not None else not _in_test()

    def eta_s(self) -> float | None:
        return None if self._valore is None else time.monotonic() - self._quando

    def rinfresca(self) -> T:
        """Ricalcola sul posto e conserva. Per il job e il riscaldamento."""
        valore = self._calcola()
        with self._lock:
            self._valore, self._quando = valore, time.monotonic()
        return valore

    def _rinfresca_dietro(self) -> None:
        try:
            self.rinfresca()
        except Exception as e:  # noqa: BLE001
            # Resta servito il valore di prima: meglio vecchio di un errore.
            logger.warning(f"[cache {self.nome}] ricalcolo fallito: {e}")
        finally:
            with self._lock:
                self._in_corso = False

    def leggi(self) -> T:
        if not self.accesa():
            return self._calcola()
        with self._lock:
            valore, quando = self._valore, self._quando
            scaduta = valore is not None and time.monotonic() - quando > self.eta_massima_s
            parti = scaduta and not self._in_corso
            if parti:
                self._in_corso = True
        if valore is None:
            return self.rinfresca()
        if parti:
            threading.Thread(target=self._rinfresca_dietro, name=f"cache-{self.nome}", daemon=True).start()
        return valore

    def svuota(self) -> None:
        with self._lock:
            self._valore, self._quando = None, 0.0
