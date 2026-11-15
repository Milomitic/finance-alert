"""Le quotazioni di riserva da Finnhub, quando Yahoo limita (FA-158).

Quando la corsia delle quotazioni di `yfinance_health` e' aperta, il prezzo
di un titolo USA arriva da Finnhub (`/quote`) invece che dall'ultima chiusura
salvata. Il prezzo porta la sua fonte (`source="finnhub"`): a schermo e nei log
si sa da dove viene.

⚠️ Tre limiti, tutti voluti:

1. **Solo titoli USA** (ticker senza suffisso di borsa): il piano gratuito di
   Finnhub risponde 403 su ogni altro mercato, misurato il 2026-11-15 su
   UCG.MI, ENI.MI, SAP.DE e SHEL.L.
2. **Al piu' `PER_MINUTO` richieste al minuto**, contate qui: il piano gratuito
   ne concede 60, e un cruscotto aperto chiede decine di titoli insieme. Oltre
   il tetto la risposta e' None e il chiamante usa il ripiego di prima.
3. **Mai solleva**: un guasto di Finnhub non deve togliere la quotazione di
   ripiego che c'era gia'.

`c == 0` nella risposta vuol dire «simbolo sconosciuto», non «prezzo zero».
"""
from __future__ import annotations

import threading
import time
from collections import deque

import requests
from loguru import logger

from app.core.config import settings

_URL = "https://finnhub.io/api/v1/quote"
PER_MINUTO = 50
_TIMEOUT = 4.0
_chiamate: deque[float] = deque()
_lock = threading.Lock()


def disponibile(ticker: str) -> bool:
    """Finnhub puo' rispondere per questo ticker: chiave presente, titolo USA."""
    return bool(settings.finnhub_api_key) and "." not in ticker and not ticker.startswith("^")


def _posto_libero(ora: float) -> bool:
    with _lock:
        while _chiamate and ora - _chiamate[0] > 60.0:
            _chiamate.popleft()
        if len(_chiamate) >= PER_MINUTO:
            return False
        _chiamate.append(ora)
        return True


def quota(ticker: str, *, ora=time.time) -> dict | None:
    """{price, prev_close, change_abs, change_pct, day_open, day_high,
    day_low, quote_time} o None."""
    if not disponibile(ticker) or not _posto_libero(ora()):
        return None
    try:
        r = requests.get(_URL, params={"symbol": ticker, "token": settings.finnhub_api_key},
                         timeout=_TIMEOUT)
        if r.status_code != 200:
            logger.debug(f"[finnhub] quote {ticker}: HTTP {r.status_code}")
            return None
        d = r.json()
    except (requests.RequestException, ValueError) as e:
        logger.debug(f"[finnhub] quote {ticker} fallita: {e}")
        return None
    prezzo = d.get("c") if isinstance(d, dict) else None
    if not isinstance(prezzo, (int, float)) or prezzo <= 0:
        return None
    prec = d.get("pc") if isinstance(d.get("pc"), (int, float)) and d.get("pc") > 0 else None
    return {
        "price": float(prezzo),
        "prev_close": float(prec) if prec else None,
        "change_abs": float(prezzo - prec) if prec else None,
        "change_pct": float((prezzo - prec) / prec * 100.0) if prec else None,
        "day_open": float(d["o"]) if isinstance(d.get("o"), (int, float)) and d["o"] > 0 else None,
        "day_high": float(d["h"]) if isinstance(d.get("h"), (int, float)) and d["h"] > 0 else None,
        "day_low": float(d["l"]) if isinstance(d.get("l"), (int, float)) and d["l"] > 0 else None,
        "quote_time": d.get("t") if isinstance(d.get("t"), int) else None,
    }


def azzera_limite() -> None:
    """Per i test."""
    with _lock:
        _chiamate.clear()
