"""Exponential backoff decorator per chiamate I/O verso upstream esterni.

Filosofia:
- I retry hanno senso SOLO per errori transitori (timeout, 429, 5xx, dns hiccup).
  Per errori semantici (404, validation) il retry è puro spreco.
- Quindi `on=` è obbligatorio e tipato: passi le classi che vuoi ri-tentare.
- Jitter è on by default (smooth thundering herd) ma disattivabile per testing.
- Niente async — i nostri service sono sync. Se in futuro andremo async,
  duplichiamo la funzione, non aggiungiamo branch.
"""
import random
import time
from collections.abc import Callable
from functools import wraps
from typing import TypeVar

from loguru import logger

T = TypeVar("T")


def with_backoff(
    *,
    retries: int,
    base_delay: float,
    max_delay: float,
    on: tuple[type[BaseException], ...],
    jitter: bool = True,
):
    """Restituisce un decorator che ri-tenta `fn` fino a `retries` volte in totale
    per le sole eccezioni in `on`. Il contatore include la chiamata iniziale:
    `retries=4` → al massimo 4 tentativi (1 iniziale + 3 retry).

    Delay: `min(base_delay * 2**attempt, max_delay)`, opzionale jitter ±25%.
    L'ultimo tentativo fallito NON dorme prima di rilanciare l'eccezione.
    """
    if retries < 0:
        raise ValueError("retries must be >= 0")

    def deco(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapped(*args, **kwargs) -> T:
            attempt = 0
            while True:
                try:
                    return fn(*args, **kwargs)
                except on as exc:
                    attempt += 1
                    if attempt >= retries:
                        raise
                    d = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    if jitter:
                        d *= 1.0 + random.uniform(-0.25, 0.25)
                    logger.debug(
                        f"[retry] {fn.__name__} attempt {attempt}/{retries} "
                        f"after {type(exc).__name__}: sleeping {d:.3f}s"
                    )
                    time.sleep(d)

        return wrapped

    return deco
