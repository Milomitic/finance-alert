"""Eccezioni tipate per il fetching da sorgenti esterne.

Sostituiscono i `except Exception: # noqa: BLE001` nei router consumer-facing.
La gerarchia è volutamente piatta — non costruiamo una ontologia, solo i 3
casi che dobbiamo distinguere in produzione per logging/metriche.

Uso tipico:

    try:
        data = yf_call(...)
    except requests.Timeout as e:
        raise UpstreamTimeout(str(e), source="yfinance", op="fundamentals") from e
    except RateLimited429 as e:  # quello che lancia yfinance su 429
        raise RateLimitError(str(e), source="yfinance", op="fundamentals") from e

E nei router:

    except UpstreamError as e:
        logger.warning(f"upstream {e.source}.{e.op} unavailable: {e}")
        # fallback / 503
"""


class UpstreamError(Exception):
    """Base: qualsiasi fallimento durante la chiamata a una sorgente esterna."""

    def __init__(self, message: str = "", *, source: str = "", op: str = "") -> None:
        super().__init__(message)
        self.source = source
        self.op = op


class RateLimitError(UpstreamError):
    """L'upstream ha risposto 429 o equivalente."""


class UpstreamTimeout(UpstreamError):
    """Timeout di rete verso l'upstream."""


class UpstreamUnavailable(UpstreamError):
    """L'upstream è raggiungibile ma risponde con errore (5xx) o body invalido."""
