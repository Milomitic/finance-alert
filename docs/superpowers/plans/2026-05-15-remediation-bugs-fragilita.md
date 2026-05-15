# Remediation bug & fragilità Finance-Alert — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminare i sei bug/fragilità identificati nell'analisi del 2026-05-15 senza introdurre regressioni, in tre fasi prioritizzate (quick wins → affidabilità → robustezza scan engine).

**Architecture:** Lavoreremo per la maggior parte sull'infrastruttura già presente (`yfinance_health` circuit breaker, `data_source_metrics` counters, `dedupe_stocks` script con CLI riusabile, APScheduler in `app/scheduler/__init__.py`). Aggiungiamo: (a) un job di cleanup ricorrente, (b) un modulo `_retry.py` con backoff esponenziale, (c) un modulo `core/errors.py` con eccezioni tipate per sostituire i `except Exception: # noqa: BLE001` nei 5 hotspot più rumorosi, (d) un secondo provider per le news (Marketaux), (e) un fallback EOD per le quote quando il breaker è aperto.

**Tech Stack:** Python 3.11 · FastAPI · SQLAlchemy · APScheduler · pytest · loguru. Niente nuove dipendenze pesanti (Marketaux è solo `requests`, backoff è scritto a mano in ~30 righe).

**Constraint:** Tutti i test esistenti (281+) devono restare verdi. Ogni task termina con `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -x -q` pulito.

**File structure decisions:**

| File | Stato | Responsabilità |
|---|---|---|
| `backend/app/core/errors.py` | NEW | Gerarchia eccezioni tipate: `UpstreamError`, `RateLimitError`, `UpstreamTimeout`, `UpstreamUnavailable`. |
| `backend/app/services/_retry.py` | NEW | Decorator `with_backoff(retries, base_delay, max_delay, on)` per chiamate I/O verso upstream. |
| `backend/app/scheduler/jobs/dedupe_stocks_job.py` | NEW | Wrapper job APScheduler attorno a `app.scripts.dedupe_stocks.dedupe`. |
| `backend/app/scheduler/jobs/cleanup_orphan_scans_job.py` | NEW | Sweep periodico delle ScanRun "running" senza heartbeat da > 5 min. |
| `backend/app/scheduler/__init__.py` | MODIFY | Registra i due job nuovi (settimanale dedupe + 1m cleanup). |
| `backend/app/services/stock_news_service.py` | MODIFY | Fallback Marketaux quando yfinance torna 0 headline o errore. |
| `backend/app/services/live_quote_service.py` | MODIFY | Quando breaker open, popolare `LiveQuote` da ultima `OhlcvDaily` invece di restituire `error="breaker"`. |
| `backend/app/api/{stocks,alerts,scores,market_detail,main}.py` | MODIFY | Sostituire `except Exception: # noqa: BLE001` con le nuove classi tipate (top-5 hotspot). |
| `backend/app/main.py` | MODIFY | `_hydrate_fetch_caches` con timing strutturato + per-ticker error counter. |
| `backend/tests/` | NEW (vari) | Test isolati per ogni modulo nuovo + regressioni sui refactor. |

**Non-goals (volutamente esclusi):**

- "Vite/uvicorn drop reload su Windows" — è una fragilità DX già documentata in CLAUDE.md, non un bug del codice applicativo.
- Riscrivere tutti i 28 `except Exception:`. Ne fixiamo 5 (i router consumer-facing); gli altri stanno in scheduler/scripts e sono accettabili.
- Riscrivere `live_quote_service` con WebSocket: fuori scope, già motivato nel docstring del file.

---

## Phase 1 — Quick wins (target: 1-2 giorni)

### Task 1: Job ricorrente `dedupe_stocks`

**Why:** Lo script `dedupe_stocks.py` esiste e ha già una funzione `dedupe(*, dry_run: bool) -> int` con CLI. Però viene eseguito a mano. Ogni volta che `catalog_refresh_service` reintroduce un duplicato (es. ticker presente in più indici Wikipedia con `default_exchange` diverso), il bug latente in `api/stocks.py:169` e `api/price_alerts.py:20` può esplodere con `MultipleResultsFound`. Eseguirlo settimanalmente subito DOPO `refresh_catalog` (Sab 03:30) chiude il loop in modo deterministico.

**Files:**
- Create: `backend/app/scheduler/jobs/dedupe_stocks_job.py`
- Create: `backend/tests/test_dedupe_stocks_job.py`
- Modify: `backend/app/scheduler/__init__.py`

- [ ] **Step 1.1: Scrivi il test del wrapper job**

Crea `backend/tests/test_dedupe_stocks_job.py`:

```python
"""Verifica che il wrapper APScheduler chiami dedupe() in modalità non-dry-run e
loggi il risultato. Non verifica la logica di dedup vera (già coperta da
test_dedupe_stocks.py); verifica solo l'orchestrazione."""
from unittest.mock import patch

from app.scheduler.jobs.dedupe_stocks_job import run_dedupe_stocks


def test_run_dedupe_stocks_invokes_dedupe_in_commit_mode():
    with patch("app.scheduler.jobs.dedupe_stocks_job.dedupe", return_value=3) as m:
        run_dedupe_stocks()
        m.assert_called_once_with(dry_run=False)


def test_run_dedupe_stocks_swallows_exceptions_and_logs():
    """Un fallimento del job non deve crashare lo scheduler."""
    with patch(
        "app.scheduler.jobs.dedupe_stocks_job.dedupe",
        side_effect=RuntimeError("boom"),
    ):
        # Non deve sollevare
        run_dedupe_stocks()
```

- [ ] **Step 1.2: Esegui il test (deve fallire)**

```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_dedupe_stocks_job.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.scheduler.jobs.dedupe_stocks_job'`.

- [ ] **Step 1.3: Implementa il job**

Crea `backend/app/scheduler/jobs/dedupe_stocks_job.py`:

```python
"""APScheduler job: collassa eventuali duplicati introdotti dal catalog refresh.

Eseguito ogni sabato alle 03:30 (30 minuti dopo refresh_catalog) così se il
refresh ha reintrodotto un duplicato, viene neutralizzato prima che un utente
ci sbatta contro lunedì.

Lo script di base è idempotente: una run su DB pulito è un no-op.
"""
from loguru import logger

from app.scripts.dedupe_stocks import dedupe


def run_dedupe_stocks() -> None:
    try:
        n = dedupe(dry_run=False)
        if n:
            logger.warning(f"[dedupe_stocks_job] collassati {n} duplicati")
        else:
            logger.info("[dedupe_stocks_job] nessun duplicato trovato")
    except Exception as exc:  # noqa: BLE001 — job entrypoint, log+continue
        logger.error(f"[dedupe_stocks_job] fallito: {exc}")
```

- [ ] **Step 1.4: Esegui il test (deve passare)**

```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_dedupe_stocks_job.py -v
```

Expected: 2 passed.

- [ ] **Step 1.5: Registra il job nello scheduler**

Modifica `backend/app/scheduler/__init__.py`. Dopo l'import di `run_refresh_all` aggiungi:

```python
from app.scheduler.jobs.dedupe_stocks_job import run_dedupe_stocks
```

E dopo il `_scheduler.add_job(run_refresh_all, ...)` (riga ~22) aggiungi:

```python
        _scheduler.add_job(
            run_dedupe_stocks,
            trigger=CronTrigger(day_of_week="sat", hour=3, minute=30),
            id="dedupe_stocks",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
```

- [ ] **Step 1.6: Esegui l'intera suite per regressione**

```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -x -q
```

Expected: tutti i test verdi (282+).

- [ ] **Step 1.7: Commit**

```bash
git add backend/app/scheduler/jobs/dedupe_stocks_job.py \
        backend/tests/test_dedupe_stocks_job.py \
        backend/app/scheduler/__init__.py
git commit -m "scheduler: weekly dedupe_stocks job (Sat 03:30, post catalog refresh)"
```

---

### Task 2: Eccezioni tipate per i 5 hotspot router

**Why:** I `except Exception: # noqa: BLE001` nei router consumer-facing (stocks, alerts, scores, market_detail, main `/admin/warmup-fundamentals`) mascherano la causa specifica. Vogliamo separare almeno tre categorie: `UpstreamError` (yfinance/Finnhub/FRED rotti), `DataValidationError` (payload sporco), e tutto il resto che resta `Exception` ma con log strutturato.

**Files:**
- Create: `backend/app/core/errors.py`
- Create: `backend/tests/test_core_errors.py`
- Modify: `backend/app/api/stocks.py:350`
- Modify: `backend/app/api/alerts.py:275`
- Modify: `backend/app/api/scores.py:136`
- Modify: `backend/app/api/market_detail.py:152`
- Modify: `backend/app/main.py:220` (dentro `/admin/warmup-fundamentals`)

- [ ] **Step 2.1: Scrivi il test della gerarchia errori**

Crea `backend/tests/test_core_errors.py`:

```python
"""Le eccezioni tipate devono comportarsi come Exception ma essere distinguibili
via except specifico — così possiamo refactor-are i broad-except nei router."""
from app.core.errors import (
    RateLimitError, UpstreamError, UpstreamTimeout, UpstreamUnavailable,
)


def test_hierarchy_root_is_exception():
    assert issubclass(UpstreamError, Exception)


def test_upstream_subclasses_inherit_from_upstream_error():
    assert issubclass(RateLimitError, UpstreamError)
    assert issubclass(UpstreamTimeout, UpstreamError)
    assert issubclass(UpstreamUnavailable, UpstreamError)


def test_upstream_error_carries_source_and_op_metadata():
    e = RateLimitError("rate limit hit", source="yfinance", op="fundamentals")
    assert e.source == "yfinance"
    assert e.op == "fundamentals"
    assert "rate limit" in str(e)
```

- [ ] **Step 2.2: Esegui il test (deve fallire)**

```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_core_errors.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.core.errors'`.

- [ ] **Step 2.3: Implementa il modulo errori**

Crea `backend/app/core/errors.py`:

```python
"""Eccezioni tipate per il fetching da sorgenti esterne.

Sostituiscono i `except Exception: # noqa: BLE001` nei router consumer-facing.
La gerarchia è volutamente piatta — non costruiamo una ontologia, solo i 4
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
    except DataValidationError as e:
        logger.warning(f"data malformed: {e}")
        # 422 / sentinel
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
```

- [ ] **Step 2.4: Esegui il test (deve passare)**

```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_core_errors.py -v
```

Expected: 3 passed.

- [ ] **Step 2.5: Refactor del primo hotspot — `api/stocks.py:350`**

Apri `backend/app/api/stocks.py` riga 350. Il pattern attuale è dentro `get_stock_detail` (route `/{ticker}/detail`). Identifica il blocco `try:` corrispondente — cattura una chiamata a un service che fa fetch upstream.

Sostituisci `except Exception:  # noqa: BLE001` con:

```python
        except UpstreamError as e:
            logger.warning(
                f"[stock_detail] upstream {e.source}.{e.op} failed for {ticker}: {e}"
            )
            # cadi al fallback già presente nel blocco originale
            # (mantieni la stessa logica, solo cambia il catch)
        except Exception as e:  # noqa: BLE001 — defensive last-resort
            logger.exception(f"[stock_detail] unexpected error for {ticker}: {e}")
```

Aggiungi in cima al file (insieme agli altri import):

```python
from app.core.errors import UpstreamError
```

- [ ] **Step 2.6: Scrivi un test di regressione per /detail**

Crea `backend/tests/test_api_stocks_detail_error_handling.py`:

```python
"""Quando un servizio downstream solleva UpstreamError, il router non deve 500
ma servire un detail con i campi opzionali a None (fallback graceful)."""
from unittest.mock import patch

import pytest


@pytest.fixture
def auth_client(test_client_auth):
    return test_client_auth  # riusa la fixture autenticata standard


def test_stock_detail_handles_upstream_error_gracefully(auth_client, sample_stock):
    """Se stock_fundamentals_service esplode con UpstreamError, /detail risponde 200
    con `fundamentals=None` invece di 500."""
    from app.core.errors import UpstreamUnavailable

    with patch(
        "app.api.stocks.stock_fundamentals_service.get_fundamentals",
        side_effect=UpstreamUnavailable(
            "yahoo 503", source="yfinance", op="fundamentals"
        ),
    ):
        r = auth_client.get(f"/api/stocks/{sample_stock.ticker}/detail")
    assert r.status_code == 200
    assert r.json().get("fundamentals") is None
```

**Nota:** I nomi delle fixture (`test_client_auth`, `sample_stock`) vanno verificati in `backend/tests/conftest.py`. Se non esistono con questi nomi, usa quelli realmente presenti (vedi i test esistenti in `test_api_stock_detail.py` per il pattern).

- [ ] **Step 2.7: Esegui il nuovo test (deve fallire o passare a seconda del path)**

```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_api_stocks_detail_error_handling.py -v
```

Expected: PASS (il refactor di 2.5 già cattura `UpstreamError`).

- [ ] **Step 2.8: Refactor degli altri 4 hotspot**

Ripeti il pattern dello Step 2.5 sui seguenti, mantenendo invariata la logica di fallback (solo il `except`):

- `backend/app/api/alerts.py:275`
- `backend/app/api/scores.py:136`
- `backend/app/api/market_detail.py:152`
- `backend/app/main.py:220` (dentro `/admin/warmup-fundamentals`, riga `try: get_fundamentals(...) except Exception:`)

Aggiungi `from app.core.errors import UpstreamError` in ogni file modificato.

- [ ] **Step 2.9: Esegui la suite completa**

```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -x -q
```

Expected: tutti verdi.

- [ ] **Step 2.10: Commit**

```bash
git add backend/app/core/errors.py \
        backend/tests/test_core_errors.py \
        backend/tests/test_api_stocks_detail_error_handling.py \
        backend/app/api/stocks.py \
        backend/app/api/alerts.py \
        backend/app/api/scores.py \
        backend/app/api/market_detail.py \
        backend/app/main.py
git commit -m "errors: typed UpstreamError hierarchy + refactor 5 router hotspots"
```

---

## Phase 2 — Affidabilità (target: 1 settimana)

### Task 3: Modulo retry con exponential backoff

**Why:** Oggi le chiamate yfinance/Finnhub/FRED falliscono senza retry. yfinance ha 429 transitori che sparirebbero con un retry breve + jitter. Vogliamo un decorator riusabile, testabile, con `monkeypatch` del clock.

**Files:**
- Create: `backend/app/services/_retry.py`
- Create: `backend/tests/test_services_retry.py`
- Modify: `backend/app/services/stock_fundamentals_service.py` (applica `with_backoff` al fetch yfinance)

- [ ] **Step 3.1: Scrivi i test del retry**

Crea `backend/tests/test_services_retry.py`:

```python
"""with_backoff: retry esponenziale con jitter, abort dopo N tentativi, rispetta
solo le eccezioni listate in `on=`."""
from unittest.mock import patch

import pytest

from app.core.errors import RateLimitError, UpstreamTimeout
from app.services._retry import with_backoff


def test_success_on_first_try_no_retry():
    calls = {"n": 0}

    @with_backoff(retries=3, base_delay=0.01, max_delay=0.1, on=(UpstreamTimeout,))
    def f():
        calls["n"] += 1
        return "ok"

    assert f() == "ok"
    assert calls["n"] == 1


def test_retries_on_listed_exception_and_succeeds():
    calls = {"n": 0}

    @with_backoff(retries=3, base_delay=0.001, max_delay=0.01, on=(UpstreamTimeout,))
    def f():
        calls["n"] += 1
        if calls["n"] < 3:
            raise UpstreamTimeout("transient")
        return "ok"

    assert f() == "ok"
    assert calls["n"] == 3


def test_gives_up_after_retries_and_reraises():
    @with_backoff(retries=2, base_delay=0.001, max_delay=0.01, on=(UpstreamTimeout,))
    def f():
        raise UpstreamTimeout("always")

    with pytest.raises(UpstreamTimeout):
        f()


def test_does_not_retry_unlisted_exception():
    calls = {"n": 0}

    @with_backoff(retries=3, base_delay=0.001, max_delay=0.01, on=(UpstreamTimeout,))
    def f():
        calls["n"] += 1
        raise RateLimitError("not listed")

    with pytest.raises(RateLimitError):
        f()
    assert calls["n"] == 1  # nessun retry


def test_delay_is_exponential_capped_at_max(monkeypatch):
    sleeps: list[float] = []

    def fake_sleep(s: float) -> None:
        sleeps.append(s)

    monkeypatch.setattr("app.services._retry.time.sleep", fake_sleep)

    @with_backoff(retries=4, base_delay=0.1, max_delay=0.5, on=(UpstreamTimeout,), jitter=False)
    def f():
        raise UpstreamTimeout("fail")

    with pytest.raises(UpstreamTimeout):
        f()
    # Senza jitter: 0.1, 0.2, 0.4 (3 sleep tra 4 tentativi), capped a 0.5.
    assert sleeps == [0.1, 0.2, 0.4]
```

- [ ] **Step 3.2: Esegui i test (devono fallire)**

```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_services_retry.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3.3: Implementa il modulo**

Crea `backend/app/services/_retry.py`:

```python
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
    """Restituisce un decorator che ri-tenta `fn` fino a `retries+1` volte
    (1 chiamata iniziale + `retries` retry) per le sole eccezioni in `on`.

    Delay: `min(base_delay * 2**attempt, max_delay)`, opzionale jitter ±25%.
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
                    if attempt > retries:
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
```

- [ ] **Step 3.4: Esegui i test (devono passare)**

```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_services_retry.py -v
```

Expected: 5 passed.

- [ ] **Step 3.5: Applica il backoff al fetch fundamentals**

Apri `backend/app/services/stock_fundamentals_service.py`. Trova la funzione che fa il fetch yfinance vero (cerca `def _fetch_fresh` o equivalente — è il chiamante che colpisce `yfinance.Ticker(...).info` / `.income_stmt` ecc.).

Wrappa la chiamata yfinance grezza con:

```python
from app.core.errors import RateLimitError, UpstreamTimeout, UpstreamUnavailable
from app.services._retry import with_backoff

# Normalizza le eccezioni di rete/yfinance nelle nostre classi tipate,
# così il decorator sa cosa ri-tentare.
def _normalize_yf_error(exc: Exception) -> Exception:
    msg = str(exc).lower()
    if "429" in msg or "rate limit" in msg:
        return RateLimitError(str(exc), source="yfinance", op="fundamentals")
    if "timeout" in msg or "timed out" in msg:
        return UpstreamTimeout(str(exc), source="yfinance", op="fundamentals")
    return UpstreamUnavailable(str(exc), source="yfinance", op="fundamentals")


@with_backoff(
    retries=2,
    base_delay=0.5,
    max_delay=4.0,
    on=(UpstreamTimeout, RateLimitError),
)
def _yf_fetch_with_retry(ticker: str):
    """Wrapping point: la chiamata yfinance + normalizzazione errori."""
    try:
        # ... contenuto esistente della chiamata yfinance ...
        return _do_yf_call(ticker)
    except Exception as exc:  # noqa: BLE001
        raise _normalize_yf_error(exc) from exc
```

**Nota implementativa:** mantieni il fallback già presente. Il decorator solleva l'errore tipato dopo i retry, il chiamante può catturarlo (sarà `UpstreamError`) e continuare la sua logica di fallback.

- [ ] **Step 3.6: Scrivi un test che dimostri il retry sul fetch reale**

Aggiungi a `backend/tests/test_stock_fundamentals_service_retry.py` (nuovo file):

```python
"""Il fetch fundamentals deve ri-tentare su timeout simulato, fino a 2 retry."""
from unittest.mock import patch

import pytest

from app.core.errors import UpstreamTimeout
from app.services.stock_fundamentals_service import _yf_fetch_with_retry


def test_yf_fetch_retries_on_timeout_then_succeeds():
    calls = {"n": 0}

    def fake_do(_t: str):
        calls["n"] += 1
        if calls["n"] < 2:
            raise TimeoutError("simulated network timeout")
        return {"ok": True}

    with patch(
        "app.services.stock_fundamentals_service._do_yf_call", side_effect=fake_do
    ):
        result = _yf_fetch_with_retry("AAPL")
    assert result == {"ok": True}
    assert calls["n"] == 2


def test_yf_fetch_gives_up_after_retries():
    def fake_do(_t: str):
        raise TimeoutError("persistent")

    with patch(
        "app.services.stock_fundamentals_service._do_yf_call", side_effect=fake_do
    ):
        with pytest.raises(UpstreamTimeout):
            _yf_fetch_with_retry("AAPL")
```

**Nota:** Se nel codice esistente la chiamata yfinance non era estratta in `_do_yf_call`, fallo come parte dello Step 3.5 (refactor "extract method") prima di applicare il decorator.

- [ ] **Step 3.7: Esegui i nuovi test + l'intera suite**

```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_stock_fundamentals_service_retry.py -v
cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -x -q
```

Expected: tutti verdi.

- [ ] **Step 3.8: Commit**

```bash
git add backend/app/services/_retry.py \
        backend/tests/test_services_retry.py \
        backend/app/services/stock_fundamentals_service.py \
        backend/tests/test_stock_fundamentals_service_retry.py
git commit -m "retry: exponential backoff helper + apply to fundamentals fetch"
```

---

### Task 4: Fallback news (Marketaux) quando yfinance vuoto

**Why:** Oggi `stock_news_service` non ha fallback. Se yfinance restituisce 0 headline o errore, la card News in UI mostra vuoto/errore. Marketaux ha un free tier (100 req/giorno) sufficiente per il single-user local-first context.

**Files:**
- Create: `backend/app/services/marketaux_news_service.py`
- Create: `backend/tests/test_marketaux_news_service.py`
- Modify: `backend/app/services/stock_news_service.py` (chiamata al fallback)
- Modify: `backend/app/core/config.py` (opzionale: aggiungi `marketaux_api_key`)

- [ ] **Step 4.1: Aggiungi la chiave config**

Apri `backend/app/core/config.py` e aggiungi il campo `marketaux_api_key: str = ""` nella classe Settings (rispetta lo stile esistente — probabilmente Pydantic `BaseSettings`).

- [ ] **Step 4.2: Scrivi i test di Marketaux**

Crea `backend/tests/test_marketaux_news_service.py`:

```python
"""Wrapper Marketaux: parsing del JSON, gestione errori, no-key short-circuit."""
from unittest.mock import patch

import pytest

from app.core.errors import UpstreamUnavailable
from app.services.marketaux_news_service import fetch_news


def test_returns_empty_when_no_api_key(monkeypatch):
    monkeypatch.setattr(
        "app.services.marketaux_news_service.settings.marketaux_api_key", ""
    )
    assert fetch_news("AAPL") == []


def test_parses_marketaux_response(monkeypatch):
    monkeypatch.setattr(
        "app.services.marketaux_news_service.settings.marketaux_api_key", "fake-key"
    )
    payload = {
        "data": [
            {
                "uuid": "abc",
                "title": "Apple beats Q4 estimates",
                "url": "https://news.example/apple-q4",
                "published_at": "2026-05-15T12:00:00Z",
                "source": "Reuters",
            }
        ]
    }
    with patch(
        "app.services.marketaux_news_service.requests.get"
    ) as mget:
        mget.return_value.status_code = 200
        mget.return_value.json.return_value = payload
        items = fetch_news("AAPL")
    assert len(items) == 1
    assert items[0].title.startswith("Apple beats")
    assert items[0].url == "https://news.example/apple-q4"


def test_raises_on_http_error(monkeypatch):
    monkeypatch.setattr(
        "app.services.marketaux_news_service.settings.marketaux_api_key", "fake-key"
    )
    with patch(
        "app.services.marketaux_news_service.requests.get"
    ) as mget:
        mget.return_value.status_code = 503
        mget.return_value.text = "down"
        with pytest.raises(UpstreamUnavailable):
            fetch_news("AAPL")
```

- [ ] **Step 4.3: Esegui i test (devono fallire)**

```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_marketaux_news_service.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 4.4: Implementa il client Marketaux**

Crea `backend/app/services/marketaux_news_service.py`:

```python
"""Marketaux news API — secondario per il fallback in stock_news_service.

Free tier: 100 req/giorno, payload ridotto. Sufficient per single-user
local-first context (max ~50 ticker visualizzati al giorno).

Schema risposta: https://www.marketaux.com/docs/api
Solo i campi che ci servono vengono mappati su NewsItem (riusiamo il
modello di stock_news_service per coerenza).
"""
from dataclasses import dataclass

import requests
from loguru import logger

from app.core.config import settings
from app.core.errors import UpstreamUnavailable


@dataclass
class NewsItem:
    title: str
    url: str
    published_at: str
    source: str


_BASE = "https://api.marketaux.com/v1/news/all"
_TIMEOUT = 8.0


def fetch_news(ticker: str, limit: int = 10) -> list[NewsItem]:
    """Ritorna headline per `ticker`. Lista vuota se la chiave non è configurata
    (graceful degrade — il caller decide se sollevare o ignorare)."""
    if not settings.marketaux_api_key:
        return []
    try:
        resp = requests.get(
            _BASE,
            params={
                "api_token": settings.marketaux_api_key,
                "symbols": ticker,
                "limit": limit,
                "language": "en",
            },
            timeout=_TIMEOUT,
        )
    except requests.RequestException as e:
        raise UpstreamUnavailable(str(e), source="marketaux", op="news") from e

    if resp.status_code != 200:
        logger.warning(
            f"[marketaux] HTTP {resp.status_code} for {ticker}: {resp.text[:200]}"
        )
        raise UpstreamUnavailable(
            f"marketaux HTTP {resp.status_code}", source="marketaux", op="news"
        )
    data = resp.json().get("data", [])
    return [
        NewsItem(
            title=item.get("title", ""),
            url=item.get("url", ""),
            published_at=item.get("published_at", ""),
            source=item.get("source", ""),
        )
        for item in data
    ]
```

- [ ] **Step 4.5: Esegui i test (devono passare)**

```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_marketaux_news_service.py -v
```

Expected: 3 passed.

- [ ] **Step 4.6: Integra il fallback in `stock_news_service`**

Apri `backend/app/services/stock_news_service.py`. Trova la funzione che esegue il fetch upstream yfinance (cerca `def _fetch_fresh` o equivalente). Dove oggi torna `[]` o un errore in caso di yfinance vuoto, aggiungi:

```python
from app.services import marketaux_news_service

# ... dopo aver tentato yfinance e ottenuto risultato vuoto/errore:
if not items:
    try:
        fallback = marketaux_news_service.fetch_news(ticker, limit=10)
        if fallback:
            logger.info(
                f"[news] yfinance vuoto per {ticker}, uso Marketaux fallback "
                f"({len(fallback)} items)"
            )
            items = [
                # mappa Marketaux NewsItem → schema interno (controlla il modello esistente)
                ...
            ]
    except Exception as exc:  # noqa: BLE001 — fallback può fallire, è OK
        logger.warning(f"[news] marketaux fallback failed for {ticker}: {exc}")
```

**Nota:** il mapping `marketaux NewsItem → schema interno` dipende dal modello già usato da `stock_news_service`. Apri il file e adatta i campi (di solito `title`, `url`, `published_at`, `source` esistono).

- [ ] **Step 4.7: Scrivi un test di integrazione del fallback**

Aggiungi a `backend/tests/test_stock_news_service.py` (esiste già):

```python
def test_falls_back_to_marketaux_when_yfinance_empty(monkeypatch):
    """Se yfinance ritorna 0 headline, il service prova Marketaux."""
    from app.services import marketaux_news_service, stock_news_service

    def fake_yf_fetch(_ticker: str):
        return []  # yfinance vuoto

    def fake_marketaux(ticker: str, limit: int = 10):
        return [
            marketaux_news_service.NewsItem(
                title="From marketaux",
                url="https://x",
                published_at="2026-05-15T00:00:00Z",
                source="Reuters",
            )
        ]

    monkeypatch.setattr(stock_news_service, "_fetch_yf_news", fake_yf_fetch)
    monkeypatch.setattr(marketaux_news_service, "fetch_news", fake_marketaux)
    # Bypass L1/L2 — il test pesa solo il branch di fallback
    stock_news_service._CACHE.clear()

    result = stock_news_service.get_news("AAPL")
    assert any("marketaux" in i.title.lower() for i in result.items)
```

**Nota:** Verifica i nomi reali (`_fetch_yf_news`, `_CACHE`, `result.items`) leggendo il file. Se differenti, adatta — il punto è validare il branch del fallback, non rispecchiare il mio nome esatto.

- [ ] **Step 4.8: Esegui tutto**

```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_stock_news_service.py tests/test_marketaux_news_service.py -v
cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -x -q
```

Expected: tutti verdi.

- [ ] **Step 4.9: Commit**

```bash
git add backend/app/services/marketaux_news_service.py \
        backend/tests/test_marketaux_news_service.py \
        backend/app/services/stock_news_service.py \
        backend/tests/test_stock_news_service.py \
        backend/app/core/config.py
git commit -m "news: Marketaux fallback when yfinance returns empty"
```

---

### Task 4b: Fallback EOD per live_quote quando il breaker è aperto

**Why:** `live_quote_service` oggi è SOLO L1 e SOLO yfinance. Quando il circuit breaker yfinance si apre (5+ fallimenti in 60s, cooldown 5min), tutti gli endpoint `/api/stocks/quotes/batch` restituiscono `LiveQuote(error="breaker_open")`. La UI mostra "—" per tutti i ticker. Soluzione minima: quando breaker open, popolare i campi `price`, `prev_close`, `change_*` dall'ultima riga di `OhlcvDaily` (l'EOD è meglio di niente), settando `market_state="CLOSED"` esplicito così la UI non finge che sia LIVE.

**Files:**
- Modify: `backend/app/services/live_quote_service.py` (funzione di fetch singolo + batch)
- Modify: `backend/tests/test_live_quote_service.py`

- [ ] **Step 4b.1: Scrivi il test del fallback EOD**

Aggiungi a `backend/tests/test_live_quote_service.py`:

```python
def test_breaker_open_uses_eod_fallback(db, monkeypatch):
    """Quando yfinance_health.is_open() == True, get_quotes_batch deve
    popolare i campi base dall'ultima OhlcvDaily invece di tornare error."""
    from datetime import date
    from app.models import OhlcvDaily, Stock
    from app.services import live_quote_service, yfinance_health

    # Setup: uno stock + una barra OHLCV recente
    s = Stock(ticker="TEST", name="Test Co", exchange="NYSE")
    db.add(s)
    db.commit()
    bar = OhlcvDaily(
        stock_id=s.id,
        date=date(2026, 5, 14),
        open=100.0,
        high=105.0,
        low=99.0,
        close=104.5,
        volume=1_000_000,
    )
    db.add(bar)
    db.commit()

    # Pre-bar per calcolare prev_close
    bar2 = OhlcvDaily(
        stock_id=s.id,
        date=date(2026, 5, 13),
        open=98.0, high=101.0, low=97.0, close=100.0, volume=900_000,
    )
    db.add(bar2)
    db.commit()

    # Forza il breaker aperto
    monkeypatch.setattr(yfinance_health, "is_open", lambda: True)
    # Svuota il cache L1 così non hit
    live_quote_service._CACHE.clear()

    quotes = live_quote_service.get_quotes_batch(["TEST"])

    assert "TEST" in quotes
    q = quotes["TEST"]
    assert q.error is None  # fallback OK, non più "breaker_open"
    assert q.price == 104.5
    assert q.prev_close == 100.0
    assert q.market_state == "CLOSED"
    assert q.change_abs == pytest.approx(4.5)
    assert q.change_pct == pytest.approx(4.5)  # (104.5 - 100) / 100 * 100
```

**Nota:** Verifica i nomi reali delle fixture (`db`, `pytest`) e dei campi nel file esistente. Adatta se differente — il punto è il branch del fallback.

- [ ] **Step 4b.2: Esegui il test (deve fallire)**

```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_live_quote_service.py -v -k eod_fallback
```

Expected: FAIL (oggi torna `error="breaker_open"`).

- [ ] **Step 4b.3: Implementa il fallback**

Apri `backend/app/services/live_quote_service.py`. Trova la funzione che decide cosa fare quando `yfinance_health.is_open()` è True (cerca `is_open` nel file — riga ~385 menziona il branch in un commento, identifica il caller).

Aggiungi un helper privato:

```python
def _eod_fallback_quote(ticker: str) -> LiveQuote:
    """Popola un LiveQuote dall'ultima OhlcvDaily disponibile. Usato quando
    il breaker yfinance è aperto: meglio EOD-stale-but-correct che '—'."""
    import time

    from sqlalchemy import select, desc

    from app.core.db import SessionLocal
    from app.models import OhlcvDaily, Stock

    with SessionLocal() as db:
        # `.limit(1).scalars().first()` per tollerare duplicati (vedi CLAUDE.md)
        stock = db.execute(
            select(Stock).where(Stock.ticker == ticker).limit(1)
        ).scalars().first()
        if stock is None:
            return LiveQuote(ticker=ticker, error="not_found")
        bars = db.execute(
            select(OhlcvDaily)
            .where(OhlcvDaily.stock_id == stock.id)
            .order_by(desc(OhlcvDaily.date))
            .limit(2)
        ).scalars().all()
        if not bars:
            return LiveQuote(ticker=ticker, error="no_ohlcv")
        last = bars[0]
        prev = bars[1] if len(bars) > 1 else None
        price = float(last.close) if last.close is not None else None
        prev_close = float(prev.close) if (prev and prev.close is not None) else None
        change_abs = (price - prev_close) if (price is not None and prev_close) else None
        change_pct = (
            (change_abs / prev_close * 100.0)
            if (change_abs is not None and prev_close)
            else None
        )
        return LiveQuote(
            ticker=ticker,
            price=price,
            prev_close=prev_close,
            change_abs=change_abs,
            change_pct=change_pct,
            day_open=float(last.open) if last.open is not None else None,
            day_high=float(last.high) if last.high is not None else None,
            day_low=float(last.low) if last.low is not None else None,
            volume=int(last.volume) if last.volume is not None else None,
            market_state="CLOSED",
            fetched_at=time.time(),
            error=None,
        )
```

Poi nella funzione di fetch (singolo o nel batch), sostituisci il branch:

```python
if yfinance_health.is_open():
    return LiveQuote(ticker=ticker, error="breaker_open")
```

con:

```python
if yfinance_health.is_open():
    logger.debug(f"[live_quote] breaker open, EOD fallback for {ticker}")
    return _eod_fallback_quote(ticker)
```

- [ ] **Step 4b.4: Esegui il test (deve passare)**

```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_live_quote_service.py -v
```

Expected: tutti i test del file (vecchi + nuovo) verdi.

- [ ] **Step 4b.5: Suite completa**

```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -x -q
```

Expected: tutti verdi.

- [ ] **Step 4b.6: Smoke check frontend**

Non c'è un test automatico — manuale:
1. Avvia backend + frontend
2. Apri DevTools, simula breaker aperto (chiama POST `/api/admin/...` se esiste un toggle, altrimenti `from app.services import yfinance_health; yfinance_health._state.opened_at = time.time()` da una shell)
3. Verifica che `/api/stocks/quotes/batch?tickers=AAPL` ritorni price = ultimo close, market_state = "CLOSED", non più error.

- [ ] **Step 4b.7: Commit**

```bash
git add backend/app/services/live_quote_service.py \
        backend/tests/test_live_quote_service.py
git commit -m "live_quote: EOD fallback from OhlcvDaily when yfinance breaker open"
```

---

### Task 5: Cleanup ScanRun orfani periodico

**Why:** `_cleanup_orphan_scans()` gira solo al startup. Se uvicorn resta su ma il worker scan crasha mid-flight, la ScanRun "running" resta tale finché il backend non viene riavviato a mano. Un job ogni minuto che chiude ScanRun senza heartbeat da > 5 min risolve.

**Files:**
- Create: `backend/app/scheduler/jobs/cleanup_orphan_scans_job.py`
- Create: `backend/tests/test_cleanup_orphan_scans_job.py`
- Modify: `backend/app/scheduler/__init__.py` (registra il job ogni minuto)

- [ ] **Step 5.1: Scrivi il test**

Crea `backend/tests/test_cleanup_orphan_scans_job.py`:

```python
"""Il job periodico chiude le ScanRun running con last_progress_at > 5 min fa.
Le ScanRun running con heartbeat recente NON devono essere toccate."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import ScanRun
from app.scheduler.jobs.cleanup_orphan_scans_job import run_cleanup_orphan_scans


def test_closes_stale_running_scan(db):
    old = ScanRun(
        trigger="manual",
        status="running",
        phase="evaluating",
        progress_done=42,
        progress_total=200,
        last_progress_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    db.add(old)
    db.commit()
    old_id = old.id

    run_cleanup_orphan_scans()

    db.expire_all()
    row = db.execute(select(ScanRun).where(ScanRun.id == old_id)).scalar_one()
    assert row.status == "failed"
    assert "heartbeat" in (row.error_message or "").lower()


def test_does_not_touch_fresh_running_scan(db):
    fresh = ScanRun(
        trigger="manual",
        status="running",
        phase="evaluating",
        progress_done=10,
        progress_total=200,
        last_progress_at=datetime.now(UTC) - timedelta(seconds=30),
    )
    db.add(fresh)
    db.commit()
    fresh_id = fresh.id

    run_cleanup_orphan_scans()

    db.expire_all()
    row = db.execute(select(ScanRun).where(ScanRun.id == fresh_id)).scalar_one()
    assert row.status == "running"


def test_does_not_touch_completed_scan(db):
    done = ScanRun(
        trigger="manual",
        status="ok",
        progress_done=200,
        progress_total=200,
        last_progress_at=datetime.now(UTC) - timedelta(hours=1),
        completed_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db.add(done)
    db.commit()
    done_id = done.id

    run_cleanup_orphan_scans()

    db.expire_all()
    row = db.execute(select(ScanRun).where(ScanRun.id == done_id)).scalar_one()
    assert row.status == "ok"  # invariato
```

- [ ] **Step 5.2: Esegui i test (devono fallire)**

```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_cleanup_orphan_scans_job.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 5.3: Implementa il job**

Crea `backend/app/scheduler/jobs/cleanup_orphan_scans_job.py`:

```python
"""Job APScheduler: chiude le ScanRun 'running' senza heartbeat da troppo tempo.

Estrae la logica già usata in main.py:_cleanup_orphan_scans (che gira solo
al boot) in una funzione invocabile anche periodicamente. Threshold: 5 min
senza heartbeat ⇒ il worker è morto/bloccato, marca 'failed'.

Idempotente: zero orfani ⇒ no-op silenzioso.
"""
from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import ScanRun

# Heartbeat threshold. 5 min copre con margine il caso peggiore di un
# fetch yfinance lento + scan grosso (scan_universe pulsa il progress
# ogni 0.5s via progress_pulse).
_STALE_AFTER_MINUTES = 5


def run_cleanup_orphan_scans() -> int:
    """Chiude le ScanRun running con heartbeat stale. Restituisce il count
    di righe chiuse (utile per test e log)."""
    cutoff = datetime.now(UTC) - timedelta(minutes=_STALE_AFTER_MINUTES)
    closed = 0
    with SessionLocal() as db:
        stale = db.execute(
            select(ScanRun).where(
                ScanRun.status == "running",
                ScanRun.last_progress_at < cutoff,
            )
        ).scalars().all()
        if not stale:
            return 0
        now = datetime.now(UTC)
        for r in stale:
            elapsed = int((now - (r.last_progress_at or now)).total_seconds() / 60)
            r.status = "failed"
            r.phase = None
            r.error_message = (
                f"Scan terminato dal cleanup periodico (heartbeat fermo da "
                f"~{elapsed}min)."
            )
            r.completed_at = now
            closed += 1
        db.commit()
        logger.warning(
            f"[orphan_cleanup] closed {closed} stale ScanRun(s) "
            f"(ids={[r.id for r in stale]})"
        )
    return closed
```

- [ ] **Step 5.4: Esegui i test (devono passare)**

```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_cleanup_orphan_scans_job.py -v
```

Expected: 3 passed.

**Nota:** se i test falliscono per "datetime con/senza timezone", verifica che la fixture `db` setti il modello come usa il resto del codebase. Il pattern in `main.py:_cleanup_orphan_scans` gestisce esplicitamente `tzinfo is None`: replica quel pattern nel job se necessario.

- [ ] **Step 5.5: Registra il job nello scheduler**

Modifica `backend/app/scheduler/__init__.py`. Aggiungi l'import:

```python
from app.scheduler.jobs.cleanup_orphan_scans_job import run_cleanup_orphan_scans
```

E dopo l'ultimo `add_job` (refresh_imminent_earnings, riga ~91):

```python
        # Cleanup orfani ScanRun — ogni minuto. Necessario perché
        # _cleanup_orphan_scans in main.py gira solo al boot; se uvicorn
        # resta su ma un worker scan crasha, la riga resta 'running'
        # all'infinito (la UI mostra una progress bar fantasma).
        _scheduler.add_job(
            run_cleanup_orphan_scans,
            trigger=CronTrigger(minute="*"),
            id="cleanup_orphan_scans",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
```

- [ ] **Step 5.6: Esegui la suite completa**

```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -x -q
```

Expected: tutti verdi.

- [ ] **Step 5.7: Commit**

```bash
git add backend/app/scheduler/jobs/cleanup_orphan_scans_job.py \
        backend/tests/test_cleanup_orphan_scans_job.py \
        backend/app/scheduler/__init__.py
git commit -m "scheduler: periodic orphan ScanRun cleanup (every minute, >5min stale)"
```

---

## Phase 3 — Robustezza misurata (target: 2-3 giorni)

### Task 6: L1 hydration con timing + partial-failure counter

**Why:** `_hydrate_fetch_caches` oggi è "non-fatal" e logga solo se qualcosa è stato caricato. Vogliamo: timing strutturato (quanto ci ha messo?), e contare quante righe L2 sono corrotte/skippate. Senza questi numeri, una L2 sempre più sporca non emerge mai.

**Files:**
- Modify: `backend/app/main.py:81` (`_hydrate_fetch_caches`)
- Modify: `backend/app/services/stock_fundamentals_service.py` (la funzione `hydrate_l1_from_db` deve tornare `(loaded, skipped)`)
- Modify: `backend/app/services/stock_news_service.py` (idem)
- Modify: `backend/tests/test_stock_fundamentals_service.py` e `test_stock_news_service.py` (aggiorna assertion)

- [ ] **Step 6.1: Scrivi il test che richiede il nuovo return type**

Aggiungi a `backend/tests/test_stock_fundamentals_service.py` (o crea `test_stock_fundamentals_hydrate.py`):

```python
def test_hydrate_l1_from_db_returns_loaded_and_skipped_counts(db):
    """hydrate_l1_from_db deve tornare una tupla (loaded:int, skipped:int)
    invece di un int singolo, così il caller può loggare entrambi."""
    from app.services import stock_fundamentals_service
    # Senza setup speciale, su DB vuoto dovrebbe tornare (0, 0).
    result = stock_fundamentals_service.hydrate_l1_from_db()
    assert isinstance(result, tuple)
    assert result == (0, 0)
```

- [ ] **Step 6.2: Esegui il test (deve fallire)**

```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_stock_fundamentals_service.py -v -k hydrate
```

Expected: FAIL — la funzione torna un int oggi.

- [ ] **Step 6.3: Aggiorna `hydrate_l1_from_db` in `stock_fundamentals_service.py`**

Apri il file. Trova `def hydrate_l1_from_db(...) -> int:`. Modifica:

```python
def hydrate_l1_from_db() -> tuple[int, int]:
    """Restituisce (loaded, skipped). skipped = righe L2 che non si sono
    deserializzate correttamente (corrotte, schema vecchio, ecc.)."""
    loaded = 0
    skipped = 0
    # ... loop esistente ...
    for row in rows:
        try:
            # deserializzazione esistente
            _CACHE[row.ticker] = _deserialize(row)
            loaded += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                f"[hydrate] skipped L2 row for {row.ticker}: {exc}"
            )
            skipped += 1
    return loaded, skipped
```

- [ ] **Step 6.4: Stessa modifica in `stock_news_service.py`**

Identico pattern al 6.3.

- [ ] **Step 6.5: Aggiorna `_hydrate_fetch_caches` in `main.py`**

Riga ~81 di `backend/app/main.py`. Sostituisci con:

```python
def _hydrate_fetch_caches() -> None:
    """Restore L1 caches da L2. Logga timing + count di righe corrotte
    skippate, così una L2 sempre più sporca emerge nelle metriche."""
    import time as _time

    from app.services import stock_fundamentals_service, stock_news_service

    t0 = _time.perf_counter()
    try:
        n_fund_ok, n_fund_skip = stock_fundamentals_service.hydrate_l1_from_db()
        n_news_ok, n_news_skip = stock_news_service.hydrate_l1_from_db()
    except Exception as exc:  # noqa: BLE001 — boot-time best effort
        logger.warning(f"[startup] L1 hydration failed (non-fatal): {exc}")
        return

    elapsed_ms = (_time.perf_counter() - t0) * 1000
    if n_fund_ok or n_news_ok or n_fund_skip or n_news_skip:
        logger.info(
            f"[startup] L1 hydrated in {elapsed_ms:.0f}ms: "
            f"fundamentals={n_fund_ok} (skipped {n_fund_skip}), "
            f"news={n_news_ok} (skipped {n_news_skip})"
        )
```

- [ ] **Step 6.6: Aggiorna test che assumevano il vecchio return type**

```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -x -q
```

Se qualche test fallisce, l'errore tipico è `TypeError: cannot unpack non-iterable int` o `assert 5 == (5, 0)`. Aggiorna le assertion al nuovo formato tupla.

- [ ] **Step 6.7: Verifica finale**

```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -x -q
```

Expected: tutti verdi.

- [ ] **Step 6.8: Commit**

```bash
git add backend/app/main.py \
        backend/app/services/stock_fundamentals_service.py \
        backend/app/services/stock_news_service.py \
        backend/tests/test_stock_fundamentals_service.py \
        backend/tests/test_stock_news_service.py
git commit -m "hydration: track loaded vs skipped L2 rows + log timing"
```

---

## Closing checklist

Dopo aver chiuso tutti i task:

- [ ] **Smoke manuale**: avvia il backend (`uvicorn app.main:app --reload`), controlla i log di startup: vedere "L1 hydrated in Xms" + scheduler jobs registrati (deve includere `dedupe_stocks` + `cleanup_orphan_scans`).
- [ ] **Suite completa**: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q` — tutti verdi.
- [ ] **Health endpoint**: `curl http://127.0.0.1:8000/api/health/data-sources` — verifica che le metriche includano nuove righe da Marketaux dopo qualche request.
- [ ] **CLAUDE.md update**: aggiungi nota sulla nuova classe `UpstreamError` e sul fatto che i nuovi service la rispettano (futuro reviewer non deve scoprirla a freddo).

## Non-regression boundary

Questi test esistenti DEVONO restare verdi dopo ogni task — sono i guardiani delle aree toccate:

- `tests/test_dedupe_stocks.py` · `tests/test_dedupe_prevention.py`
- `tests/test_scan_service.py` · `tests/test_smoke.py`
- `tests/test_stock_detail_service.py` · `tests/test_stock_news_service.py`
- `tests/test_api_alerts.py` · `tests/test_api_stocks.py`

Se uno di questi rosseggia dopo un tuo cambio, NON proseguire al task successivo — la regressione va capita prima.
