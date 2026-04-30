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
| Dashboard Home con KPI | Fase 3 |
| Pagina Stock Detail con grafico candlestick | Fase 3 |
| Statistiche hit rate | Fase 3 |
| Backtest | Post-MVP |
| Email/webhook notifiche | Post-MVP |
| Import/export watchlist | Post-MVP |
| Multi-utente | Non previsto |
| Deploy su OCI | Post-MVP |

**In scope Fase 1**: scheduler APScheduler con un job attivo (refresh catalogo settimanale, vedi §6.2); esecuzione background su Windows via Task Scheduler (vedi §12.5).

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
| Scheduler | APScheduler | 3.x |
| HTML scraping (catalog refresh) | pandas (`read_html`) + lxml | latest |
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

In esecuzione "produzione locale" (un processo, eventualmente lanciato da Windows Task Scheduler al logon):

```
┌────────────────────────────────────────────┐
│ uvicorn :8000                              │
│ FastAPI                                    │
│ ├── /api/* → router                        │
│ └── /*     → StaticFiles(frontend/dist)    │
│ APScheduler                                │
│ └── refresh_catalog (weekly, Sat 03:00)    │
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
| market_cap | BIGINT NULL | popolato dal seed se presente nel CSV; non aggiornato dal refresh Wikipedia (la fonte non lo include consistentemente) |
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

### 5.7 `catalog_refresh_log`

Tracking del job di refresh catalogo (vedi §6.2).

| Campo | Tipo | Note |
|---|---|---|
| id | INTEGER PK | |
| index_code | TEXT NOT NULL | "SP500", "NDX", "DJI", "FTSEMIB" |
| started_at | TIMESTAMP NOT NULL | |
| completed_at | TIMESTAMP NULL | NULL se fallito |
| status | TEXT NOT NULL | "success" \| "failed" |
| stocks_added | INTEGER NULL | |
| stocks_updated | INTEGER NULL | |
| stocks_removed | INTEGER NULL | dalla membership dell'indice |
| error_message | TEXT NULL | |

## 6. Seed e refresh catalogo

### 6.1 Seed iniziale (bootstrap)

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

I CSV iniziali sono uno snapshot scaricato manualmente da Wikipedia. Servono come fallback offline e per il primo bootstrap senza rete.

### 6.2 Refresh periodico (in Fase 1)

Job APScheduler `refresh_catalog`:

- **Trigger**: cron settimanale, sabato 03:00 ora locale (mercati chiusi, traffico ridotto)
- **Strategia**: per ogni indice, fetch della pagina Wikipedia tramite `pandas.read_html(url)`, parsing della tabella dei constituenti, upsert delle righe in `stocks` e ricostruzione della membership in `stock_indices`. Tracking dell'esito per indice in `catalog_refresh_log`.
- **Fonti**:
  - S&P 500: `https://en.wikipedia.org/wiki/List_of_S%26P_500_companies`
  - NASDAQ-100: `https://en.wikipedia.org/wiki/Nasdaq-100`
  - Dow Jones: `https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average`
  - FTSE MIB: `https://en.wikipedia.org/wiki/FTSE_MIB`
- **Resilienza**:
  - Fallimento di un indice non blocca gli altri.
  - Retry con backoff esponenziale (3 tentativi, 30s/2min/8min).
  - Timeout 30s per richiesta.
  - User-Agent identificato (rispetto delle policy Wikipedia).
  - Se la struttura della tabella cambia (parsing fallisce), logga error e marca `status=failed` per quell'indice; i dati esistenti restano intatti.
- **Trigger manuale**: endpoint `POST /api/catalog/refresh` (auth richiesta) avvia il job ad-hoc.
- **Stato visibile**: endpoint `GET /api/catalog/status` ritorna ultimo refresh per indice (timestamp, status, conteggi). In Fase 1 nessuna pagina UI lo consuma; sarà aggiunta in Fase 3.

## 7. API surface (Fase 1)

Tutti gli endpoint sotto prefisso `/api`. Risposte JSON. OpenAPI auto-generato disponibile in dev su `/api/docs`, disabilitato se `APP_ENV=production`.

### 7.1 Auth

| Method | Path | Body | Risposta |
|---|---|---|---|
| POST | `/api/auth/login` | `{username, password}` | 200 + Set-Cookie session; 401 se invalid |
| POST | `/api/auth/logout` | — | 204, cookie scaduto |
| GET | `/api/auth/me` | — | `{username}` se loggato, 401 altrimenti |

Cookie: `httpOnly`, `SameSite=Strict`, `Secure=false` in dev (no HTTPS local). Scadenza 7 giorni con sliding refresh. Vedi §12 per il modello CSRF.

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

### 7.4 Catalog

| Method | Path | Body | Risposta |
|---|---|---|---|
| POST | `/api/catalog/refresh` | `{index_code?: string}` | 202 Accepted, job avviato in background; se `index_code` omesso, refresha tutti |
| GET | `/api/catalog/status` | — | Per ogni indice: ultimo refresh, status, conteggi, ultimo errore se presente |

### 7.5 Health

| Method | Path | Risposta |
|---|---|---|
| GET | `/api/health` | `{status: "ok", db_ok: bool, scheduler_running: bool, version: string}` |

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
- Input nome watchlist (autosave debounced)
- Textarea descrizione opzionale (autosave debounced)
- Tabella stock contenuti con: ticker, nome, exchange, settore, X per rimuovere (rimozione immediata)
- Indicatore stato salvataggio in alto a destra: "Salvataggio…" → "Salvato" (ultima ora) — fade out dopo 2s
- Bottone secondario "Elimina watchlist" (solo in edit, con conferma modale)

**Modello autosave**:
- **Campi testo (nome, descrizione)**: debounce 500ms dopo l'ultimo keystroke; al primo trigger valido in modalità *create*, l'API crea la watchlist e l'URL viene riscritto con `replaceState` da `/watchlists/new` a `/watchlists/:id`. Da quel momento i salvataggi sono PATCH.
- **Aggiunta stock**: POST immediato a `/api/watchlists/{id}/items` non appena l'utente clicca "+ aggiungi". In modalità create senza watchlist ancora persistita, l'azione forza prima la creazione (richiede nome non vuoto; se nome vuoto, mostra hint "Inserisci un nome per iniziare").
- **Rimozione stock**: DELETE immediato.
- **Rete down / errore**: l'indicatore mostra "Errore di salvataggio" in rosso con bottone "Riprova"; lo stato locale non viene perso fino a successo.
- **Validazione nome**: vuoto = no save; duplicato = errore inline. Min 1 char, max 100.

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
│   │   │   ├── watchlist_service.py
│   │   │   └── catalog_refresh_service.py
│   │   ├── core/
│   │   │   ├── config.py              # pydantic-settings
│   │   │   ├── db.py                  # engine, session, Base
│   │   │   ├── security.py            # bcrypt, signed cookies
│   │   │   └── logging.py             # loguru config
│   │   ├── scheduler/
│   │   │   ├── __init__.py            # APScheduler setup
│   │   │   └── jobs/
│   │   │       ├── __init__.py
│   │   │       └── refresh_catalog.py
│   │   ├── data/
│   │   │   └── seed/
│   │   │       ├── sp500.csv
│   │   │       ├── nasdaq100.csv
│   │   │       ├── djia.csv
│   │   │       └── ftsemib.csv
│   │   └── scripts/
│   │       ├── seed.py
│   │       ├── bootstrap.py
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
├── scripts/
│   └── windows/
│       ├── Register-FinanceAlertStartup.ps1
│       ├── Unregister-FinanceAlertStartup.ps1
│       └── Run-FinanceAlert.ps1
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

# avvia entrambi in parallelo (Git Bash su Windows: `&` backgrounda il primo)
# In alternativa: aprire due terminali e lanciare `just be` in uno e `just fe` nell'altro
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
- Session cookie: signed con `SECRET_KEY`, `httpOnly`, **`SameSite=Strict`**, `Secure=false` in dev.
- **CSRF**: difesa strutturale combinando due meccanismi:
  1. `SameSite=Strict` impedisce al browser di inviare il cookie di sessione su navigazioni cross-site (anche da link/form esterni).
  2. Tutte le mutating routes (POST/PATCH/DELETE) richiedono `Content-Type: application/json` ed un body JSON. I form HTML cross-origin non possono inviare JSON, eliminando il vettore CSRF classico.

  Niente token CSRF dedicato: il modello del browser già garantisce la protezione per un single-page same-origin con session cookie strict.
- Validazione input: Pydantic sui body, query parameter typed.
- SQL injection: solo SQLAlchemy parametrizzato, mai stringhe concatenate.
- Nessun secret in codice; tutto via `.env`.
- `.env` in `.gitignore`, `.env.example` no.

## 12.5 Esecuzione background su Windows

Strategia: registrare un task in **Windows Task Scheduler** che lancia l'app al logon dell'utente.

### 12.5.1 `Run-FinanceAlert.ps1`

Wrapper che:
1. Si sposta nella cartella del progetto.
2. Attiva l'environment Python (`uv run`) e lancia `uvicorn app.main:app --port 8000` (modalità prod-local con frontend buildato).
3. Reindirizza stdout/stderr a `backend/data/logs/windows-task.log` con rotazione semplice via PowerShell (rinomina + nuovo file se >10 MB).

Lo script è invocato senza finestra visibile (`-WindowStyle Hidden`).

### 12.5.2 `Register-FinanceAlertStartup.ps1`

Crea un'entry in Task Scheduler:

```powershell
Register-ScheduledTask `
  -TaskName "FinanceAlert" `
  -Description "Avvia l'app Finance Alert al logon utente" `
  -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME) `
  -Action (New-ScheduledTaskAction `
            -Execute "powershell.exe" `
            -Argument "-WindowStyle Hidden -File `"$PSScriptRoot\Run-FinanceAlert.ps1`"") `
  -Settings (New-ScheduledTaskSettingsSet `
              -AllowStartIfOnBatteries `
              -DontStopIfGoingOnBatteries `
              -RestartOnIdle `
              -RestartCount 3 `
              -RestartInterval (New-TimeSpan -Minutes 1))
```

Caratteristiche:

- **Nessun privilegio admin richiesto** (esegue come utente loggato).
- Sopravvive al riavvio: parte automaticamente al logon successivo.
- Restart automatico (3 tentativi) in caso di crash dell'app.
- Funziona anche con laptop a batteria.

### 12.5.3 `Unregister-FinanceAlertStartup.ps1`

Rimuove il task: `Unregister-ScheduledTask -TaskName "FinanceAlert" -Confirm:$false`.

### 12.5.4 Workflow utente

```powershell
# Setup iniziale (una volta)
just install
just build-fe
.\scripts\windows\Register-FinanceAlertStartup.ps1

# Verifica avvio
Start-Process "http://localhost:8000"

# Per disattivare in futuro
.\scripts\windows\Unregister-FinanceAlertStartup.ps1
```

### 12.5.5 Verifica stato

L'utente può controllare lo stato del task con:

```powershell
Get-ScheduledTask -TaskName "FinanceAlert" | Get-ScheduledTaskInfo
```

Oppure aprire `taskschd.msc` e cercare "FinanceAlert" nella libreria.

### 12.5.6 Out of scope per Fase 1

- Servizio Windows true (con NSSM o `sc.exe`): richiede privilegi admin, non necessario.
- Notifiche di "app non disponibile" se il task crasha: ci si affida a Task Scheduler restart policy.
- Aggiornamento automatico dell'app via `git pull` allo startup: post-MVP.

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
# edita ADMIN_PASSWORD_HASH (generato con script utility)
just install
just up
```

Apre `http://localhost:5173`, fa login, crea una watchlist "Tech USA" filtrando per exchange=NASDAQ + settore=Information Technology, vede il conteggio anteprima (~30 stock), aggiunge gli stock — l'indicatore segna "Salvato" pochi istanti dopo. Ricarica la pagina, la watchlist è lì con tutti gli item.

Ferma il backend, lo riavvia: tutto persistito.

Lancia `just prod-local`, apre `http://localhost:8000`, stessa esperienza con frontend statico buildato.

Esegue `.\scripts\windows\Register-FinanceAlertStartup.ps1` da PowerShell, riavvia Windows, dopo il logon l'app è già attiva su `localhost:8000` senza terminali aperti.

Triggers manualmente `POST /api/catalog/refresh` (via Swagger UI in dev), il job parte; `GET /api/catalog/status` ritorna timestamp e conteggi non-zero per ogni indice.

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
- UI per stato refresh catalogo (consumo `/api/catalog/status`)

## 16. Assunzioni esplicite

1. **NASDAQ = NASDAQ-100**, non Composite. Documentato in §6.
2. **Catalogo stock**: bootstrap iniziale da CSV statici committati; refresh settimanale automatico da Wikipedia attivo da Fase 1 (vedi §6.2).
3. **Single-user**: l'app non gestisce più di un account; il modello dati lo permetterebbe ma l'UI e gli endpoint assumono l'unico admin.
4. **Niente HTTPS in locale**: cookie con `Secure=false`. Quando/se si farà deploy, `Secure=true` via env.
5. **Salvataggio watchlist autosave real-time** con debounce 500ms su testo, immediato su add/remove stock (vedi §8.5).
6. **Lingua UI**: italiano hard-coded; nessuna libreria i18n in Fase 1.
7. **Windows 11 host**: comandi `just` cross-platform; gli script di startup (`scripts/windows/*.ps1`) sono Windows-specifici.
8. **Esecuzione background Windows**: in scope Fase 1 via Task Scheduler con script PowerShell (vedi §12.5).
9. **OCI deploy**: completamente fuori scope per Fase 1. Il `Dockerfile` viene scritto come artefatto futuro.
10. **Wikipedia come fonte**: dipendenza accettata per il refresh settimanale; fallback graceful documentato in §6.2 e §17.

## 17. Rischi e mitigazioni

| Rischio | Mitigazione |
|---|---|
| Wikipedia cambia struttura HTML delle tabelle constituenti | Parsing tollerante (cerca colonne per nome, non per indice); fallimento di un indice non blocca gli altri; CSV statici come fallback offline; log + endpoint status per visibilità |
| Wikipedia rate-limit o blocca scraping | Retry con backoff esponenziale; User-Agent identificato; frequenza settimanale ben sotto soglia |
| Performance ricerca stock con many-to-many indici | Indici DB su colonne filtro; pagination obbligatoria; limit max 500 risultati |
| Frontend bundle size con tutte le icone shadcn | Tree-shaking di lucide-react via import nominali; verifica con `npm run build -- --report` |
| Alembic autogenerate manca colonne con SQLite (tipi flessibili) | Test che applica migrations da zero in pytest fixture |
| Cookie session non funziona cross-port in dev (5173 vs 8000) | Vite proxy `/api → :8000` rende same-origin lato browser |
| Autosave race condition (utente digita più veloce della rete) | Debounce 500ms + AbortController sulla request precedente quando arriva una nuova; ultima vince |
| Task Scheduler Windows non lancia l'app (PATH, working dir) | Script `Run-FinanceAlert.ps1` imposta `Set-Location` esplicito; log dedicato in `windows-task.log` per debug |
