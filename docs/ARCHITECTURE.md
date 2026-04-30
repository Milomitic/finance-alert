# Finance Alert — Architettura tecnica

> Documento vivo. **Aggiornare ad ogni commit che modifica architettura, flussi, modello dati, dipendenze esterne, o policy operative.** Vedi §10 (Policy di manutenzione).

**Ultimo aggiornamento**: 2026-04-30
**Stato applicazione**: Fase 1 in pianificazione, nessun codice implementato.

---

## 1. Panoramica

Applicazione web full-stack single-user per:

- Catalogare e selezionare azioni in watchlist tematiche
- (Fase 2) Monitorare segnali tecnici e inviare alert
- (Fase 3) Visualizzare statistiche e grafici

**Modello di deployment**: locale sul PC dell'utente (Windows 11). Nessun cloud, nessuna esposizione di rete.

## 2. Stack tecnologico

```
┌─ Frontend ──────────────────────────────────────┐
│ React 18 + TypeScript                           │
│ Vite (bundler / dev server)                     │
│ TailwindCSS + shadcn/ui                         │
│ TanStack Query (server state)                   │
│ React Router                                    │
│ React Hook Form + Zod                           │
│ Recharts (Fase 3) + lightweight-charts (Fase 3) │
└─────────────────────────────────────────────────┘
              ↕ HTTP /api (JSON, cookie session)
┌─ Backend ───────────────────────────────────────┐
│ Python 3.11+                                    │
│ FastAPI                                         │
│ SQLAlchemy 2.0 + Alembic (migrations)           │
│ APScheduler (in-process)                        │
│ pydantic-settings, loguru                       │
│ pandas + lxml (HTML scraping)                   │
│ bcrypt + itsdangerous (auth)                    │
└─────────────────────────────────────────────────┘
              ↕ SQLAlchemy
┌─ Storage ───────────────────────────────────────┐
│ SQLite (file ./backend/data/app.db, WAL mode)   │
│ Filesystem logs ./backend/data/logs/            │
└─────────────────────────────────────────────────┘
```

**Tooling**: `uv` (package mgr), `ruff` (lint+format), `pyright` (types), `pytest` (test), `vitest`, `eslint`, `prettier`, `just` (task runner).

## 3. Topologia di esecuzione

### 3.1 Modalità development

Due processi distinti, hot-reload entrambi.

```
┌──────────────────────────┐    ┌──────────────────────────┐
│ uvicorn :8000            │    │ vite dev :5173           │
│ FastAPI + APScheduler    │    │ proxy /api → :8000       │
│ ./backend/data/app.db    │    │ React SPA con HMR        │
└─────────────▲────────────┘    └─────────────▲────────────┘
              │                                │
              └─────────browser ───────────────┘
                       localhost:5173
```

Avvio: `just up` (Git Bash) oppure due terminali con `just be` e `just fe`.

### 3.2 Modalità prod-local

Un solo processo. FastAPI serve sia API che assets React buildati.

```
┌──────────────────────────────────────────────────┐
│ uvicorn :8000                                    │
│ ┌────────────────────────────────────────────┐   │
│ │ FastAPI                                    │   │
│ │ ├── /api/* → router (JSON)                 │   │
│ │ └── /*     → StaticFiles(frontend/dist)    │   │
│ │             SPA fallback → index.html      │   │
│ └────────────────────────────────────────────┘   │
│ APScheduler                                      │
│ └── refresh_catalog (weekly, Sat 03:00 local)    │
│ ./backend/data/app.db                            │
└────────────────────▲─────────────────────────────┘
                     │
                  browser → localhost:8000
```

Avvio:
- Manuale: `just prod-local`
- Automatico al logon Windows: Task Scheduler → `Run-FinanceAlert.ps1` (vedi §8)

## 4. Modello dati

ERD (Fase 1):

```
┌──────────┐
│  users   │  (1 sola riga, l'admin)
├──────────┤
│ id       │
│ username │
│ password_hash
│ created_at
└─────┬────┘
      │ 1:N
      ▼
┌──────────────┐         ┌──────────────────┐
│  watchlists  │         │      stocks      │
├──────────────┤         ├──────────────────┤
│ id           │         │ id               │
│ name         │         │ ticker           │
│ description  │         │ exchange         │
│ user_id ─────┘         │ name             │
│ created_at             │ sector           │
│ updated_at             │ industry         │
└──────┬───────┘         │ country          │
       │ 1:N             │ currency         │
       ▼                 │ market_cap       │
┌──────────────────┐     │ created_at       │
│ watchlist_items  │     │ updated_at       │
├──────────────────┤     └──────┬───────────┘
│ watchlist_id ────┼──N:1        │ M:N
│ stock_id ────────┼──N:1───────▼
│ added_at         │     ┌─────────────────┐
└──────────────────┘     │ stock_indices   │
                         ├─────────────────┤
                         │ stock_id        │
                         │ index_id ───────┼──N:1───┐
                         └─────────────────┘        │
                                                    ▼
                                              ┌──────────┐
                                              │ indices  │
                                              ├──────────┤
                                              │ id       │
                                              │ code     │ (SP500, NDX, DJI, FTSEMIB)
                                              │ name     │
                                              │ country  │
                                              └──────────┘

┌──────────────────────┐
│ catalog_refresh_log  │  (audit trail del job settimanale)
├──────────────────────┤
│ id                   │
│ index_code           │
│ started_at           │
│ completed_at         │
│ status               │ (success | failed)
│ stocks_added         │
│ stocks_updated       │
│ stocks_removed       │
│ error_message        │
└──────────────────────┘
```

**Indici**:
- `stocks(ticker, exchange)` UNIQUE
- `stocks(exchange)`, `stocks(sector)`, `stocks(country)` per filtri
- `stock_indices(stock_id)`, `stock_indices(index_id)` per join

**Migrations**: gestite da Alembic, versioned in `backend/alembic/versions/`. Ogni cambio di modello richiede una migration generata e committata insieme al codice.

## 5. Flussi applicativi principali

### 5.1 Login

```
Browser              FastAPI                 SQLite
   │                    │                       │
   │ POST /api/auth/login                       │
   │ {username, password}                       │
   ├───────────────────▶│                       │
   │                    │ SELECT user           │
   │                    ├──────────────────────▶│
   │                    │◀──────────────────────┤
   │                    │ bcrypt.verify         │
   │                    │ ─────┐                │
   │                    │ ◀────┘                │
   │                    │ sign session payload  │
   │                    │ (itsdangerous)        │
   │ 200 + Set-Cookie   │                       │
   │   finance_alert_session                    │
   │   httpOnly, SameSite=Strict                │
   │◀───────────────────┤                       │
   │                    │                       │
```

Sessione persistita 7 giorni con sliding refresh (rinnovo a ogni richiesta autenticata).

### 5.2 Ricerca stock con filtri

```
Browser           FastAPI                  SQLite
   │                 │                        │
   │ GET /api/stocks/search?exchange=NASDAQ&sector=Tech&limit=50
   ├────────────────▶│                        │
   │                 │ Build query con join   │
   │                 │ stocks ⨝ stock_indices │
   │                 │ WHERE ... LIMIT 50     │
   │                 ├───────────────────────▶│
   │                 │◀───────────────────────┤
   │ 200 {items, total, has_more}             │
   │◀────────────────┤                        │
```

Pagination via `limit` + cursor implicito su `id`. Max 500.

### 5.3 Autosave watchlist (modalità edit)

```
User digita "name" ───┐
                      │
                      ▼
            ┌─────────────────────┐
            │ Debounce 500ms      │
            │ (lodash o RAF)      │
            └──────────┬──────────┘
                       │
                       ▼
            ┌─────────────────────┐
            │ AbortController     │  ← cancella richiesta in volo
            │ Fetch PATCH /api/   │     se ne arriva una nuova
            │   watchlists/:id    │
            │ {name}              │
            └──────────┬──────────┘
                       │
            ┌──────────┴──────────┐
            ▼                     ▼
       success               error
       │                     │
       ▼                     ▼
       Indicator             Indicator + Retry button
       "Salvato"             "Errore di salvataggio"
```

Lo stato visivo è derivato da TanStack Query mutation state: `idle`/`pending`/`success`/`error`.

**Caso edge — modalità create**: la prima volta che il nome diventa non-vuoto e supera il debounce, parte un POST `/api/watchlists` (non PATCH). Risposta contiene l'`id` della nuova watchlist. L'URL viene aggiornato con `history.replaceState` da `/watchlists/new` a `/watchlists/:id`. Tutte le mutation successive sono PATCH/POST/DELETE su quell'id.

### 5.4 Aggiunta stock alla watchlist

```
User clicca "+ aggiungi" su un risultato di ricerca
   │
   ▼
Frontend: optimistic update (chip appare subito)
   │
   ▼
POST /api/watchlists/:id/items {stock_ids: [N]}
   │
   ├── 200: nessuna azione, stato consistente
   └── error: rollback ottimistico, mostra toast errore
```

### 5.5 Refresh catalogo (job settimanale)

```
APScheduler trigger (cron sab 03:00 local)
              │
              ▼
   ┌─────────────────────────────┐
   │ For each index (SP500,      │
   │   NDX, DJI, FTSEMIB):       │
   └──────────────┬──────────────┘
                  │
                  ▼
        ┌──────────────────────┐
        │ INSERT catalog_      │
        │   refresh_log        │
        │ status=in_progress   │
        └──────────┬───────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │ pandas.read_html(URL)│
        │ + retry exp.backoff  │
        │ (3 tentativi)        │
        └──────────┬───────────┘
                   │
            ┌──────┴──────┐
            ▼             ▼
         success        failure (after retries)
         │              │
         ▼              ▼
   parse table      log error
   upsert stocks    update log row
   rebuild          status=failed
   stock_indices    error_message=...
   membership
   │
   ▼
   update log row
   status=success
   counts=...
```

Trigger manuale: `POST /api/catalog/refresh` esegue lo stesso job in background (FastAPI BackgroundTasks o `scheduler.add_job(...)` con `run_date=now`).

## 6. Architettura del backend (modulare)

Separazione in layer per testabilità:

```
api/        → router FastAPI, deserializza request, chiama services
schemas/    → Pydantic, contratto request/response
services/   → logica di business pura (riceve session SQLAlchemy, ritorna domain objects)
models/     → SQLAlchemy ORM
core/       → config, db engine, security primitives, logging
scheduler/  → APScheduler setup + job functions (chiamano services)
fetchers/   → (Fase 2) yfinance + fallback
indicators/ → (Fase 2) calcoli TA puri (input: DataFrame, output: Series)
rules/      → (Fase 2) regole alert come classi con interfaccia comune
notifiers/  → (Fase 2) Telegram, email, webhook
```

**Regola di dipendenza**: i layer interni non importano i layer esterni. `services` non importa `api`. `models` non importa `services`. Test su services usano session SQLAlchemy fittizia (SQLite in-memory) senza FastAPI.

## 7. Sicurezza

### 7.1 Autenticazione

Single-user. Password admin generata via bcrypt cost 12, hash salvato in `.env` come `ADMIN_PASSWORD_HASH`.

Cookie sessione: signed con `itsdangerous` usando `SECRET_KEY`. Payload: `{username, exp}`.

### 7.2 CSRF

Difesa strutturale, niente token dedicato:

1. **`SameSite=Strict`** sul cookie sessione: il browser non lo invia su navigazioni cross-site
2. **`Content-Type: application/json` enforced** su POST/PATCH/DELETE: i form HTML cross-origin non possono inviare JSON

Per single-page same-origin questo è sufficiente.

### 7.3 Validazione input

Tutti i body sono Pydantic schemas. Query parameters sono typed via FastAPI. Nessuna concatenazione SQL — solo SQLAlchemy parametrizzato.

### 7.4 Secrets

Tutti via `.env`. `.env` è in `.gitignore`; `.env.example` ha solo nomi delle chiavi senza valori. Nessun secret hardcoded mai.

## 8. Esecuzione background su Windows

Strategia: Windows Task Scheduler con trigger `AtLogOn`.

```
Logon utente
     │
     ▼
Task Scheduler ─── lancia ──▶ powershell.exe -WindowStyle Hidden
                              -File Run-FinanceAlert.ps1
                                       │
                                       ▼
                              Set-Location $ProjectRoot
                                       │
                                       ▼
                              uv run uvicorn app.main:app --port 8000
                              (frontend statico già in dist/)
                                       │
                                       ▼
                              ──── App attiva su localhost:8000 ────
```

Setup tramite `scripts/windows/Register-FinanceAlertStartup.ps1` (no admin richiesto). Restart automatico in caso di crash (3 tentativi via Task Scheduler policy). Log dedicato `backend/data/logs/windows-task.log` con rotazione.

## 9. Roadmap fasi

| Fase | Stato | Contenuto principale |
|---|---|---|
| **Fase 1** — Watchlist viewer | In pianificazione | Catalogo, watchlist CRUD, autosave, refresh catalogo, login, autostart Windows |
| **Fase 2** — Alert engine | Futura | Fetch OHLCV (yfinance), indicatori (SMA/EMA/RSI), regole alert (RSI, Golden/Death cross), notifier Telegram, scheduler giornaliero |
| **Fase 3** — Dashboard & analytics | Futura | Home con KPI, candlestick stock detail, hit rate, regole MACD/BB/volume/breakout, editor regole UI con AND/OR, UI stato refresh catalogo |

## 10. Policy di manutenzione di questo documento

Questo file è **vincolante**: ogni commit che introduce uno dei seguenti cambiamenti deve aggiornarlo nello stesso commit:

- Nuova entità o modifica schema DB
- Nuovo endpoint API (o cambio del contratto di uno esistente)
- Nuovo flusso applicativo significativo
- Nuova dipendenza esterna (libreria, servizio, fonte dati)
- Cambio di topologia di esecuzione (dev, prod-local, eventuale futuro deploy)
- Cambio policy di sicurezza
- Nuovo job APScheduler o modifica schedule esistente
- Inizio/fine di una fase della roadmap

**Formato dell'aggiornamento**:

1. Aggiornare la sezione rilevante con la modifica
2. Aggiornare `**Ultimo aggiornamento**: YYYY-MM-DD` in cima
3. Aggiungere un'entry in `## 11. Changelog` in fondo

**Verifica in code review**: chiunque revisioni un PR/commit con cambi architetturali deve verificare che `ARCHITECTURE.md` rifletta lo stato post-merge. Se manca, il commit non è completo.

## 11. Changelog

| Data | Commit | Cambiamento |
|---|---|---|
| 2026-04-30 | initial | Creazione documento, descrizione architettura Fase 1 (in pianificazione) |
| 2026-04-30 | 0ffebfb | Schema persisted via Alembic migration. SQLite tables: users, stocks, indices, stock_indices, watchlists, watchlist_items, catalog_refresh_log. WAL mode active via SQLAlchemy connect-listener. |
| 2026-04-30 | 1621dfa | Auth endpoints live: POST /api/auth/login, POST /api/auth/logout, GET /api/auth/me. Cookie session with SameSite=Strict, signed via itsdangerous. CSRF guard via JSON content-type on mutating routes (deps.require_json). |
| 2026-04-30 | 93e6056 | Watchlists CRUD endpoints live: list/create/get/patch/delete + items add/remove/bulk-delete. CSRF guard on mutating routes via require_json. |
| 2026-04-30 | bb5ec8d | APScheduler in-process started via FastAPI lifespan. Cron job `refresh_catalog` runs Sat 03:00 Europe/Rome. Health endpoint returns scheduler_running. |
| 2026-04-30 | 23578f3 | Frontend complete: autosave watchlist editor with create-on-first-edit, debounced text saves, AbortController race-safety, optimistic add/remove. End-to-end watchlist CRUD UI is live. |
| 2026-04-30 | b2f96f9 | Production-local mode: FastAPI serves frontend `dist/` as static + SPA fallback. `just prod-local` runs the full app on a single port (8000). |
| 2026-04-30 | 2f926ab | Windows auto-start at user logon via PowerShell scripts (`scripts/windows/`). Register-FinanceAlertStartup.ps1 creates a Task Scheduler entry without admin; Run-FinanceAlert.ps1 boots prod-local with rotated logs. |
