# Finance Alert

Local-first, single-user stock watchlist manager. A FastAPI backend serves a React SPA over a SQLite database; everything runs on the user's own machine, no cloud, no network exposure.

Phase 1 (current) ships the catalog browser and the watchlist editor. Phase 2 will add a technical-signal alert engine; Phase 3 will add a charts/statistics dashboard.

---

## Prerequisites

- **Python 3.11+**
- **Node.js 20+** (with `npm`)
- **[uv](https://docs.astral.sh/uv/)** — Python package manager (`winget install astral-sh.uv` on Windows)
- **[just](https://github.com/casey/just)** — task runner (`winget install Casey.Just` on Windows)
- **Git**

On Windows, the recipes work from **PowerShell** or **cmd** out of the box (the `justfile` declares `set windows-shell := ["cmd.exe", "/C"]`). The `just up` recipe uses platform-specific recipe attributes (`[unix]` / `[windows]`) so it works on both.

---

## First-time setup

```bash
# 1. Clone
git clone <your-remote> finance-alert
cd finance-alert

# 2. Copy the env template into backend/ (where pydantic-settings reads it)
#    Linux/macOS/Git Bash:    cp .env.example backend/.env
#    Windows PowerShell:      Copy-Item .env.example backend/.env

# 3. Install backend + frontend deps and bootstrap the DB
#    (runs alembic upgrade head, generates SECRET_KEY if empty,
#     seeds the 4 indices and ~79 stocks)
just install

# 4. Set the admin password — the script hashes it, writes it to
#    backend/.env, AND creates/updates the user in the DB in one go
just set-password

# 5. Start the dev servers (backend :8000, frontend :5173)
just up
```

Open <http://localhost:5173> and log in with `admin` / the password you just set.

---

## Daily development

| Recipe              | What it does                                                         |
| ------------------- | -------------------------------------------------------------------- |
| `just be`           | Run backend with `--reload` on port 8000                             |
| `just fe`           | Run Vite dev server on port 5173 (proxies `/api` → 8000)             |
| `just up`           | Run backend + frontend together (cross-platform via `[unix]`/`[windows]` recipes) |
| `just test`         | `pytest` (backend) + `vitest --run` (frontend)                       |
| `just lint`         | `ruff check` + `pyright` (backend) + `eslint` (frontend)             |
| `just fmt`          | `ruff format` (backend) + `prettier` (frontend)                      |
| `just migrate "msg"`| Autogenerate a new Alembic revision                                  |
| `just migrate-apply`| `alembic upgrade head`                                               |
| `just seed`         | Re-run the catalog seed (idempotent)                                 |

The bootstrap script (`just install` calls it) is idempotent: re-running it is safe.

---

## Production-local mode

A single uvicorn process serves both the API and the built React assets — same origin, SPA fallback, no Vite dev server.

```bash
just prod-local
```

Equivalent to:

```bash
cd frontend && npm run build
cd ../backend && uv run uvicorn app.main:app --port 8000
```

Then open <http://localhost:8000>.

---

## Windows auto-start (optional)

Schedule the app to launch at user logon via Windows Task Scheduler. Scripts live in `scripts/windows/` and do **not** require admin privileges.

```powershell
# Register the scheduled task (creates "Finance Alert" in Task Scheduler)
powershell -ExecutionPolicy Bypass -File scripts\windows\Register-FinanceAlertStartup.ps1

# Remove it
powershell -ExecutionPolicy Bypass -File scripts\windows\Unregister-FinanceAlertStartup.ps1
```

`Run-FinanceAlert.ps1` is what the task invokes; it boots `prod-local` with rotated logs into `backend/data/logs/`.

---

## Updating

```bash
git pull
just install        # re-syncs deps and runs bootstrap
just migrate-apply  # apply any new Alembic revisions
```

`just install` is safe to re-run on every pull.

---

## Project layout

```
finance-alert/
├── backend/                  # FastAPI app
│   ├── app/
│   │   ├── api/              # routers: auth, catalog, stocks, watchlists
│   │   ├── core/             # config, db, logging, security, sessions
│   │   ├── models/           # SQLAlchemy models
│   │   ├── schemas/          # Pydantic schemas
│   │   ├── services/         # business logic (auth, seed, stocks, watchlists, refresh)
│   │   ├── scheduler/        # APScheduler jobs (weekly Wikipedia refresh)
│   │   ├── scripts/          # bootstrap, seed, set_admin_password
│   │   ├── data/             # bundled seed CSV
│   │   └── main.py           # FastAPI app + lifespan
│   ├── alembic/              # migrations
│   ├── tests/                # pytest suite (48 tests)
│   └── data/                 # SQLite DB + logs (gitignored)
├── frontend/                 # React + Vite SPA
│   └── src/
│       ├── pages/            # routes
│       ├── components/       # UI (shadcn/ui based)
│       ├── hooks/            # autosave, query hooks
│       ├── api/              # typed fetch client
│       └── lib/              # helpers
├── docs/
│   ├── ARCHITECTURE.md       # living technical reference
│   └── superpowers/
│       ├── specs/            # design spec
│       └── plans/            # implementation plan
├── scripts/windows/          # PowerShell scripts (auto-start)
├── justfile                  # task runner recipes
└── .env.example              # environment template
```

---

## Tech stack

**Backend**

- Python 3.11+, FastAPI, uvicorn
- SQLAlchemy 2.0 + Alembic
- SQLite (WAL mode)
- APScheduler (in-process cron)
- pydantic-settings, loguru
- pandas + lxml (Wikipedia HTML scraping)
- bcrypt + itsdangerous (auth + signed cookie sessions)
- pytest, ruff, pyright

**Frontend**

- React 18 + TypeScript
- Vite
- TailwindCSS + shadcn/ui
- TanStack Query
- React Router
- React Hook Form + Zod
- vitest, eslint, prettier

**Tooling**: `uv`, `just`.

---

## Documentation

- [Design spec](docs/superpowers/specs/2026-04-30-finance-alert-fase1-design.md) — what we're building and why
- [Implementation plan](docs/superpowers/plans/2026-04-30-finance-alert-fase1.md) — task breakdown for Phase 1
- [Architecture reference](docs/ARCHITECTURE.md) — living technical doc, updated on every merge that touches architecture/data model/dependencies

---

## Roadmap

- **Phase 1 (done)** — Catalog + watchlist editor. Auth, models, API, autosave UI, weekly Wikipedia refresh, prod-local mode, Windows auto-start.
- **Phase 2** — Alert engine: configurable technical signals (e.g. crossings, threshold breaks) evaluated on a schedule with on-screen + system notifications.
- **Phase 3** — Dashboard: per-watchlist statistics, candle/line charts (Recharts + lightweight-charts), historical-quote ingestion.

---

## License / personal-use note

This is a personal, single-user, local-first project. No license is granted for redistribution; no warranty is provided. Run it on your own machine at your own risk.
