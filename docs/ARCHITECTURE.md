# Finance Alert — Architettura tecnica

> Documento vivo. **Aggiornare ad ogni commit che modifica architettura, flussi, modello dati, dipendenze esterne, o policy operative.** Vedi §10 (Policy di manutenzione).

**Ultimo aggiornamento**: 2026-05-22
**Stato applicazione**: in production come **piattaforma di research/screening
azionario** single-user. Tutte le fasi 1-3 implementate ed estese ben oltre il
piano originale. Sottosistemi attivi: scoring composito 6-pilastri (IC-validato),
dashboard di mercato, screener, stock-detail con chart, calendario earnings+macro,
istituzionali/13F, pre-market USA, alert engine + digest Telegram, salute
piattaforma. Le **watchlist sono state rimosse** (lo screener `/stocks` + lo
scoring le hanno rese superflue) — vedi nota in §4.

> Le sezioni §4 (modello dati) e §5 (flussi) descrivono il **nucleo originale
> Fase 1/2** e restano in gran parte valide; per i sottosistemi aggiunti dopo
> (scoring, fonti dati, istituzionali, pre-market, fondamentali PIT) vedi la
> nuova **§3.5 Sottosistemi attuali**.

---

## 1. Panoramica

Applicazione web full-stack single-user per la **ricerca e selezione azionaria**.
Ingerisce ~1.000 titoli globali ogni notte, ne calcola uno **score composito**,
e li espone attraverso una dashboard di mercato, uno screener, pagine di
dettaglio ricche e un motore di alert. Funzioni principali:

- **Scoring** — score composito 0-100 per titolo da **5 pilastri** (Profitability ·
  Sustainability · Growth · Value · Sentiment — `PILLAR_WEIGHTS` in
  `score_service/common.py`), classificazione in risk-tier, smoothing EWMA con
  isteresi. Il pilastro **Momentum è stato RIMOSSO**: la price-action appartiene
  alla lente Tecnico, tenerla anche qui era leakage fra lenti.
  ⚠️ **I pesi NON sono "validati sull'Information Coefficient".** Il backtest IC
  point-in-time (2026-07-07, 552 titoli US, 39 cross-section trimestrali, 20.217
  osservazioni — `app/data/score_ic_report.json`) ha trovato l'**opposto**:
  nessun pilastro raggiunge la significatività (profitability IC −0.006 t=−0.39 ·
  sustainability +0.000 t=0.04 · growth +0.041 t=1.68), il composito è IC +0.015
  (t=0.81) con **decile spread NEGATIVO** e non monotono. Conclusione operativa:
  **il composito Qualità è un DESCRITTORE di qualità aziendale, non un predittore
  di rendimento** — non va ripesato su basi di alpha. Vedi `docs/scoring-algorithm.md`.
- **Dashboard** (`/`) — hero mood + KPI globali, matrice breadth per-indice,
  top-movers con polling live 15s su pool ampio, top-volume, RSI histogram,
  sector heatmap, 52w/vol, card pre-market USA, top-pick per score, consensus
  superinvestor, ultime azioni analisti. Snapshot pre-computato in
  `market_snapshot` a fine scan.
- **Screener** (`/stocks`) — filtro/ordina il catalogo per score/settore/indice/
  fondamentali (ha soppiantato le watchlist).
- **Stock detail** (`/stocks/:ticker`) — candlestick (lightweight-charts) con
  indicatori adattivi al range (SMA/EMA/RSI/MACD/BB), multi-timeframe (5m→mensile),
  fondamentali, valutazione, target+azioni analisti, insider, holder
  istituzionali, news.
- **Istituzionali** (`/institutionals`) — portafogli 13F superinvestor/fondi
  (SEC EDGAR), holder per-stock, infografiche allocation dual-encoded.
- **Settori** (`/sectors`), **Calendario** (`/calendar`, earnings+macro),
  **Market detail** (`/market/:symbol`, indici/commodity/crypto live),
  **Alert** (`/alerts`, regole tecniche edge-triggered + digest Telegram),
  **Salute piattaforma** (`/health`, stato di ogni fonte dati).

**Modello di deployment — DUE, non uno** (branch diversi, stessa codebase):

| | `master` — locale | `cloud` — questo branch |
|---|---|---|
| Dove gira | PC dell'utente (Windows 11) | VM Ampere A1 su OCI Always-Free |
| DB | SQLite (`./backend/data/app.db`) | **PostgreSQL** (CloudNativePG su k3s) |
| Esposizione | nessuna (LAN opzionale su `0.0.0.0`) | **HTTPS pubblico** su `80-225-80-141.sslip.io`, :443 IP-allowlistato via NSG |
| Orchestrazione | processo singolo / `just up` | k3s + Helm + ArgoCD (GitOps) |

Lo stesso codice serve entrambi: il DB è astratto via SQLAlchemy con un helper
dialect-aware (`app/core/db_json.py`), e `postgres.enabled` nel chart decide se
l'app parla SQLite o Postgres. **Il resto di questo documento descrive
l'applicazione** (valida per entrambi); la topologia cloud è in §3.3 e in
`docs/cloud/`.

## 2. Stack tecnologico

```
┌─ Frontend ──────────────────────────────────────┐
│ React 19 + TypeScript                           │
│ Vite 8 (bundler / dev server)                   │
│ TailwindCSS + shadcn/ui                         │
│ TanStack Query 5 (server state)                 │
│ React Router                                    │
│ React Hook Form + Zod                           │
│ lightweight-charts (candle) + Recharts          │
└─────────────────────────────────────────────────┘
              ↕ HTTP /api (JSON, cookie session)
┌─ Backend ───────────────────────────────────────┐
│ Python 3.11+                                    │
│ FastAPI                                         │
│ SQLAlchemy 2.0 + Alembic (migrations)           │
│ APScheduler (in-process cron)                   │
│ pydantic-settings, loguru                       │
│ pandas + numpy (metrics, indicators)            │
│ yfinance (primary market data)                  │
│ requests / httpx (Finnhub, Marketaux, FRED,     │
│   SEC EDGAR, ForexFactory, Nasdaq)              │
│ bcrypt + itsdangerous (auth)                    │
└─────────────────────────────────────────────────┘
              ↕ SQLAlchemy / two-tier cache (L1 dict + L2 fetch_cache)
┌─ Storage ───────────────────────────────────────┐
│ SQLite (file ./backend/data/app.db, WAL mode)   │
│ fetch_cache table (L2 persistent payload cache) │
│ Runtime state: breakers.json, ff_calendar.xml   │
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
│ APScheduler (in-process cron)                    │
│ ├── scan_alerts          (daily 23:30 → score    │
│ │     recompute + market snapshot + alert eval)  │
│ ├── send_digest          (daily 08:00, Telegram) │
│ ├── refresh_catalog      (weekly, Wikipedia)     │
│ ├── refresh_fred         (every 2h, macro)       │
│ ├── refresh_institutionals + refresh_sec_13f     │
│ ├── refresh_imminent_earnings (Finnhub calendar) │
│ ├── refresh_premarket    (*/5 in US PM window)   │
│ ├── health_probes_fast/slow (5m / 30m)           │
│ └── cleanup_orphan_scans, dedupe_stocks          │
│ ./backend/data/app.db                            │
└────────────────────▲─────────────────────────────┘
                     │
                  browser → localhost:8000
```

Avvio:
- Manuale: `just prod-local`
- Automatico al logon Windows: Task Scheduler → `Run-FinanceAlert.ps1` (vedi §8)

### 3.3 Modalità cloud (branch `cloud`) — LIVE

Stessa immagine, stesso codice; cambiano DB, esposizione e chi lo tiene in piedi.

```
                         Internet
                            │
   :80  0.0.0.0/0 ──────────┤   :443  solo IP allowlistato (NSG)
   SOLO challenge ACME      │   ← qui vive tutto il resto
   (404 su tutto il resto)  │
                    ┌───────▼────────────┐
                    │ Traefik (in k3s)   │ cert-manager + Let's Encrypt
                    │                    │ HTTP-01 → 80-225-80-141.sslip.io
                    └───────┬────────────┘
                            │
                    ┌───────▼────────────┐
                    │ FastAPI + SPA      │ StatefulSet 1 replica
                    │ APScheduler        │ APP_ENV=production → cookie Secure
                    └───┬────────────┬───┘
         legge/scrive   │            │ /metrics
                  ┌─────▼──┐         │
                  │Postgres│ CloudNativePG · TLS obbligatorio
                  │  `pg`  │ ruolo app NON-superuser · pgaudit
                  └───┬────┘ NetworkPolicy
      WAL continuo +  │
      base giornaliero│
                  ┌───▼──────────┐
                  │ OCI Object   │ barman-cloud (API S3-compat)
                  │ Storage      │ restore VERIFICATO
                  └──────────────┘
                            osservabilità
                    ┌───────────────────────────────┐
                    │ Prometheus · Grafana · Loki   │
                    │ Alertmanager → Telegram       │
                    └───────────────────────────────┘
```

**Perché single-replica** (non è pigrizia): APScheduler gira **in-process**, quindi
una seconda replica duplicherebbe ogni scan. Il multi-replica richiede prima una
leader-election per lo scheduler — finché non c'è, `replicaCount: 1` è corretto.

**Il DB è astratto, non riscritto**: `app/core/db_json.py` espone `json_text()`,
un costrutto `@compiles` che emette `json_extract()` su SQLite e `jsonb ->>` su
Postgres. Lo stesso codice ORM serve entrambi i branch; una lane CI dedicata
(`backend-postgres`) gira contro un Postgres reale per impedire regressioni.

Deploy: push su `cloud` → GitHub Actions (test + immagine arm64 → GHCR + bump del
tag) → **ArgoCD** in-cluster fa pull e applica. È pull-based per necessità: la NSG
blocca la :6443 a chiunque non sia l'IP del proprietario, quindi la CI **non può**
raggiungere il cluster. Dettagli in `docs/cloud/` (ROADMAP, GITOPS, OBSERVABILITY,
RUNBOOK-postgres-dr).

## 3.5 Sottosistemi attuali

Aggiunti dopo il nucleo Fase 1/2. Ognuno ha il proprio servizio in
`backend/app/services/` e (dove serve) job schedulato + router API.

### 3.5.1 Scoring engine (`score_service.py`)

Score composito 0-100 per titolo = media pesata di 6 pilastri (vedi §1 e
`docs/scoring-algorithm.md`), ciascuno 0-100 con **rinormalizzazione dei pesi
sui pilastri presenti** (un pilastro senza dati viene escluso, non azzerato).
Caratteristiche:

- **Sector-aware**: i pilastri value/profitability/growth confrontano il titolo
  con la mediana del suo settore (`_build_sector_stats` pre-pass).
- **EWMA + isteresi**: lo score e il risk-tier sono smoothed run-over-run per
  controllare il churn (`_apply_turnover_control`).
- **Risk overlay**: fattore vol/beta bounded che modula il composite.
- **Cross-sectional engine** (`_apply_cross_sectional_engine`, flag
  `SCORE_ENGINE_XS`): percentile sector-relative + shrinkage bayesiano.
  **Disattivato di default** — la validazione IC ha mostrato che degrada il
  segnale predittivo su questo universo.
- **Validazione IC**: `app/scripts/entry_ic_report.py` è un harness read-only
  che misura l'Information Coefficient (rank-IC vs forward return a 5/21/63/252
  giorni) di ogni segnale contro dati **point-in-time**, e confronta retune
  OLD-vs-NEW prima del commit. Persistenza score in `stock_scores`.

### 3.5.2 Layer fonti dati (multi-source con fallback)

Nessun provider è dipendenza hard. Pipeline e protezioni:

- **News**: yfinance → Finnhub → Marketaux (in ordine di larghezza-quota).
- **Analyst actions**: yfinance `upgrades_downgrades` + Finnhub upgrade/downgrade
  (deduplicati per firm+data±3g) + estrazione regex dalle news (con gate di
  presenza-ticker e fetch del corpo articolo come last-resort).
- **Earnings**: yfinance + Finnhub actuals (più veloci a popolarsi).
- **Macro**: FRED (serie) + ForexFactory (consensus, con cache su disco 6h).
- **13F**: SEC EDGAR submissions/infotable.
- **Fondamentali point-in-time**: SEC EDGAR XBRL companyfacts
  (`sec_fundamentals_history.py`) — usa il campo `filed` come marcatore PIT.
- **Pre-market**: yfinance prepost + arricchimento volume via endpoint Nasdaq.

**Protezioni** (`data_source_metrics.py`, `probes.py`, `breaker_state.py`):
circuit breaker per-fonte **persistente tra restart** (`breakers.json`),
rate-limiter client-side, budget giornaliero soft, probe di reachability con
elision intelligente. Tutto monitorato su `/health`.

### 3.5.3 Cache a due livelli

- **L1**: dict in-process (microsecondi), idratato all'avvio da L2.
- **L2**: tabella `fetch_cache` (una riga per `(ticker, kind)`, payload JSON),
  sopravvive ai restart. `stock_fundamentals_service` e `stock_news_service`
  seguono `L1 hit → L2 hit → upstream` con UPSERT su successo. Gli errori NON
  vengono persistiti (un fallimento transitorio non avvelena la cache 24h).

### 3.5.4 Live quote + pre-market

- `live_quote_service`: quote near-real-time (TTL 10s), batch **parallelizzato**
  (ThreadPool) per pool ampi; prev_close derivato dall'OHLCV per correggere i
  `previousClose` errati di yfinance. La dashboard polla i top-movers ogni 15s
  su un pool ampio (unione di tutte le liste mover) così nuovi mover possono
  emergere.
- `premarket_service`: top gainer/loser USA pre-market, warm-on-boot + job
  schedulato nella finestra PM; la card è visibile solo quando i dati sono freschi.

## 4. Modello dati

> **Nota stato (2026-05):** l'ERD Fase-1 sotto mostra il nucleo storico. Le
> **watchlist sono state rimosse** (tabelle `watchlists`/`watchlist_items`
> deprecate; lo screener `/stocks` + lo scoring le hanno rese superflue — le
> regole "Tier 2" per-watchlist non esistono più, restano solo le regole
> globali Tier 1). Tabelle **aggiunte** dopo la Fase 1, oltre a quelle in
> "Aggiunte Fase 2": `stock_scores` (composito + sub-score + breakdown JSON +
> risk_tier), `market_snapshot` (dashboard pre-computata), `fetch_cache` (L2
> payload cache), `scan_runs` (storico scan), `institutionals` +
> `institutional_filings` + `institutional_holdings` (13F), `macro_series` +
> `macro_observations` + `macro_release_dates` (FRED/calendario),
> `price_alerts`, `rule_states`. Il catalogo `stocks` ha duplicati noti per
> ~12 ticker (i read-path usano `.limit(1).scalars().first()` — vedi CLAUDE.md).

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

Single-user. Password admin generata via bcrypt cost 12, hash in `ADMIN_PASSWORD_HASH`
(locale: `.env` · **cloud: il Secret k8s `finance-alert-prod`**, che il chart
referenzia ma NON gestisce — ArgoCD renderizza da git, e materiale crittografico
in git è fuori discussione).

Cookie sessione: signed con `itsdangerous` usando `SECRET_KEY`. Payload: `{username, exp}`.
Attributi: `HttpOnly`, `SameSite=Strict`, e **`Secure` sse `APP_ENV != development`**
(`secure=not settings.is_dev`, unico consumatore di `is_dev` in tutto il backend).
In locale resta OFF di proposito: senza TLS un cookie Secure non tornerebbe mai
indietro e il login fallirebbe in silenzio. Sul cloud è **ON** da M4.

Throttling login: dopo N fallimenti consecutivi per username → 429 + Retry-After
(stato in-memory, si azzera al riavvio — accettabile per single-user/single-process).

### 7.2 CSRF

Difesa strutturale, niente token dedicato:

1. **`SameSite=Strict`** sul cookie sessione: il browser non lo invia su navigazioni cross-site
2. **`Content-Type: application/json` enforced** su POST/PATCH/DELETE: i form HTML cross-origin non possono inviare JSON

Per single-page same-origin questo è sufficiente.

### 7.3 Validazione input

Tutti i body sono Pydantic schemas. Query parameters sono typed via FastAPI. Nessuna concatenazione SQL — solo SQLAlchemy parametrizzato.

### 7.4 Secrets

Locale: tutti via `.env`, che è in `.gitignore`; `.env.example` ha solo i nomi
delle chiavi senza valori. Nessun secret hardcoded, mai.

Cloud: **Secret k8s, mai in git**. `finance-alert-prod` (SECRET_KEY +
ADMIN_PASSWORD_HASH + MARKETAUX_API_KEY) creato una volta sul cluster; `pg-app`
generato dall'operatore CloudNativePG (l'app lo consuma verbatim via
`secretKeyRef`, senza duplicare credenziali); `pg-wal-s3` (Customer Secret Key
OCI per il WAL). ⚠️ Un Secret k8s è **base64, non cifrato**: chi può leggere i
Secret del namespace legge le password. La difesa reale è che l'accesso al
cluster (:6443) è NSG-allowlistato al solo IP del proprietario.

### 7.5 Postura di sicurezza cloud (M4 + M7-P5)

| Layer | Cosa |
|---|---|
| **Rete** | NSG allowlista l'IP del proprietario su :22/:443/:6443. **:80 è aperta a 0.0.0.0/0** — necessaria per il challenge ACME (i validator Let's Encrypt hanno IP rotanti) e serve **solo quello**: app e Grafana sono `websecure`-only, quindi `http://<ip>/qualunque-cosa` → 404. ⚠️ **Ogni nuovo Ingress deve essere websecure-only, o è pubblico all'istante** (è già successo a Grafana). |
| **Trasporto** | TLS Let's Encrypt su `80-225-80-141.sslip.io`, rinnovo automatico via cert-manager. |
| **App↔DB** | TLS **imposto**: `pg_hba` = `hostssl … scram-sha-256` + `hostnossl … reject`. Provato: `sslmode=disable` → `FATAL … no encryption`. |
| **Privilegi DB** | L'app usa `fa_app`, **non-superuser** (no CREATEDB/CREATEROLE), owner del solo DB `finance_alert`. Il superuser Postgres non ha login esterno. |
| **Audit** | pgaudit `ddl,role` → log Postgres → Loki → Grafana. NON `write`: uno scan scrive milioni di righe ohlcv e allagherebbe il disco. |
| **Isolamento** | NetworkPolicy sui pod Postgres. ⚠️ Limite **misurato** di k3s/kube-router: i selettori pod/namespace non matchano il traffico via ClusterIP → l'app passa via `ipBlock` sul pod-CIDR. L'isolamento per-pod sul path del service richiederebbe Calico. |
| **Durabilità** | WAL continuo + base backup giornaliero → OCI Object Storage. **Restore verificato** (drill: cluster ricostruito dal solo bucket, dati identici al live). |
| **Patching** | `dnf-automatic` security-only, `reboot = never`. L'immagine OL arriva con un backlog: al primo audit c'erano **185 advisory pendenti, 6 Critical**. |

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
| 2026-05-22 | (docs) | **Documentazione aggiornata allo stato attuale.** README riscritto come "piattaforma di research/screening" (non più "watchlist editor"); ARCHITECTURE §1/§2/§3.5 aggiornate (scoring engine IC-validato, layer fonti dati multi-source con breaker persistenti, cache L1/L2, live-quote/pre-market); nota in §4 su watchlist rimosse + tabelle aggiunte (stock_scores, market_snapshot, fetch_cache, institutionals/13F, macro_*, scan_runs, price_alerts); `.env.example` con chiavi FRED/Finnhub/Marketaux + flag SCORE_ENGINE_XS; `docs/scoring-algorithm.md` riscritto a 6 pilastri + metodologia IC. |
| 2026-05 | (vari) | **Estensioni post-Fase-3** (sintesi): scoring engine 6-pilastri sector-aware con EWMA + risk overlay + retune momentum/profitability validati su IC point-in-time (harness `entry_ic_report.py`); fondamentali point-in-time da SEC companyfacts (`sec_fundamentals_history.py`); istituzionali/13F (SEC EDGAR) con pagine `/institutionals`; pre-market USA (`premarket_service` + card); calendario earnings+macro (FRED + Finnhub + ForexFactory); fonti dati Finnhub (earnings/news/upgrades/recommendations) + Marketaux (news fallback) con rate-limiter/quota-guard/circuit-breaker persistenti; cache a due livelli L1/L2; live-quote batch parallelizzato + polling top-movers su pool ampio; pagina Salute piattaforma `/health`; rimozione watchlist e SSE50. ~580 test. |
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
| 2026-05-02 | 9c9917b | Fase 3C indicatori avanzati + regole composite + Rule Editor UI: 4 nuovi indicatori (MACD, Bollinger, ATR, ADX in `app/indicators/`); 6 nuove regole atomiche (`volume_spike`, `breakout`, `macd_bullish_cross`, `macd_bearish_cross`, `bollinger_squeeze`, `bollinger_breakout`) registrate nel `RULES` registry; `Rule.expression` Text nullable (migration 4841a82d3387) per espressioni JSON ad albero AND/OR/atomic con max depth 5 / max 8 atomic; nuovo `app/rules/composite.py` (`evaluate_expression`, `snapshot_expression`, `validate_expression`) integrato in `scan_service` con backward-compat (legacy `kind`+`params` se `expression IS NULL`); endpoints `GET /api/rules/catalog` (10 kinds + label/description/default_params per UI builder) e `POST /api/rules/preview` (valuta expression contro un ticker, ritorna `{matched, snapshot}`). Frontend: nuova pagina `/rules` con 5 componenti rule editor (`RulesTable`, `RuleEditorDialog` modal, `ExpressionTree` recursive AND/OR builder, `AtomicConditionForm` con catalog-driven params, `ExpressionPreview` con test su ticker), hooks `useRuleCatalog` (5min cache) + `useRulePreview` (mutation); sidebar `Regole` attivata. `RuleKind` union espanso da 4 a 11 kinds. ~38 nuovi test backend (totale ~238 passing). |
