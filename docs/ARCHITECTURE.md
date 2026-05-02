# Finance Alert — Architettura tecnica

> Documento vivo. **Aggiornare ad ogni commit che modifica architettura, flussi, modello dati, dipendenze esterne, o policy operative.** Vedi §10 (Policy di manutenzione).

**Ultimo aggiornamento**: 2026-05-02
**Roadmap update 2026-05-02**: Fase 3D (Multi-channel notifiers) rimossa dal piano — out of scope.
**Stato applicazione**: Fase 1 in production. Fase 2 (alert engine) implemented. Fase 3A (Dashboard Home) implemented. Fase 3A-bis (Market Dashboard redesign) implemented. Fase 3B (Stock Detail) implemented.

---

## 1. Panoramica

Applicazione web full-stack single-user per:

- Catalogare e selezionare azioni in watchlist tematiche
- **(Fase 2 — implementato)** Monitorare segnali tecnici e inviare alert Telegram
- **(Fase 3A — implementato)** Dashboard riepilogativa su `/` con KPI, grafico alert/giorno, top 10 stock, feed alert recenti, stato sistema
- **(Fase 3A-bis — implementato)** Dashboard ridisegnata: hero strip (mood + KPI globali) + matrice breadth per-indice (7×11) + 4-col grid (movers tabbed/RSI histogram/sectors heatmap/52w-vol tabbed) + treemap mkt-cap × performance + alerts compact panel + system status footer slim. Snapshot pre-computato in `market_snapshot` rigenerato a fine scan (~0.75s su 201 stock)
- **(Fase 3B — implementato)** Pagina Stock Detail su `/stocks/:ticker` con candlestick chart (lightweight-charts), indicatori SMA/RSI, drawing tools (H-line persistite in localStorage), price-target alerts (nuovo dominio `PriceAlert` + edge-trigger evaluator integrato in scan_runner non-fatal), news headlines via yfinance (cache TTL 1h), vista read-only delle regole effettive (Tier 1 + override Tier 2). SpotlightCards reali in HomePage (top gainer + most-alerted-7d + vol spike) al posto del placeholder
- (Fase 3C+) Indicatori avanzati (MACD/BB/ATR/ADX), settings, hit-rate stats per regola

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
│ yfinance + numpy (OHLCV fetch)                  │
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
│ ├── refresh_catalog (weekly Sat 03:00)           │
│ ├── scan_alerts    (daily 23:30)                 │
│ └── send_digest    (daily 08:00)                 │
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

### Aggiunte Fase 2 — alert engine

```
┌──────────────────┐         ┌──────────────────┐
│  ohlcv_daily     │         │      rules       │  (Tier 1: watchlist_id=NULL
├──────────────────┤         ├──────────────────┤   Tier 2: watchlist_id IS NOT NULL)
│ stock_id ────┐   │         │ id               │
│ date         │PK │         │ watchlist_id ────┼──N:1──▶ watchlists (FK CASCADE, NULLABLE)
│ open/high/low│   │         │ kind             │
│ close/volume │   │         │ params (JSON)    │
└──────┬───────┘   │         │ enabled          │
       │ N:1       │         │ created_at       │
       ▼           │         │ updated_at       │
    stocks         │         └────────┬─────────┘
                   │                  │ 1:N
                   │                  ▼
┌──────────────────┐    ┌──────────────────────┐
│   rule_states    │    │      alerts          │
├──────────────────┤    ├──────────────────────┤
│ rule_id  ────────┼──N:1│ id                   │
│ stock_id ────────┼──N:1│ rule_id ─────────────┼──N:1──▶ rules
│ last_evaluation  │    │ stock_id ────────────┼──N:1──▶ stocks
│ last_evaluated_at│    │ triggered_at         │
└──────────────────┘    │ trigger_price        │
                        │ snapshot (JSON)      │
                        │ read_at              │
                        │ archived_at          │
                        └──────────────────────┘
```

- **Edge-trigger model**: `rule_states` keyed by `(rule_id, stock_id)`; alerts fired only on `False → True` transition.
- **3-tier rule resolution**: per `(stock, kind)` la regola effettiva si determina come segue:
  1. Tier 2 disabled override (most restrictive) → rule skipped
  2. Tier 2 enabled override with custom params → uses overridden params, state still keyed by global `rule_id`
  3. Tier 1 global → default behavior
- Migration `aabe2bc3256f` applied via Alembic.

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
| **Fase 1** — Watchlist viewer | **Implementata** | Catalogo, watchlist CRUD, autosave, refresh catalogo, login, autostart Windows |
| **Fase 2** — Alert engine | **Implementata** | Fetch OHLCV (yfinance), indicatori (SMA/EMA/RSI), regole alert (RSI, Golden/Death cross), notifier Telegram, scheduler giornaliero |
| **Fase 3A** — Dashboard Home | **Implementata** | Dashboard `/` con KPI cards, AlertsByDayChart (Recharts), TopStocksTable, RecentAlertsFeed, SystemStatusCard. BFF `/api/dashboard/summary`, polling 30s |
| **Fase 3A-bis** — Market Dashboard | **Implementata** | Redesign con primary-focus su statistiche tecniche per-indice. Snapshot pre-computato (`market_snapshot`) a fine scan; endpoint `/api/dashboard/market-summary`; 13 nuovi componenti (HeroStrip + BreadthMatrix + Movers/RSI/Sectors/52w-Vol + Treemap + AlertsCompactPanel + SystemStatusFooter); densità informativa alta con breakdown per i 7 indici (SP500/NDX/DJI/EUSTX50/FTSEMIB/SSE50/HSI30) |
| **Fase 3B** — Stock Detail | **Implementata** | Pagina `/stocks/:ticker` con candlestick (lightweight-charts) + SMA + volume + RSI panel + drawing tools (H-line) + price-target alerts (nuovo modello `PriceAlert` + endpoint CRUD + evaluator non-fatal in scan_runner) + news yfinance (cache 1h) + alert history per-stock + effective_rules read-only Tier1/Tier2. SpotlightCards in HomePage al posto del placeholder. |
| **Fase 3C** — Indicatori avanzati | Futura | MACD, Bollinger Bands, ATR, ADX; regole volume/breakout; editor regole UI con AND/OR |
| **Fase 3E** — Settings & hit-rate | Futura | Pagina settings, statistiche hit-rate per regola, UI stato refresh catalogo |

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
| 2026-04-30 | 6fd274a | Fase 1 complete: 30 tasks across 10 sections (A-J) shipped. Backend (FastAPI + SQLAlchemy + APScheduler + 48 tests) and frontend (React + Vite + shadcn + autosave) deliver an end-to-end watchlist editor over a seeded catalog with weekly Wikipedia refresh. README finalized; Windows auto-start scripts ready. |
| 2026-04-30 | initial | Creazione documento, descrizione architettura Fase 1 (in pianificazione) |
| 2026-04-30 | 0ffebfb | Schema persisted via Alembic migration. SQLite tables: users, stocks, indices, stock_indices, watchlists, watchlist_items, catalog_refresh_log. WAL mode active via SQLAlchemy connect-listener. |
| 2026-04-30 | 1621dfa | Auth endpoints live: POST /api/auth/login, POST /api/auth/logout, GET /api/auth/me. Cookie session with SameSite=Strict, signed via itsdangerous. CSRF guard via JSON content-type on mutating routes (deps.require_json). |
| 2026-04-30 | 93e6056 | Watchlists CRUD endpoints live: list/create/get/patch/delete + items add/remove/bulk-delete. CSRF guard on mutating routes via require_json. |
| 2026-04-30 | bb5ec8d | APScheduler in-process started via FastAPI lifespan. Cron job `refresh_catalog` runs Sat 03:00 Europe/Rome. Health endpoint returns scheduler_running. |
| 2026-04-30 | 23578f3 | Frontend complete: autosave watchlist editor with create-on-first-edit, debounced text saves, AbortController race-safety, optimistic add/remove. End-to-end watchlist CRUD UI is live. |
| 2026-04-30 | b2f96f9 | Production-local mode: FastAPI serves frontend `dist/` as static + SPA fallback. `just prod-local` runs the full app on a single port (8000). |
| 2026-04-30 | 2f926ab | Windows auto-start at user logon via PowerShell scripts (`scripts/windows/`). Register-FinanceAlertStartup.ps1 creates a Task Scheduler entry without admin; Run-FinanceAlert.ps1 boots prod-local with rotated logs. |
| 2026-05-01 | 6b66d02 | Fase 2 alert engine: catalog espanso a ~210 stocks (+EuroStoxx 50, SSE 50, Hang Seng top 30); 4 regole pre-installate con edge-trigger; APScheduler jobs scan_alerts (23:30) + send_digest (08:00); Telegram digest mode; pagina /alerts con filtri+bulk+export CSV; RulesOverrideEditor 3-stati nella WatchlistDetailPage; sidebar unread badge. ~103 test backend. |
| 2026-05-01 | 6e51068 | Fase 3A: Dashboard Home `/` con KPI cards (alert 24h con delta, non letti, stock monitorati, ultimo scan), AlertsByDayChart (Recharts AreaChart 30gg con tooltip per-rule), TopStocksTable (link a /alerts?ticker=), RecentAlertsFeed (riusa AlertDetailDialog), SystemStatusCard (scheduler/Telegram/next runs). Single BFF endpoint `/api/dashboard/summary` aggrega tutto via `stats_service` (4 funzioni); polling 30s via TanStack Query. Sidebar Dashboard entry attivata. ~13 nuovi test backend (stats_service + dashboard API). |
| 2026-05-02 | ae58161 | Fase 3A-bis: Market Dashboard redesign con primary-focus su statistiche tecniche per-indice. Nuova tabella `market_snapshot` (single-row, UPSERT id=1) generata a fine ogni scan in modo non-fatal (~0.75s su 201 stock). Nuovo `market_stats_service` con compute_stock_metrics (SMA50/200, RSI14, 52w extremes, vol_ratio), aggregate per global/index/sector, builders per movers/RSI distribution/treemap, e derive_mood (bullish/neutral/bearish da breadth). Nuovo endpoint `/api/dashboard/market-summary` parallelo a `/summary`, polling 30s indipendente. UI: 13 nuovi componenti dashboard (HeroStrip + MoodCard + GlobalKpiTiles + DataFreshnessCard + BreadthMatrixTable 7×11 + MoversCard tabbed + RsiHistogramCard con dropdown indice + SectorsHeatmapCard + FiftyTwoWeekVolCard tabbed + MarketTreemap Recharts + SpotlightPlaceholder + AlertsCompactPanel tabbed + SystemStatusFooter slim). HomePage rewrite, vecchio SystemStatusCard rimosso, AlertsByDayChart con prop `compact`. ~22 nuovi test backend (totale 142 + 2 flake date-rollover). Bundle 933→999 kB. |
| 2026-05-02 | 481857e | Fase 3B Stock Detail: nuova pagina `/stocks/:ticker` (layout grid 2-col chart+sidebar). Nuovo dominio PriceAlert (tabella `price_alerts` + edge-trigger evaluator non-fatal in scan_runner; alerts.rule_id reso nullable per supportare alert price-target con rule_id=NULL). Nuovi endpoint `/api/stocks/{ticker}/detail` (range 1m/3m/6m/1y/all), `/news` (yfinance + cache TTL 1h + graceful fallback), `/price-alerts` CRUD (4 verb), `/api/dashboard/spotlight`. Frontend: lightweight-charts 4.2 (candlestick + SMA50/200 overlays + volume + RSI panel separato + price-line drawings); 14 nuovi componenti stock + 5 hooks (useStockDetail, useStockPriceAlerts CRUD, useStockNews 1h cache, useSpotlight 60s polling, useStockDrawings localStorage); SpotlightCards (3 sparkline mini-card → click /stocks/:ticker) sostituisce SpotlightPlaceholder; Treemap navigate su click; Stocks sidebar entry attivata (link `/stocks/AAPL`). ~28 nuovi test backend (totale 182 passing). Bundle 999→1210 kB (+lightweight-charts). |
