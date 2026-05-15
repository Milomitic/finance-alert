# Platform Health — pagina di osservabilità e log

**Status:** Approved (utente ha autorizzato a decidere sul resto)
**Owner:** —
**Created:** 2026-05-15

## Goal

Una pagina `/health` che mostra in tempo reale:
1. La salute dei servizi (sorgenti dati, scheduler, scan recenti, cache+DB)
2. Lo stream live dei log dell'app (tutti i livelli, filtrabili)

Per permettere all'operatore di:
- Rilevare un upstream che inizia a flakkare prima che lo noti l'utente finale
- Vedere errori transitori che oggi finiscono solo nel file `app.log` senza visibilità immediata
- Diagnosticare phantom scan, cache stale, breaker aperti

## Non-goals

- Download/export log (i file rotati in `./data/logs/` bastano per analisi forensi)
- Alerting (la pagina è **read-only** in v1; nessuna notifica/integrazione esterna)
- Time-series storiche dei metric (snapshot corrente è sufficiente per single-user)
- Multi-tab sync, real-time charting, regex avanzato sui log

## Architecture overview

```
┌─────────────────────────┐         ┌─────────────────────────────────┐
│ loguru                  │         │ APScheduler                     │
│ (existing 3 sinks:      │         │                                 │
│  stdout, file, +NEW)    │         │ Job listeners: EXECUTED, ERROR, │
└──────────┬──────────────┘         │                MISSED           │
           │ each record            └────────────┬────────────────────┘
           ▼                                     │
┌─────────────────────────┐              ┌──────▼──────────────────┐
│ log_buffer.append(rec)  │              │ scheduler_metrics       │
│  - deque(maxlen=2000)   │              │  - dict[job_id, JobStat]│
│  - pub/sub callbacks    │              └──────────┬──────────────┘
└──────────┬──────────────┘                         │
           │ subscribers                            │
           ▼                                        ▼
┌──────────────────────────────────────────────────────────────────┐
│ FastAPI router: /api/platform                                    │
│  - GET /health      → JSON snapshot (REST)                       │
│  - GET /logs        → filtered list of records (REST)            │
│  - GET /stream      → SSE: snapshot every 5s, log on append,     │
│                       keepalive every 30s                        │
└──────────┬───────────────────────────────────────────────────────┘
           │ EventSource
           ▼
┌──────────────────────────────────────────────────────────────────┐
│ Frontend: PlatformHealthPage.tsx                                 │
│  - Health row (4 cards: data sources, scheduler, scans, cache)   │
│  - Log stream (filterable table, max 500 visible)                │
└──────────────────────────────────────────────────────────────────┘
```

## Backend design

### New modules

**`backend/app/core/log_buffer.py`** — ring buffer thread-safe (~100 LOC)

```python
class LogBuffer:
    """In-process ring buffer with pub/sub. Loguru sink writes here;
    SSE handlers subscribe to receive new records as they arrive."""

    def __init__(self, maxlen: int = 2000) -> None: ...
    def append_record(self, record: dict) -> None: ...   # loguru sink target
    def get_snapshot(self, level=None, module=None, search=None, limit=500) -> list[dict]: ...
    def subscribe(self, callback: Callable[[dict], None]) -> Callable[[], None]: ...
    # callback signature: callback(record) -> None
    # returns: unsubscribe function

_INSTANCE = LogBuffer()  # module-level singleton
```

Stored record shape:
```python
{
    "ts": float,           # unix timestamp
    "level": "INFO",       # WARNING, ERROR, etc.
    "module": "scan_service",
    "function": "scan_universe",
    "line": 142,
    "message": "[scan] iteration 47/200",
    "exception": str | None,  # full traceback if present
}
```

**`backend/app/services/scheduler_metrics.py`** — APScheduler listener (~60 LOC)

```python
@dataclass
class JobStat:
    job_id: str
    last_run_at: float | None        # unix ts
    last_result: str | None          # "ok" | "error" | "missed"
    last_duration_ms: float | None
    last_error: str | None
    runs: int = 0
    errors: int = 0

class SchedulerMetrics:
    def __init__(self) -> None:
        self._stats: dict[str, JobStat] = {}
        self._lock = Lock()
    def on_event(self, event) -> None: ...    # called by APScheduler
    def snapshot(self) -> list[JobStat]: ...
```

Registered in `scheduler/__init__.py` with `EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED`.

**`backend/app/services/cache_metrics.py`** — read-only snapshot (~50 LOC)

```python
def snapshot() -> dict:
    """Return cache + DB health snapshot:
    {
        'fundamentals': {'l1_entries': int, 'l2_entries': int, 'oldest_age_s': float | None},
        'news':         {'l1_entries': int, 'l2_entries': int, 'oldest_age_s': float | None},
        'db':           {'size_mb': float, 'journal_mode': str}
    }
    """
```

**`backend/app/api/platform_health.py`** — router (~150 LOC)

```python
router = APIRouter(prefix="/api/platform", tags=["platform"])

@router.get("/health")
def health_snapshot(_user: User = Depends(get_current_user)) -> dict:
    """Combined snapshot: data_sources + scheduler + recent_scans + cache."""

@router.get("/logs")
def logs(
    level: str | None = None,    # WARNING+ filter
    module: str | None = None,   # substring filter
    search: str | None = None,   # substring on message
    limit: int = 500,
    _user: User = Depends(get_current_user),
) -> list[dict]: ...

@router.get("/stream")
async def stream(_user: User = Depends(get_current_user)) -> StreamingResponse:
    """SSE: yields events:
       - event: snapshot    (every 5s, full health snapshot)
       - event: log         (each new log record)
       - : keepalive        (every 30s, SSE comment)
    """
```

### Modifications

**`backend/app/core/logging.py`** — add a third sink:

```python
from app.core.log_buffer import _INSTANCE as log_buffer

# After existing stdout + file sinks:
logger.add(
    log_buffer.append_record,
    level="DEBUG",
    format="{message}",  # we use the record dict, not the formatted string
    serialize=False,
)
```

**`backend/app/scheduler/__init__.py`** — register the metrics listener:

```python
from app.services.scheduler_metrics import _INSTANCE as scheduler_metrics
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED

# After creating _scheduler:
_scheduler.add_listener(
    scheduler_metrics.on_event,
    EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED,
)
```

**`backend/app/main.py`** — include the new router:

```python
from app.api import platform_health as platform_health_router
app.include_router(platform_health_router.router)
```

### Auth

All three endpoints use `Depends(get_current_user)` — same as the rest of `/api/*`. The session cookie set on login covers SSE too (EventSource sends cookies by default for same-origin).

### Log capture wire-in

Loguru sinks accept a callable as target. The sink we add doesn't format anything — it just calls `log_buffer.append_record(record)` where `record` is loguru's structured dict. The `append_record` reshapes it into our smaller payload and notifies subscribers.

The catch: loguru calls sinks synchronously by default. If a subscriber is slow, it could block logging. Mitigation: SSE subscribers push to an `asyncio.Queue` and return immediately; the heavy lifting (serialization, network) runs in the SSE coroutine.

### SSE protocol details

```
event: snapshot
data: {"data_sources": {...}, "scheduler": [...], "scans": [...], "cache": {...}}

event: log
data: {"ts": 1747309200.5, "level": "WARNING", "module": "scan_service", ...}

: keepalive
```

The frontend's `EventSource` handles `event:` parsing natively. Heartbeat lines starting with `:` are SSE comments (per W3C spec) — they keep proxies/load-balancers from closing idle connections.

## Frontend design

### Route

`/health` (Italian label: "Salute"). Position in `Layout.tsx` nav: between Alerts and Impostazioni.

Icon: `HeartPulse` from `lucide-react` (already used in the project).

### New files

```
frontend/src/pages/PlatformHealthPage.tsx
frontend/src/components/health/HealthSummary.tsx     (4-card row)
frontend/src/components/health/DataSourcesCard.tsx
frontend/src/components/health/SchedulerCard.tsx
frontend/src/components/health/ScansCard.tsx
frontend/src/components/health/CacheCard.tsx
frontend/src/components/health/LogStream.tsx         (filterable table)
frontend/src/hooks/usePlatformHealthStream.ts        (SSE state hook)
```

### Modifications

```
frontend/src/components/Layout.tsx                   (add nav entry)
frontend/src/main.tsx (or wherever routes live)      (register route)
```

### Data flow

1. **Mount**: page issues initial REST calls in parallel:
   - `GET /api/platform/health` → fills the 4 cards
   - `GET /api/platform/logs?limit=500` → pre-populates the log stream
2. **Live**: page opens `new EventSource('/api/platform/stream')`. Hook updates state on:
   - `event: snapshot` → replace the 4 cards' data
   - `event: log` → append to the log buffer (cap 500 visible, drop oldest)
3. **Filters** are entirely client-side on the live buffer.
4. **Reconnect**: EventSource auto-reconnects on network drop; on reconnect, page silently re-fetches the snapshot to recover from missed events.

### Visual layout (text mock)

```
┌─ Salute piattaforma ─────────────────────────────────────────────────┐
│                                                                       │
│ ┌─Data Sources─┐ ┌─Scheduler────┐ ┌─Scan recenti──┐ ┌─Cache+DB─────┐ │
│ │ yfinance  ✓  │ │ 9 job · 1 KO │ │ Last: success │ │ L1f: 142 ent │ │
│ │ stooq    ✓   │ │ Next: scan_  │ │ 03m 12s · 47A │ │ L2f: 138 ent │ │
│ │ finnhub  ✓   │ │  alerts 23:30│ │               │ │ DB: 24.3 MB  │ │
│ │ fred    !    │ │              │ │ history: ↓↓↑→ │ │              │ │
│ │ marketaux ✓  │ │ details ▾    │ │               │ │ details ▾    │ │
│ └──────────────┘ └──────────────┘ └───────────────┘ └──────────────┘ │
│                                                                       │
│ ┌─ Log live ─ [Level: All ▾] [Module: ___] [Search: ___] [⏸] ─────┐  │
│ │ 14:17:48  INFO  [scan_service] iteration 522/1097 │              │
│ │ 14:17:47  WARN  [yfinance] timeout for AAPL, retry 1/2 │         │
│ │ 14:17:46  INFO  [fetch_cache_store] hydrate skip XYZ.MI: ... │   │
│ │ ...                                                              │
│ └──────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────┘
```

### Visual tone

- Stato verde / giallo / rosso: usa Tailwind tone classes già presenti (`bg-green-500/10 text-green-700` ecc.). Niente nuovi token.
- Log table: monospace font, color del livello (gray INFO, amber WARNING, red ERROR).
- Polling indicator: small `RefreshCw` icon animato durante l'attesa snapshot.
- Pause button: la UI può mettere in pausa il log stream (utile quando passa veloce) — modifica solo il behavior locale, l'EventSource resta aperto.

## Testing strategy

### Backend unit tests
- `test_log_buffer.py`: pub/sub correttezza, maxlen, snapshot con filtri
- `test_scheduler_metrics.py`: aggiornamento stats su EVENT_JOB_EXECUTED/ERROR/MISSED
- `test_cache_metrics.py`: snapshot shape su DB vuoto + popolato
- `test_api_platform_health.py`: integration test su REST endpoints (snapshot + filtered logs)

### Backend integration test for SSE
- Test che apre `client.stream("/api/platform/stream")` e verifica che:
  - Riceve initial snapshot event
  - Quando logger emette un record, arriva `event: log`
  - Heartbeat dopo 30s+ (skippato in test, troppo lento)

### Frontend
- Smoke test che la pagina renderizza con dati mock
- Skip dei test SSE in CI (fragile + lento) — covered by manual test

### Manual test (post-implementation)
- Avviare backend + frontend
- Aprire `/health`
- Verificare:
  - 4 card popolate con dati reali
  - Log stream parte popolato con ultime righe
  - Triggerare un evento (es. POST /api/admin/warmup-fundamentals?limit=2): vedere log fluire in tempo reale
  - Filtri (level WARNING+ riduce, search "yfinance" filtra)
  - Pause stoppa l'append visivo

## Risks

1. **SSE + uvicorn --reload su Windows**: noto fragile (HMR triggera disconnessione). Mitigazione: smoke test sui :8000 (prod build) dove non c'è reload.
2. **Loguru sink sincrono**: se il pub/sub-callback blocca, blocca anche il logging. Risolto rendendo i callback puramente non-bloccanti (push in queue + return).
3. **Volume log su scan grosso**: 1097 ticker × ~3 log/ticker = ~3000 log in pochi minuti. Maxlen 2000 li copre con un po' di scroll. Acceptable.
4. **EventSource & cookie auth**: same-origin → cookies inviati automaticamente. Cross-origin richiederebbe `withCredentials: true`; non è il nostro caso (serviamo frontend dal stesso host del backend).

## Decisioni already locked

| | |
|---|---|
| Route | `/health` |
| Nav label | "Salute" |
| Nav icon | `HeartPulse` (lucide) |
| Auth | `Depends(get_current_user)` (session cookie) |
| Log buffer maxlen | 2000 records server-side |
| Log visible maxlen | 500 client-side |
| Snapshot SSE cadence | 5s |
| SSE keepalive | 30s |
| Filter scope | Client-side (level + module + search substring) |
| No log download in v1 | confermato |
| No alerting in v1 | confermato |
