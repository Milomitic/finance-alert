# Finance Alert — Fase 1 Design

**Data**: 2026-04-30
**Stato**: Approvato in brainstorming, in attesa review utente
**Scope**: Solo Fase 1 (MVP "watchlist viewer"). Fasi 2 e 3 elencate in fondo per contesto, non in scope qui.

---

## 1. Obiettivo della Fase 1

Consegnare un'applicazione web full-stack eseguibile localmente sul PC dell'utente, con cui sia possibile:

1. Effettuare login (utente singolo).
2. Consultare un catalogo di stock pre-seedato (S&P 500, NASDAQ-100, Dow Jones, FTSE MIB).
3. Cercare e filtrare stock per ticker, nome, exchange, settore, indice di appartenenza, paese.
4. Creare, modificare, eliminare watchlist nominate, popolandole tramite ricerca singola o filtri combinati.
5. Persistere tutto in un database SQLite locale che sopravvive al riavvio dell'app.

**La Fase 1 non recupera dati di mercato, non calcola indicatori, non emette alert.** Quelli sono Fase 2.

## 2. Vincoli e principi guida

- **Local-first**: l'app gira sul PC dell'utente (Windows 11). Nessun cloud, nessuna esposizione di rete oltre il `localhost`. Notifiche e fetch dati sono Fase 2.
- **Single-user**: nessuna multi-tenancy, un solo account amministratore configurato via `.env`.
- **Stack minimale**: niente Redis, Celery, Postgres. SQLite + APScheduler + FastAPI + React.
- **Container-ready ma non container-required**: il `Dockerfile` viene scritto in Fase 1 come artefatto futuro, ma lo sviluppo e l'esecuzione "produzione" locali non richiedono Docker.
- **Lingua**: codice, identifier, commenti, log, OpenAPI in inglese; testi UI rivolti all'utente in italiano hard-coded (no libreria i18n).

## 3. Cosa è esplicitamente fuori scope per Fase 1

| Funzionalità | Fase prevista |
|---|---|
| Fetch dati OHLCV (yfinance) | Fase 2 |
| Cache dati di mercato | Fase 2 |
| Calcolo indicatori tecnici | Fase 2 |
| Regole di alert | Fase 2 |
| Notifiche Telegram | Fase 2 |
| Scheduler APScheduler attivo | Fase 2 (skeleton in Fase 1, no job registrati) |
| Dashboard Home con KPI | Fase 3 |
| Pagina Stock Detail con grafico candlestick | Fase 3 |
| Statistiche hit rate | Fase 3 |
| Backtest | Post-MVP |
| Email/webhook notifiche | Post-MVP |
| Import/export watchlist | Post-MVP |
| Multi-utente | Non previsto |
| Deploy su OCI | Post-MVP |

## 4. Architettura tecnica

### 4.1 Stack

| Layer | Scelta | Versione |
|---|---|---|
| Backend runtime | Python | 3.11+ |
| Framework API | FastAPI | latest stabile |
| ORM | SQLAlchemy | 2.0+ |
| Migrations | Alembic | latest |
| Settings | pydantic-settings | latest |
| Logging | loguru | latest |
| Scheduler (skeleton) | APScheduler | 3.x |
| Auth | itsdangerous (signed cookie) + bcrypt (passlib) | latest |
| Test backend | pytest, pytest-asyncio, httpx | latest |
| Lint/format Python | ruff | latest |
| Type check Python | pyright | latest |
| Package manager Python | uv | latest |
| Frontend runtime | Node.js | 20 LTS |
| Framework UI | React | 18+ |
| Bundler | Vite | 5+ |
| Linguaggio | TypeScript | 5+ |
| Styling | Tailwind CSS | 3+ |
| Component library | shadcn/ui | latest |
| State/data fetching | TanStack Query | 5+ |
| Routing | React Router | 6+ |
| Form | React Hook Form + Zod | latest |
| Test frontend | Vitest + Testing Library | latest |
| Lint frontend | ESLint + Prettier | latest |
| Task runner cross-platform | just | latest |

### 4.2 Topologia esecuzione

In sviluppo (due processi):

```
┌──────────────────────────┐    ┌──────────────────────────┐
│ uvicorn :8000            │    │ vite dev :5173           │
│ FastAPI + APScheduler    │←───│ proxy /api → :8000       │
│ SQLite ./backend/data    │    │ React SPA con HMR        │
└──────────────────────────┘    └──────────────────────────┘
                  ↑                          ↑
                  └────────browser──────────┘
                       localhost:5173
```

In esecuzione "produzione locale" (un processo):

```
┌────────────────────────────────────────────┐
│ uvicorn :8000                              │
│ FastAPI                                    │
│ ├── /api/* → router                        │
│ └── /*     → StaticFiles(frontend/dist)    │
│ APScheduler (skeleton, no jobs in Fase 1)  │
│ SQLite ./backend/data/app.db               │
└────────────────────────────────────────────┘
                       ↑
                    browser
                  localhost:8000
```

## 5. Modello dati (Fase 1)

Solo tabelle necessarie alla Fase 1. Schema in inglese.

### 5.1 `users`

| Campo | Tipo | Note |
|---|---|---|
| id | INTEGER PK | |
| username | TEXT UNIQUE NOT NULL | |
| password_hash | TEXT NOT NULL | bcrypt |
| created_at | TIMESTAMP | default now |

In Fase 1 c'è esattamente UNA riga, seedata da `.env` (`ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH`) tramite uno script di bootstrap idempotente.

### 5.2 `stocks`

| Campo | Tipo | Note |
|---|---|---|
| id | INTEGER PK | |
| ticker | TEXT NOT NULL | es. "AAPL" |
| exchange | TEXT NOT NULL | "NASDAQ", "NYSE", "BIT" (Borsa Italiana) |
| name | TEXT NOT NULL | "Apple Inc." |
| sector | TEXT NULL | "Information Technology" |
| industry | TEXT NULL | "Consumer Electronics" |
| country | TEXT NULL | "US", "IT" |
| currency | TEXT NULL | "USD", "EUR" |
| market_cap | BIGINT NULL | snapshot al seed; aggiornato in Fase 3 |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

Indice unico su `(ticker, exchange)`. Indici secondari su `exchange`, `sector`, `country`.

### 5.3 `indices`

| Campo | Tipo | Note |
|---|---|---|
| id | INTEGER PK | |
| code | TEXT UNIQUE NOT NULL | "SP500", "NDX", "DJI", "FTSEMIB" |
| name | TEXT NOT NULL | "S&P 500" |
| country | TEXT | "US", "IT" |

### 5.4 `stock_indices` (membership many-to-many)

| Campo | Tipo |
|---|---|
| stock_id | INTEGER FK → stocks.id |
| index_id | INTEGER FK → indices.id |

PK composta. Indici su entrambi i campi.

### 5.5 `watchlists`

| Campo | Tipo | Note |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT UNIQUE NOT NULL | |
| description | TEXT NULL | |
| user_id | INTEGER FK → users.id | sempre l'unico admin in Fase 1 |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

### 5.6 `watchlist_items`

| Campo | Tipo |
|---|---|
| watchlist_id | INTEGER FK → watchlists.id ON DELETE CASCADE |
| stock_id | INTEGER FK → stocks.id |
| added_at | TIMESTAMP |

PK composta `(watchlist_id, stock_id)`.

## 6. Seed catalog

Quattro CSV statici in `backend/app/data/seed/`, committati nel repo:

- `sp500.csv` — ~500 ticker (NYSE/NASDAQ)
- `nasdaq100.csv` — ~100 ticker (NASDAQ)
- `djia.csv` — 30 ticker (NYSE/NASDAQ)
- `ftsemib.csv` — ~40 ticker (Borsa Italiana, suffisso `.MI`)

**Assunzione**: "NASDAQ" nello scope si riferisce a NASDAQ-100, non NASDAQ Composite (~3000 ticker, overlap massiccio con S&P 500, troppo rumoroso per Fase 1).

Schema CSV:

```csv
ticker,name,exchange,sector,industry,country,currency
AAPL,Apple Inc.,NASDAQ,Information Technology,Consumer Electronics,US,USD
```

Script di seed idempotente (`uv run python -m app.scripts.seed`):

1. Legge i quattro CSV.
2. Upsert in `stocks` per `(ticker, exchange)`.
3. Upsert in `indices` con i codici fissi.
4. Ricostruisce `stock_indices` membership.
5. Logga conteggi: stocks totali, per indice, nuovi vs aggiornati.

L'esecuzione del seed è parte di `just install`. Re-eseguibile a piacere senza danni.

**Sorgente CSV**: per la Fase 1 i CSV sono committati statici (snapshot scaricato manualmente, es. da Wikipedia/SlickCharts). L'aggiornamento programmatico via job è Fase 3.

## 7. API surface (Fase 1)

Tutti gli endpoint sotto prefisso `/api`. Risposte JSON. OpenAPI auto-generato disponibile in dev su `/api/docs`, disabilitato se `APP_ENV=production`.

### 7.1 Auth

| Method | Path | Body | Risposta |
|---|---|---|---|
| POST | `/api/auth/login` | `{username, password}` | 200 + Set-Cookie session; 401 se invalid |
| POST | `/api/auth/logout` | — | 204, cookie scaduto |
| GET | `/api/auth/me` | — | `{username}` se loggato, 401 altrimenti |

Cookie: `httpOnly`, `SameSite=Lax`, `Secure=false` in dev (no HTTPS local). Scadenza 7 giorni con sliding refresh.

### 7.2 Stocks

| Method | Path | Query | Risposta |
|---|---|---|---|
| GET | `/api/stocks/search` | `q`, `exchange[]`, `sector[]`, `country[]`, `index[]`, `limit` (default 50, max 500) | Lista paginata con totale |
| GET | `/api/stocks/{ticker}` | — | Dettaglio singolo stock |
| GET | `/api/stocks/filters` | — | Valori distinti per popolare i select UI: `{exchanges, sectors, countries, indices}` |

La ricerca testuale `q` matcha case-insensitive su `ticker` (prefix) e `name` (substring).

### 7.3 Watchlists

| Method | Path | Body | Risposta |
|---|---|---|---|
| GET | `/api/watchlists` | — | Lista con conteggio item per ognuna |
| POST | `/api/watchlists` | `{name, description?, stock_ids?[]}` | 201 watchlist creata |
| GET | `/api/watchlists/{id}` | — | Dettaglio con elenco stock completo |
| PATCH | `/api/watchlists/{id}` | `{name?, description?}` | 200 |
| DELETE | `/api/watchlists/{id}` | — | 204 |
| POST | `/api/watchlists/{id}/items` | `{stock_ids: number[]}` | aggiunge item, 200 con count |
| DELETE | `/api/watchlists/{id}/items/{stock_id}` | — | 204 |
| POST | `/api/watchlists/{id}/items/bulk-delete` | `{stock_ids: number[]}` | 200 |

Tutti gli endpoint richiedono autenticazione tranne `/api/auth/login` e `/api/health`.

### 7.4 Health

| Method | Path | Risposta |
|---|---|---|
| GET | `/api/health` | `{status: "ok", db_ok: bool, version: string}` |

## 8. Frontend (Fase 1)

### 8.1 Routing

```
/login              → LoginPage
/                   → redirect → /watchlists
/watchlists         → WatchlistListPage (lista watchlist)
/watchlists/:id     → WatchlistDetailPage (modifica + costruzione selezione)
/watchlists/new     → WatchlistDetailPage (modalità create)
*                   → 404
```

Una rotta protetta richiede sessione: se non autenticato → redirect a `/login`.

### 8.2 Layout

- Sidebar sinistra fissa con voci: "Watchlists" (sola attiva in Fase 1; "Dashboard", "Stocks", "Alerts", "Rules", "Settings" presenti come placeholder disabilitati con tooltip "disponibile nelle prossime fasi").
- Header con username e bottone logout.
- Area contenuto principale.

### 8.3 LoginPage

Form `username` + `password`, button "Accedi". Errori in italiano. Su success → `/watchlists`.

### 8.4 WatchlistListPage

Tabella con colonne: nome, descrizione, conteggio stock, ultimo aggiornamento, azioni (apri, elimina). Bottone "Nuova watchlist" → `/watchlists/new`.

Empty state: card centrale con CTA "Crea la tua prima watchlist".

### 8.5 WatchlistDetailPage

Layout a due colonne:

**Colonna sinistra — pannello selezione stock**
- Tab "Ricerca singola": input con autocomplete (debounced 300ms) → risultati con chip "+ aggiungi"
- Tab "Filtri combinati":
  - Multiselect: Exchange, Settore, Paese, Indice
  - Anteprima live: "247 stock selezionati"
  - Bottone "Aggiungi tutti i selezionati"

**Colonna destra — watchlist corrente**
- Input nome watchlist
- Textarea descrizione (opzionale)
- Tabella stock contenuti con: ticker, nome, exchange, settore, X per rimuovere
- Bottone in basso "Salva" (in modalità create) o salvataggio implicito on-blur (in modalità edit) — **decisione: salvataggio esplicito con bottone in entrambe le modalità per rendere il flusso chiaro**.
- Bottone secondario "Elimina watchlist" (solo in edit, con conferma modale).

## 9. Configurazione

### 9.1 `.env.example`

```
APP_ENV=development
DATABASE_URL=sqlite:///./data/app.db
SECRET_KEY=
SESSION_COOKIE_NAME=finance_alert_session
SESSION_MAX_AGE_DAYS=7
LOG_LEVEL=INFO
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=
PUBLIC_BASE_URL=http://localhost:8000
```

### 9.2 Generazione credenziali

Comando utility:

```
uv run python -m app.scripts.set_admin_password
```

Prompt interattivo: chiede password, genera hash bcrypt, lo stampa così che l'utente lo incolli in `.env`. Non scrive direttamente il file (più sicuro, evita che password finisca nei log della shell history).

`SECRET_KEY` viene generato automaticamente al primo `just install` se assente in `.env`.

## 10. Struttura repo (post Fase 1)

```
finance-alert/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app, mounts API + StaticFiles
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── deps.py                # auth deps, db session
│   │   │   ├── auth.py
│   │   │   ├── stocks.py
│   │   │   ├── watchlists.py
│   │   │   └── health.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── base.py                # SQLAlchemy declarative base
│   │   │   ├── user.py
│   │   │   ├── stock.py
│   │   │   ├── index.py
│   │   │   └── watchlist.py
│   │   ├── schemas/
│   │   │   ├── auth.py
│   │   │   ├── stock.py
│   │   │   └── watchlist.py
│   │   ├── services/
│   │   │   ├── auth_service.py
│   │   │   ├── stock_service.py
│   │   │   └── watchlist_service.py
│   │   ├── core/
│   │   │   ├── config.py              # pydantic-settings
│   │   │   ├── db.py                  # engine, session, Base
│   │   │   ├── security.py            # bcrypt, signed cookies
│   │   │   └── logging.py             # loguru config
│   │   ├── scheduler/
│   │   │   └── __init__.py            # APScheduler skeleton, no jobs in Fase 1
│   │   ├── data/
│   │   │   └── seed/
│   │   │       ├── sp500.csv
│   │   │       ├── nasdaq100.csv
│   │   │       ├── djia.csv
│   │   │       └── ftsemib.csv
│   │   └── scripts/
│   │       ├── seed.py
│   │       └── set_admin_password.py
│   ├── alembic/
│   │   ├── versions/
│   │   └── env.py
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_auth.py
│   │   ├── test_stocks.py
│   │   └── test_watchlists.py
│   ├── data/                          # SQLite file (gitignored)
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── .python-version
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── pages/
│   │   │   ├── LoginPage.tsx
│   │   │   ├── WatchlistListPage.tsx
│   │   │   └── WatchlistDetailPage.tsx
│   │   ├── components/
│   │   │   ├── Layout.tsx
│   │   │   ├── ProtectedRoute.tsx
│   │   │   └── ui/                    # shadcn components generati
│   │   ├── hooks/
│   │   │   ├── useAuth.ts
│   │   │   ├── useStocks.ts
│   │   │   └── useWatchlists.ts
│   │   ├── api/
│   │   │   └── client.ts              # fetch wrapper tipizzato
│   │   └── lib/
│   │       └── utils.ts
│   ├── tests/
│   │   └── pages/
│   ├── public/
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   ├── package.json
│   └── .nvmrc
├── docs/
│   └── superpowers/specs/
│       └── 2026-04-30-finance-alert-fase1-design.md
├── docker-compose.yml                 # solo per future deploy
├── justfile
├── .env.example
├── .gitignore
└── README.md
```

## 11. Tooling, build, comandi

### 11.1 `justfile`

```
# install dipendenze + setup iniziale
install:
    cd backend && uv sync
    cd frontend && npm ci
    just _bootstrap

_bootstrap:
    cd backend && uv run python -m app.scripts.bootstrap

# avvia backend in dev
be:
    cd backend && uv run uvicorn app.main:app --reload --port 8000

# avvia frontend in dev
fe:
    cd frontend && npm run dev

# avvia entrambi in parallelo (richiede `just` con feature `parallel`, oppure due terminali)
up:
    just be & just fe

# build frontend statico per esecuzione "produzione locale"
build-fe:
    cd frontend && npm run build

# avvia solo backend con frontend buildato statico servito da FastAPI
prod-local: build-fe
    cd backend && uv run uvicorn app.main:app --port 8000

# test
test:
    cd backend && uv run pytest
    cd frontend && npm test -- --run

# lint
lint:
    cd backend && uv run ruff check . && uv run pyright
    cd frontend && npm run lint

# format
fmt:
    cd backend && uv run ruff format .
    cd frontend && npm run format

# migrazioni alembic
migrate msg:
    cd backend && uv run alembic revision --autogenerate -m "{{msg}}"

migrate-apply:
    cd backend && uv run alembic upgrade head

# seed catalogo stock
seed:
    cd backend && uv run python -m app.scripts.seed
```

### 11.2 Quality gates Fase 1

Una feature è "fatta" quando:

1. `just test` passa
2. `just lint` passa (ruff senza warning, pyright senza errori, eslint pulito)
3. La feature è esercitata manualmente nel browser
4. Le migration Alembic sono generate e committate
5. Il README riflette eventuali nuovi step

## 12. Sicurezza

- Password admin: bcrypt con cost 12.
- Session cookie: signed con `SECRET_KEY`, `httpOnly`, `SameSite=Lax`.
- CSRF: tutte le richieste mutanti (POST/PATCH/DELETE) richiedono header `X-Requested-With: XMLHttpRequest` (semplice ma efficace per single-page same-origin).
- Validazione input: Pydantic sui body, query parameter typed.
- SQL injection: solo SQLAlchemy parametrizzato, mai stringhe concatenate.
- Nessun secret in codice; tutto via `.env`.
- `.env` in `.gitignore`, `.env.example` no.

## 13. Logging

`loguru` configurato con:
- Output console in dev (formato leggibile)
- File rotato `backend/data/logs/app.log` (10 MB rotation, 7 giorni retention)
- Livello configurabile via `LOG_LEVEL`
- Request middleware FastAPI logga method, path, status, durata ms

In Fase 1 nessuna UI per i log; lettura via filesystem o tail.

## 14. Definition of Done — Fase 1

L'utente, partendo da repo clonato, esegue:

```bash
cp .env.example .env
# edita ADMIN_PASSWORD_HASH (generato con just bootstrap o utility)
just install
just up
```

Apre `http://localhost:5173`, fa login, crea una watchlist "Tech USA" filtrando per exchange=NASDAQ + settore=Information Technology, vede il conteggio anteprima (~30 stock), salva, ricarica la pagina, la watchlist è ancora lì con gli stessi item.

Ferma il backend, lo riavvia: tutto persistito.

Lancia `just prod-local`, apre `http://localhost:8000`, stessa esperienza con frontend statico buildato.

Tutti i quality gates passanti.

## 15. Future fasi (riferimento, non in scope qui)

### Fase 2 — Alert engine
- Fetcher yfinance + cache OHLCV (timeframe 1d)
- APScheduler con job giornaliero post-chiusura
- Indicatori SMA/EMA/RSI hand-rolled in `app/indicators/`
- Modelli `Rule`, `Alert`, regole RSI oversold/overbought + Golden/Death cross
- Notifier Telegram con cooldown anti-spam
- Pagina Alerts (tabella filtrabile)

### Fase 3 — Dashboard & analytics
- Home con KPI cards + feed live SSE
- Pagina Stock Detail con candlestick + overlay indicatori (lightweight-charts)
- Statistiche hit rate
- Timeframe 1h, regole MACD/BB/volume spike/breakout
- Editor regole UI con AND/OR
- Aggiornamento programmatico catalogo stock (job settimanale)

## 16. Assunzioni esplicite

1. **NASDAQ = NASDAQ-100**, non Composite. Documentato in §6.
2. **Catalogo stock** è uno snapshot statico committato in repo per Fase 1; nessun aggiornamento programmatico finché Fase 3.
3. **Single-user**: l'app non gestisce più di un account; il modello dati lo permetterebbe ma l'UI e gli endpoint assumono l'unico admin.
4. **Niente HTTPS in locale**: cookie con `Secure=false`. Quando/se si farà deploy, `Secure=true` via env.
5. **Salvataggio watchlist con bottone esplicito** (no autosave on-blur), per chiarezza di flusso.
6. **Lingua UI**: italiano hard-coded; nessuna libreria i18n in Fase 1.
7. **Windows 11 host**: comandi `just` cross-platform; nessun comando shell-specifico nel codice.
8. **Esecuzione background Windows**: fuori scope. L'utente lancia da terminale; quando chiude, l'app si ferma. Operazionalizzare via Task Scheduler è post-MVP.
9. **OCI deploy**: completamente fuori scope per Fase 1. Il `Dockerfile` viene scritto come artefatto futuro.

## 17. Rischi e mitigazioni

| Rischio | Mitigazione |
|---|---|
| Snapshot CSV catalogo invecchia rapidamente (IPO, delisting) | Documentato come limite; aggiornamento in Fase 3 |
| Performance ricerca stock con many-to-many indici | Indici DB su colonne filtro; pagination obbligatoria; limit max 500 risultati |
| Frontend bundle size con tutte le icone shadcn | Tree-shaking di lucide-react via import nominali; verifica con `npm run build -- --report` |
| Alembic autogenerate manca colonne con SQLite (tipi flessibili) | Test che applica migrations da zero in pytest fixture |
| Cookie session non funziona cross-port in dev (5173 vs 8000) | Vite proxy `/api → :8000` rende same-origin lato browser |
