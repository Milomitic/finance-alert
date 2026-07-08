# Finance Alert

**Local-first, single-user equity research & screening platform.** A FastAPI
backend serves a React SPA over a SQLite database; everything runs on your own
machine — no cloud, no network exposure (beyond the optional outbound calls to
free market-data providers).

What started as a catalog + watchlist tool is now a full personal
**market-intelligence platform**: it ingests ~1,000 global stocks nightly and
looks at each one through **three independent lenses** — fundamental **Qualità**,
price-action **Tecnico**, and a 17-detector **signal engine** whose alerts carry
an honest Forza + Probabilità pair and get their **realized outcomes** tracked
in a warehouse. Around that core: top picks & movers, **superinvestor 13F
tracking** (with quarter-over-quarter deltas), pre-market movers, an earnings +
macro **calendar**, **sector** drill-downs, **position tracking** with live P&L
and stop/target hits, and **Telegram** notifications — all behind a single
login on your LAN.

---

## What it does

| Area | Highlights |
|---|---|
| **Dashboard** (`/`) | Market-mood hero, per-index breadth matrix, live top-movers (15s polling, market-hours aware), top-volume, RSI histogram, sector heatmap, 52-week/vol stats, US pre-market card, score-based top picks, superinvestor consensus, latest analyst actions. Cards render progressively as their data arrives |
| **Scoring** | Three orthogonal lenses: **Qualità** (5-pillar fundamental composite), **Tecnico** (price-action posture), **Segnali** (17 detectors). Risk tiers, EWMA smoothing, turnover control. Every score-affecting change is gated behind a statistical study — see "The three lenses" below |
| **Screener** (`/stocks`) | Filter/sort ~30 dimensions (score & pillars, tech posture, RSI/EMA/52w/volume EOD metrics, index, sector, ETF toggle), saved filter presets, "N fondi" 13F badge, metrics as-of hint, column manager |
| **Segnali** (`/alerts`) | The 17-detector signal feed: each alert carries **Forza** (pattern strength) + **Probabilità** (detector base rate), a confirmation chain (Catena), confluence clusters, an **Esito** column with the realized outcome once the horizon matures, earnings-proximity badge, trade playbook, CSV export |
| **Posizioni** (`/positions`) | "Track this trade" from any playbook: entry/stop/target persisted, live P&L, automatic stop/target hit detection (intraday sweep + EOD) with Telegram notify |
| **Stock detail** (`/stocks/:ticker`) | Candlestick chart (lightweight-charts) with adaptive indicators (SMA/EMA/RSI/MACD/BB), multi-timeframe (5m→monthly), fundamentals with current-FY estimate row, valuation, analyst targets + actions, insider transactions, institutional holders, news |
| **Institutionals** (`/institutionals`) | Superinvestor (Dataroma) + fund/hedge-fund 13F portfolios (SEC EDGAR) with quarter-over-quarter deltas (new/add/reduce/sold-out), per-stock holders, filed-date honesty labels, allocation infographics |
| **Esplora** (`/sectors`) | Per-sector aggregates (11 GICS sectors), industry rollups, constituent drill-down |
| **Calendar** (`/calendar`) | Upcoming earnings (with EPS/revenue estimates + post-release surprise) and macro releases (FRED + ForexFactory consensus) |
| **Market detail** (`/markets/:symbol`) | Indices, commodities, crypto with live quotes + charts |
| **Salute** (`/health`) | Live status of every external data source, scheduler jobs, circuit-breaker state, live log stream, signal-drift monitor, detector-performance explorer (live + 10y-replay segments) |

---

## Prerequisites

- **Python 3.11+**
- **Node.js 20+** (with `npm`)
- **[uv](https://docs.astral.sh/uv/)** — Python package manager (`winget install astral-sh.uv`)
- **[just](https://github.com/casey/just)** — task runner (`winget install Casey.Just`)
- **Git**

On Windows the recipes run from **PowerShell** or **cmd** (the `justfile`
declares `set windows-shell := ["cmd.exe", "/C"]`). The `just up` recipe uses
`[unix]` / `[windows]` attributes so it works on both.

---

## First-time setup

```bash
# 1. Clone
git clone <your-remote> finance-alert
cd finance-alert

# 2. Copy the env template into backend/ (where pydantic-settings reads it)
#    Git Bash / Linux / macOS:  cp .env.example backend/.env
#    Windows PowerShell:        Copy-Item .env.example backend/.env

# 3. Install backend + frontend deps and bootstrap the DB
#    (alembic upgrade head, generate SECRET_KEY if empty, seed indices + stocks)
just install

# 4. Set the admin password (hashes it, writes to backend/.env, upserts the DB user)
just set-password

# 5. Start the dev servers (backend :8000, frontend :5173)
just up
```

Open <http://localhost:5173> and log in with `admin` / your password.

> **First scan** backfills ~10 years of OHLCV for the whole catalog (~10-20 min
> via yfinance batch download) and computes the first scores. Subsequent nightly
> scans fetch incrementally (seconds of network, ~1-2 min total). The first run
> may emit many "initial-state" alerts — bulk-archive them in `/alerts`. If the
> machine was off at scan time, a **boot catch-up** runs the missed scan (and
> stale institutional refreshes) automatically at the next backend start.

---

## Configuration

All settings live in `backend/.env` (template: [`.env.example`](.env.example)).
**Every external data source is optional** — the app degrades gracefully when a
key is missing (the feature that needs it simply shows "n/d" or falls back to
another source).

| Variable | Required | Purpose |
|---|---|---|
| `SECRET_KEY` | auto-generated | Signs the session cookie |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD_HASH` | yes (via `just set-password`) | Single-user login |
| `FRED_API_KEY` | optional | Macro series (CPI, unemployment, rates…) — free from [FRED](https://fred.stlouisfed.org/docs/api/api_key.html) |
| `FINNHUB_API_KEY` | optional | Earnings actuals + company news + analyst upgrade/downgrade + recommendation trends — free from [Finnhub](https://finnhub.io) (60 req/min) |
| `MARKETAUX_API_KEY` | optional | News fallback (100 req/day free; quota-guarded + circuit-broken) |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | optional | Enables all Telegram surfaces: daily digest, instant price-alert + position-close pushes |
| `TELEGRAM_PUSH_PER_SIGNAL` | default `false` | Opt-in instant push of strong signals at scan end |
| `TELEGRAM_PUSH_MIN_STRENGTH` | default `75` | Min Forza for the per-signal push |
| `SCAN_HOUR` / `SCAN_MINUTE` | default 23:30 | Nightly scan time (Europe/Rome) |
| `DIGEST_HOUR` / `DIGEST_MINUTE` | default 08:00 | Telegram digest time |

**Feature flags (environment):**

- `SCORE_ENGINE_XS=1` enables the cross-sectional (sector-relative) scoring
  engine. **Left OFF by default** — IC validation showed sector-neutralisation
  degrades the predictive signal on this universe (see scoring docs).

### Telegram setup (optional)

1. `@BotFather` → `/newbot` → get a `BOT_TOKEN`.
2. Open the chat with your bot, send `/start`.
3. `curl https://api.telegram.org/bot<BOT_TOKEN>/getUpdates` → read `result[0].message.chat.id`.
4. Set `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` in `backend/.env`, restart, click
   "Invia digest ora" in `/alerts` to test.

---

## Data sources

The app is **multi-source with graceful fallback** — no single provider is a hard
dependency. Each source is monitored on `/health` (success rate, rate-limit usage,
circuit-breaker state).

| Source | Used for | Limit / protection |
|---|---|---|
| **yfinance** (Yahoo) | Primary: OHLCV, fundamentals, live quotes, news, market cap | No documented limit; protected by a local circuit breaker |
| **Finnhub** | Earnings actuals + company news + analyst upgrade/downgrade + recommendation buckets (fallbacks when yfinance is stale/empty) | 60 req/min; client-side rate-limiter (30/min organic) + 5-min breaker |
| **Marketaux** | News fallback (last resort, after yfinance + Finnhub) | 100/day; 12h per-ticker cache + soft 85/day budget + UTC-midnight breaker |
| **SEC EDGAR** | 13F institutional filings (latest + 5-quarter history, put/call rows excluded, CUSIP→ticker via company_tickers.json with a persistent map); **point-in-time fundamentals** via XBRL companyfacts (for backtesting/score validation) | Polite ~6 req/s; persistent breaker |
| **Dataroma** | ~80 curated superinvestor portfolios (pre-computed Q/Q actions) | HTML scrape, weekly + boot catch-up |
| **FRED** | Macro series for the calendar | 120 req/min |
| **ForexFactory** | Macro consensus (expected values) | XML weekly; 6h on-disk fallback cache |
| **Nasdaq** (unofficial) | Pre-market volume enrichment | Best-effort, US pre-market window only |

Circuit-breaker state persists across restarts (`backend/data/breakers.json`), so a
tripped breaker isn't blanked by a reload.

---

## The three lenses

Every stock is evaluated through **three deliberately independent lenses** —
none of them nudges another:

**1 · Qualità** — a fundamental composite 0-100 from five pillars
(Profitability · Sustainability · Growth · Value · Sentiment), each 0-100 with
missing-data renormalization and sector-aware benchmarking. Stocks get a
**risk tier** (conservative / moderate / aggressive); scores are EWMA-smoothed
with tier hysteresis to control churn. *(The former Momentum pillar was removed
in the 2026-05 redesign: price action belongs to the Tecnico lens.)*

**2 · Tecnico** — a continuous price-action posture score (trend, momentum,
structure, volume, relative strength) recomputed at every scan. Owns
everything price-derived.

**3 · Segnali** — 17 detectors (volume breakout, trend+pullback, RSI/MACD
divergences, squeeze expansion, 52-week momentum, gap-and-go, PEAD, insider
buys…). Each alert carries two first-class numbers: **Forza** (weighted
pattern strength with a soft-min anti-mediocrity cap) and **Probabilità**
(the detector's historical hit-rate from a 10-year, no-look-ahead replay of
~250k signals — honestly labeled as a base rate, not a per-signal prediction).
Once an alert's horizon elapses, its **realized outcome** (absolute +
market-neutral) lands in the `signal_outcomes` warehouse and surfaces in the
UI as the Esito column and the detector-performance explorer.

**Honesty gates.** No score-affecting change ships without a statistical study
— and three of the four gates run so far returned **negatives** that shaped
the product: confirmation counts don't predict outcomes (so they're
display-only), no Qualità pillar shows significant IC on forward returns (so
the composite is a quality *descriptor*, not an alpha claim, and is never
reweighted on alpha grounds), and per-factor Probabilità adjustments failed
out-of-sample validation (so Probabilità stays a per-detector base rate).
The studies live in `app/scripts/` (`signal_detector_outcomes`,
`score_ic_backtest`, `fit_signal_calibration`) and their verdicts are recorded
in [CLAUDE.md](CLAUDE.md). Full detail:
[docs/scoring-algorithm.md](docs/scoring-algorithm.md).

---

## Daily development

| Recipe | What it does |
|---|---|
| `just be` | Backend with `--reload` on :8000 |
| `just fe` | Vite dev server on :5173 (proxies `/api` → :8000) |
| `just up` | Backend + frontend together |
| `just test` | `pytest` (backend, ~1,200 tests, network-guarded) + `vitest --run` (frontend) |
| `just lint` | `ruff check` + `pyright` + `eslint` |
| `just fmt` | `ruff format` + `prettier` |
| `just migrate "msg"` | Autogenerate an Alembic revision |
| `just migrate-apply` | `alembic upgrade head` |
| `just seed` | Re-run the catalog seed (idempotent) |
| `just prod-local` | Build the SPA + serve everything from one uvicorn on :8000 |

`just install` is idempotent — safe to re-run on every pull.

> **Windows note:** `uvicorn --reload` can miss file-change events; after a backend
> edit, restart it explicitly. FastAPI on :8000 serves a **pre-built** `frontend/dist`
> — rebuild (`cd frontend && npm run build`) after frontend changes before testing
> on :8000. See [CLAUDE.md](CLAUDE.md) for the full operational playbook.

---

## Production-local mode

A single uvicorn process serves the API **and** the built React assets (same origin,
SPA fallback, no Vite dev server):

```bash
just prod-local         # = cd frontend && npm run build ; cd ../backend && uv run uvicorn app.main:app --port 8000
```

Then open <http://localhost:8000>.

### LAN access (e.g. from your phone)

Bind to all interfaces and reach the dashboard from another device on the same Wi-Fi:

```bash
cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
# → http://<your-LAN-IP>:8000  (find it with `ipconfig` / `ip addr`)
```

`0.0.0.0` listens on every local interface but stays behind your router's NAT — it
is **not** exposed to the internet without explicit port-forwarding. You may need to
allow Python through the Windows Firewall on Private networks the first time.

---

## Windows auto-start (optional)

Launch the app at logon via Task Scheduler (no admin needed). Scripts in
`scripts/windows/`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\Register-FinanceAlertStartup.ps1    # register
powershell -ExecutionPolicy Bypass -File scripts\windows\Unregister-FinanceAlertStartup.ps1  # remove
```

`Run-FinanceAlert.ps1` boots `prod-local` with rotated logs into `backend/data/logs/`.

---

## Updating

```bash
git pull
just install        # re-syncs deps + bootstrap
just migrate-apply  # apply new Alembic revisions
```

---

## Project layout

```
finance-alert/
├── backend/                         # FastAPI app
│   ├── app/
│   │   ├── api/                     # routers: auth, dashboard, stocks, scores,
│   │   │                            #   institutionals, sectors, calendar, market,
│   │   │                            #   alerts, positions, price_alerts, platform_health…
│   │   ├── core/                    # config, db, logging, security, persist_json
│   │   ├── indicators/              # ema, sma, rsi, macd, bb, atr, adx
│   │   ├── models/                  # SQLAlchemy models
│   │   ├── schemas/                 # Pydantic schemas
│   │   ├── signals/                 # the 17 detectors + runner, chain enrichment,
│   │   │                            #   calibration_map (Forza/Probabilità)
│   │   ├── services/                # ~60 modules: score_service/ (package),
│   │   │                            #   technical_score_service, signal_outcome_service,
│   │   │                            #   market_stats_service, stock_fundamentals_service,
│   │   │                            #   live_quote_service, institutional_service,
│   │   │                            #   position_service, currency_units, ohlcv_fetch_plan…
│   │   ├── scheduler/jobs/          # APScheduler: scan_alerts, send_digest, db_backup,
│   │   │                            #   retention, refresh_catalog/fred/institutionals/
│   │   │                            #   sec_13f/premarket, live_movers_sweep, probes…
│   │   ├── scripts/                 # bootstrap, seed, set_admin_password + the
│   │   │                            #   statistical gates: signal_detector_outcomes,
│   │   │                            #   score_ic_backtest, fit_signal_calibration,
│   │   │                            #   backfill_replay_outcomes, backfill_13f_history
│   │   ├── data/seed/               # bundled index-constituent CSVs
│   │   └── main.py                  # FastAPI app + lifespan (cache hydrate, scheduler)
│   ├── alembic/versions/            # migrations
│   ├── tests/                       # pytest suite (~1,200 tests)
│   └── data/                        # SQLite DB, logs, runtime state (gitignored)
├── frontend/                        # React 19 + Vite SPA
│   └── src/
│       ├── pages/                   # routes (Home, Stocks, StockDetail, Sectors,
│       │                            #   Institutionals, Calendar, Market, Alerts, Health…)
│       ├── components/dashboard/    # dashboard cards (movers, breadth, premarket, picks…)
│       ├── components/stock/        # stock-detail cards (chart, fundamentals, analysts…)
│       ├── components/ui/           # shadcn/ui primitives + shared (CardSkeleton, FlashValue…)
│       ├── hooks/                   # TanStack Query hooks, live-quote polling, price-flash
│       ├── api/                     # typed fetch client + response types
│       └── lib/                     # formatters, meta maps, helpers
├── docs/                            # ARCHITECTURE.md, scoring-algorithm.md, calendar-page.md
├── scripts/windows/                 # PowerShell auto-start
├── justfile                         # task runner
├── CLAUDE.md                        # operational playbook + accumulated gotchas
└── .env.example                     # environment template
```

---

## Tech stack

**Backend** — Python 3.11+ · FastAPI · uvicorn · SQLAlchemy 2.0 + Alembic ·
SQLite (WAL) · APScheduler · pydantic-settings · loguru · pandas/numpy ·
yfinance · requests/httpx · bcrypt + itsdangerous · pytest · ruff · pyright

**Frontend** — React 19 + TypeScript · Vite 8 · TailwindCSS + shadcn/ui ·
TanStack Query 5 · React Router · React Hook Form + Zod · lightweight-charts ·
Recharts · vitest · eslint · prettier

**Tooling** — `uv`, `just`.

---

## Testing

```bash
just test                                   # backend + frontend
cd backend && uv run pytest tests/ -x -q    # backend only (~1,200 tests, ~25s)
cd frontend && npm run build                # type-check + production build
```

The backend suite runs with an **anti-network guard** (any accidental real
HTTP raises) and a per-test circuit-breaker reset — tests are deterministic
and offline by construction.

---

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — living technical reference (data
  model, flows, caching, scheduler, scoring engine internals)
- [docs/scoring-algorithm.md](docs/scoring-algorithm.md) — the Qualità composite (5 pillars),
  per-pillar formulas, and the IC-validation methodology
- [docs/calendar-page.md](docs/calendar-page.md) — earnings + macro calendar design
- [CLAUDE.md](CLAUDE.md) — operational playbook (backend restart discipline, dist
  rebuild rules, known data quirks)

---

## License / personal-use note

Personal, single-user, local-first project. No license is granted for
redistribution; no warranty is provided. Market data is fetched from third-party
providers under their respective free-tier terms — respect their rate limits. Run
it on your own machine at your own risk; nothing here is investment advice.
