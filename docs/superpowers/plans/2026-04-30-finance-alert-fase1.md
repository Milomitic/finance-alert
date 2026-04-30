# Finance Alert — Fase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-first single-user web app to manage stock watchlists over a seeded catalog (S&P 500, NASDAQ-100, DJIA, FTSE MIB), with weekly Wikipedia-driven catalog refresh and Windows auto-start at logon.

**Architecture:** FastAPI + SQLAlchemy 2.0 + SQLite + APScheduler (single backend process); React + Vite + TypeScript + shadcn/ui (frontend, served as static dist by FastAPI in prod-local). Cookie session auth (`SameSite=Strict`). Autosave watchlists with debounce.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, Alembic, APScheduler, pandas (for `read_html`), pydantic-settings, loguru, bcrypt, itsdangerous, pytest. Node 20, React 18, Vite 5, TypeScript, TailwindCSS, shadcn/ui, TanStack Query, React Router, React Hook Form, Vitest, just, uv.

**Spec:** [docs/superpowers/specs/2026-04-30-finance-alert-fase1-design.md](../specs/2026-04-30-finance-alert-fase1-design.md)
**Architecture (living):** [docs/ARCHITECTURE.md](../../ARCHITECTURE.md)

---

## Conventions used in this plan

- Working directory in commands: project root `C:/Users/giuli/Documents/Progetti/finance-alert` unless stated. The plan uses POSIX paths (`backend/...`); Git Bash on Windows resolves them correctly.
- Commit messages use Conventional Commits (`feat:`, `fix:`, `chore:`, `test:`, `docs:`, `refactor:`).
- After each task that changes architecture/schema/endpoints/flows/deps/scheduler/security, also update `docs/ARCHITECTURE.md` in the same commit (per ARCHITECTURE.md §10).
- TDD discipline on backend logic and security-sensitive code. UI is verified by component-level smoke tests + manual checks (rather than full TDD).

---

## Section A — Project scaffolding

### Task A1: Initialize repo, gitignore, top-level files

**Files:**
- Create: `.gitignore`, `.env.example`, `README.md`, `justfile`

- [ ] **Step 1: Create `.gitignore`**

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
.pytest_cache/
.ruff_cache/
.mypy_cache/

# Node
node_modules/
frontend/dist/

# Local data
backend/data/*.db
backend/data/*.db-journal
backend/data/*.db-wal
backend/data/*.db-shm
backend/data/logs/

# Env
.env
.env.local

# IDE
.vscode/
.idea/
*.swp
.DS_Store

# OS
Thumbs.db
```

- [ ] **Step 2: Create `.env.example`**

```env
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

- [ ] **Step 3: Create `justfile`**

```just
default:
    @just --list

install:
    cd backend && uv sync
    cd frontend && npm ci
    just _bootstrap

_bootstrap:
    cd backend && uv run python -m app.scripts.bootstrap

be:
    cd backend && uv run uvicorn app.main:app --reload --port 8000

fe:
    cd frontend && npm run dev

up:
    just be & just fe

build-fe:
    cd frontend && npm run build

prod-local: build-fe
    cd backend && uv run uvicorn app.main:app --port 8000

test:
    cd backend && uv run pytest
    cd frontend && npm test -- --run

lint:
    cd backend && uv run ruff check . && uv run pyright
    cd frontend && npm run lint

fmt:
    cd backend && uv run ruff format .
    cd frontend && npm run format

migrate msg:
    cd backend && uv run alembic revision --autogenerate -m "{{msg}}"

migrate-apply:
    cd backend && uv run alembic upgrade head

seed:
    cd backend && uv run python -m app.scripts.seed
```

- [ ] **Step 4: Create initial `README.md`** (skeleton, expanded later)

```markdown
# Finance Alert

Local-first single-user stock watchlist manager.

## Setup

Prerequisites: Python 3.11+, Node 20+, [uv](https://docs.astral.sh/uv/), [just](https://github.com/casey/just).

```bash
cp .env.example .env
# Generate ADMIN_PASSWORD_HASH:
just install
just up
```

Open http://localhost:5173.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for technical reference.
```

- [ ] **Step 5: Commit**

```bash
git add .gitignore .env.example justfile README.md
git commit -m "chore: scaffold repo with gitignore, env example, justfile, readme"
```

---

### Task A2: Initialize Python backend project

**Files:**
- Create: `backend/pyproject.toml`, `backend/.python-version`, `backend/app/__init__.py`, `backend/app/main.py`

- [ ] **Step 1: Create `backend/.python-version`**

```
3.11
```

- [ ] **Step 2: Create `backend/pyproject.toml`**

```toml
[project]
name = "finance-alert-backend"
version = "0.1.0"
description = "Finance Alert backend"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "pydantic>=2.6",
    "pydantic-settings>=2.2",
    "loguru>=0.7",
    "apscheduler>=3.10",
    "bcrypt>=4.1",
    "itsdangerous>=2.1",
    "pandas>=2.2",
    "lxml>=5.1",
    "httpx>=0.27",
    "python-multipart>=0.0.9",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
    "pyright>=1.1",
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "N", "SIM"]

[tool.pyright]
include = ["app", "tests"]
typeCheckingMode = "standard"
pythonVersion = "3.11"

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 3: Create `backend/app/__init__.py`** (empty)

- [ ] **Step 4: Create minimal `backend/app/main.py`**

```python
"""FastAPI application entry point."""
from fastapi import FastAPI

app = FastAPI(title="Finance Alert", version="0.1.0")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 5: Run `cd backend && uv sync` to materialize the venv and lockfile**

Expected: creates `.venv/`, `uv.lock`. No errors.

- [ ] **Step 6: Smoke test the server**

```bash
cd backend && uv run uvicorn app.main:app --port 8000
```

In another terminal: `curl http://localhost:8000/api/health` → `{"status":"ok"}`. Stop server.

- [ ] **Step 7: Commit**

```bash
git add backend/
git commit -m "chore(backend): initialize FastAPI project with health endpoint"
```

---

### Task A3: Initialize React frontend project

**Files:**
- Create: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/.nvmrc`, `frontend/tailwind.config.js`, `frontend/postcss.config.js`, `frontend/src/index.css`

- [ ] **Step 1: Scaffold via Vite**

```bash
cd frontend
npm create vite@latest . -- --template react-ts
npm install
```

Accept overwriting if prompted. Result: standard Vite+React+TS template.

- [ ] **Step 2: Add `frontend/.nvmrc`**

```
20
```

- [ ] **Step 3: Install Tailwind + autoprefixer + postcss**

```bash
cd frontend
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

- [ ] **Step 4: Configure `frontend/tailwind.config.js`**

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: { extend: {} },
  plugins: [],
};
```

- [ ] **Step 5: Replace `frontend/src/index.css` with Tailwind directives**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 6: Configure Vite proxy in `frontend/vite.config.ts`**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
```

- [ ] **Step 7: Update `frontend/tsconfig.json`** — add path alias (merge into existing `compilerOptions`):

```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] }
  }
}
```

- [ ] **Step 8: Add testing dependencies**

```bash
cd frontend
npm install -D vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom
```

Add to `frontend/package.json` scripts:

```json
"scripts": {
  "dev": "vite",
  "build": "tsc -b && vite build",
  "lint": "eslint .",
  "format": "prettier --write src",
  "preview": "vite preview",
  "test": "vitest"
}
```

- [ ] **Step 9: Smoke test**

```bash
cd frontend && npm run dev
```

Open http://localhost:5173 → see Vite default page. Stop.

- [ ] **Step 10: Commit**

```bash
git add frontend/
git commit -m "chore(frontend): scaffold Vite+React+TS project with Tailwind and proxy"
```

---

## Section B — Database foundation

### Task B1: Configure pydantic-settings and DB engine

**Files:**
- Create: `backend/app/core/__init__.py`, `backend/app/core/config.py`, `backend/app/core/db.py`

- [ ] **Step 1: Create `backend/app/core/__init__.py`** (empty)

- [ ] **Step 2: Create `backend/app/core/config.py`**

```python
"""Application configuration loaded from environment / .env."""
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./data/app.db"
    secret_key: str = Field(default="")
    session_cookie_name: str = "finance_alert_session"
    session_max_age_days: int = 7
    log_level: str = "INFO"
    admin_username: str = "admin"
    admin_password_hash: str = ""
    public_base_url: str = "http://localhost:8000"

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"


settings = Settings()


def ensure_data_dir() -> None:
    """Make sure ./data and ./data/logs exist."""
    Path("./data").mkdir(parents=True, exist_ok=True)
    Path("./data/logs").mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 3: Create `backend/app/core/db.py`** with WAL setup

```python
"""SQLAlchemy engine, session, and Base."""
from collections.abc import Iterator
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record):
    if settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/
git commit -m "feat(backend): add settings and SQLAlchemy engine with SQLite WAL"
```

---

### Task B2: Define all SQLAlchemy models

**Files:**
- Create: `backend/app/models/__init__.py`, `backend/app/models/user.py`, `backend/app/models/stock.py`, `backend/app/models/index.py`, `backend/app/models/watchlist.py`, `backend/app/models/catalog_log.py`

- [ ] **Step 1: Create `backend/app/models/__init__.py`**

```python
"""Aggregate model imports so Alembic sees them."""
from app.models.catalog_log import CatalogRefreshLog
from app.models.index import Index, StockIndex
from app.models.stock import Stock
from app.models.user import User
from app.models.watchlist import Watchlist, WatchlistItem

__all__ = [
    "User",
    "Stock",
    "Index",
    "StockIndex",
    "Watchlist",
    "WatchlistItem",
    "CatalogRefreshLog",
]
```

- [ ] **Step 2: Create `backend/app/models/user.py`**

```python
"""User model — single-user admin in Fase 1."""
from datetime import datetime
from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 3: Create `backend/app/models/stock.py`**

```python
"""Stock model."""
from datetime import datetime
from sqlalchemy import BigInteger, DateTime, Index as SAIndex, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Stock(Base):
    __tablename__ = "stocks"
    __table_args__ = (
        UniqueConstraint("ticker", "exchange", name="uq_stocks_ticker_exchange"),
        SAIndex("ix_stocks_exchange", "exchange"),
        SAIndex("ix_stocks_sector", "sector"),
        SAIndex("ix_stocks_country", "country"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    market_cap: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

- [ ] **Step 4: Create `backend/app/models/index.py`**

```python
"""Index model + many-to-many membership table."""
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Index(Base):
    __tablename__ = "indices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    country: Mapped[str | None] = mapped_column(String(8), nullable=True)


class StockIndex(Base):
    __tablename__ = "stock_indices"

    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True
    )
    index_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("indices.id", ondelete="CASCADE"), primary_key=True
    )
```

- [ ] **Step 5: Create `backend/app/models/watchlist.py`**

```python
"""Watchlist + items models."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Watchlist(Base):
    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    watchlist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("watchlists.id", ondelete="CASCADE"), primary_key=True
    )
    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 6: Create `backend/app/models/catalog_log.py`**

```python
"""Catalog refresh audit log."""
from datetime import datetime
from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CatalogRefreshLog(Base):
    __tablename__ = "catalog_refresh_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    index_code: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    stocks_added: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stocks_updated: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stocks_removed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/
git commit -m "feat(backend): define all SQLAlchemy models for Fase 1"
```

---

### Task B3: Setup Alembic and create initial migration

**Files:**
- Create: `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`, `backend/alembic/versions/` (dir)

- [ ] **Step 1: Init Alembic**

```bash
cd backend && uv run alembic init alembic
```

- [ ] **Step 2: Edit `backend/alembic.ini` — set script location and DB URL stub**

Find and modify:

```ini
script_location = alembic
sqlalchemy.url =
```

(Empty `sqlalchemy.url`; we set it from settings in `env.py`.)

- [ ] **Step 3: Replace `backend/alembic/env.py`** with version that uses our settings

```python
"""Alembic environment configured for SQLAlchemy 2.0 + our settings."""
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.core.db import Base
import app.models  # noqa: F401  (register all models)

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

Note: `render_as_batch=True` is essential for SQLite to support ALTER TABLE.

- [ ] **Step 4: Generate the initial migration**

```bash
cd backend && mkdir -p data && uv run alembic revision --autogenerate -m "initial schema"
```

Open the generated file in `backend/alembic/versions/` and verify it creates: `users`, `stocks`, `indices`, `stock_indices`, `watchlists`, `watchlist_items`, `catalog_refresh_log`. Manual touch-ups if any column missed.

- [ ] **Step 5: Apply the migration**

```bash
cd backend && uv run alembic upgrade head
```

Expected: creates `data/app.db` with all tables.

- [ ] **Step 6: Verify schema**

```bash
cd backend && uv run python -c "from sqlalchemy import inspect; from app.core.db import engine; print(sorted(inspect(engine).get_table_names()))"
```

Expected: `['alembic_version', 'catalog_refresh_log', 'indices', 'stock_indices', 'stocks', 'users', 'watchlist_items', 'watchlists']`.

- [ ] **Step 7: Commit**

```bash
git add backend/alembic.ini backend/alembic/
git commit -m "feat(backend): setup Alembic with initial schema migration"
```

Update ARCHITECTURE.md changelog entry.

---

### Task B4: Test fixture for in-memory SQLite

**Files:**
- Create: `backend/tests/__init__.py`, `backend/tests/conftest.py`

- [ ] **Step 1: Create `backend/tests/__init__.py`** (empty)

- [ ] **Step 2: Create `backend/tests/conftest.py`**

```python
"""Pytest fixtures: isolated in-memory DB per test."""
from collections.abc import Iterator
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import Base
import app.models  # noqa: F401


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
```

- [ ] **Step 3: Add a smoke test in `backend/tests/test_smoke.py`**

```python
"""Sanity check: schema creates cleanly."""
from sqlalchemy.orm import Session

from app.models import Stock


def test_schema_smoke(db: Session) -> None:
    db.add(Stock(ticker="AAPL", exchange="NASDAQ", name="Apple Inc."))
    db.commit()
    rows = db.query(Stock).all()
    assert len(rows) == 1
    assert rows[0].ticker == "AAPL"
```

- [ ] **Step 4: Run tests**

```bash
cd backend && uv run pytest -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/
git commit -m "test(backend): add pytest fixtures and schema smoke test"
```

---

## Section C — Seed catalog

### Task C1: Add seed CSV files

**Files:**
- Create: `backend/app/data/seed/sp500.csv`, `nasdaq100.csv`, `djia.csv`, `ftsemib.csv`

- [ ] **Step 1: Download S&P 500 list**

Source the data manually (Wikipedia table, or SlickCharts CSV export). Create `backend/app/data/seed/sp500.csv` with header:

```csv
ticker,name,exchange,sector,industry,country,currency
AAPL,Apple Inc.,NASDAQ,Information Technology,Consumer Electronics,US,USD
MSFT,Microsoft Corporation,NASDAQ,Information Technology,Software,US,USD
...
```

(Populate with all ~500 rows. For development, even a 20-row subset is acceptable as initial bootstrap; the weekly refresh job will fill the rest.)

- [ ] **Step 2: Create `backend/app/data/seed/nasdaq100.csv`** with same columns and ~100 NASDAQ-100 constituents.

- [ ] **Step 3: Create `backend/app/data/seed/djia.csv`** with the 30 DJIA constituents.

- [ ] **Step 4: Create `backend/app/data/seed/ftsemib.csv`** with FTSE MIB constituents (exchange `BIT`, currency `EUR`, country `IT`, ticker suffix `.MI`).

Example row:

```csv
ENI.MI,Eni S.p.A.,BIT,Energy,Oil & Gas,IT,EUR
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/data/seed/
git commit -m "chore(backend): add seed CSVs for SP500, NASDAQ-100, DJIA, FTSE MIB"
```

---

### Task C2: Seed service with idempotent upsert (TDD)

**Files:**
- Create: `backend/app/services/__init__.py`, `backend/app/services/seed_service.py`, `backend/tests/test_seed_service.py`

- [ ] **Step 1: Create `backend/app/services/__init__.py`** (empty)

- [ ] **Step 2: Write failing test `backend/tests/test_seed_service.py`**

```python
"""Tests for seed service idempotent upsert."""
import io
from sqlalchemy.orm import Session

from app.models import Index, Stock, StockIndex
from app.services.seed_service import seed_index_from_csv

CSV_SAMPLE = """ticker,name,exchange,sector,industry,country,currency
AAPL,Apple Inc.,NASDAQ,Information Technology,Consumer Electronics,US,USD
MSFT,Microsoft Corporation,NASDAQ,Information Technology,Software,US,USD
"""


def test_seed_creates_stocks_and_membership(db: Session) -> None:
    result = seed_index_from_csv(db, io.StringIO(CSV_SAMPLE), index_code="NDX", index_name="Nasdaq-100", country="US")
    db.commit()

    assert result.added == 2
    assert result.updated == 0
    assert db.query(Stock).count() == 2
    assert db.query(Index).filter_by(code="NDX").one().name == "Nasdaq-100"
    assert db.query(StockIndex).count() == 2


def test_seed_is_idempotent(db: Session) -> None:
    seed_index_from_csv(db, io.StringIO(CSV_SAMPLE), index_code="NDX", index_name="Nasdaq-100", country="US")
    db.commit()
    result2 = seed_index_from_csv(db, io.StringIO(CSV_SAMPLE), index_code="NDX", index_name="Nasdaq-100", country="US")
    db.commit()

    assert result2.added == 0
    assert result2.updated == 2
    assert db.query(Stock).count() == 2
    assert db.query(StockIndex).count() == 2
```

- [ ] **Step 3: Run test, verify failure**

```bash
cd backend && uv run pytest tests/test_seed_service.py -v
```

Expected: ImportError.

- [ ] **Step 4: Implement `backend/app/services/seed_service.py`**

```python
"""Idempotent seeding of stocks and index membership from CSV."""
import csv
from dataclasses import dataclass
from typing import IO

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Index, Stock, StockIndex


@dataclass
class SeedResult:
    added: int
    updated: int


def _upsert_stock(db: Session, row: dict[str, str]) -> tuple[Stock, bool]:
    """Return (stock, created)."""
    stmt = select(Stock).where(Stock.ticker == row["ticker"], Stock.exchange == row["exchange"])
    stock = db.execute(stmt).scalar_one_or_none()
    if stock is None:
        stock = Stock(
            ticker=row["ticker"],
            exchange=row["exchange"],
            name=row["name"],
            sector=row.get("sector") or None,
            industry=row.get("industry") or None,
            country=row.get("country") or None,
            currency=row.get("currency") or None,
        )
        db.add(stock)
        db.flush()
        return stock, True
    stock.name = row["name"]
    stock.sector = row.get("sector") or stock.sector
    stock.industry = row.get("industry") or stock.industry
    stock.country = row.get("country") or stock.country
    stock.currency = row.get("currency") or stock.currency
    return stock, False


def _upsert_index(db: Session, code: str, name: str, country: str | None) -> Index:
    idx = db.execute(select(Index).where(Index.code == code)).scalar_one_or_none()
    if idx is None:
        idx = Index(code=code, name=name, country=country)
        db.add(idx)
        db.flush()
    else:
        idx.name = name
        idx.country = country
    return idx


def _ensure_membership(db: Session, stock_id: int, index_id: int) -> None:
    exists = db.execute(
        select(StockIndex).where(StockIndex.stock_id == stock_id, StockIndex.index_id == index_id)
    ).scalar_one_or_none()
    if exists is None:
        db.add(StockIndex(stock_id=stock_id, index_id=index_id))


def seed_index_from_csv(
    db: Session, csv_source: IO[str], *, index_code: str, index_name: str, country: str | None
) -> SeedResult:
    """Upsert stocks from CSV, ensure membership in the named index."""
    idx = _upsert_index(db, index_code, index_name, country)
    added = 0
    updated = 0
    reader = csv.DictReader(csv_source)
    for row in reader:
        _, created = _upsert_stock(db, row)
        added += int(created)
        updated += int(not created)
        # membership requires id; flush already done in _upsert_stock
        stock_id = db.execute(
            select(Stock.id).where(Stock.ticker == row["ticker"], Stock.exchange == row["exchange"])
        ).scalar_one()
        _ensure_membership(db, stock_id, idx.id)
    return SeedResult(added=added, updated=updated)
```

- [ ] **Step 5: Run test, verify pass**

```bash
cd backend && uv run pytest tests/test_seed_service.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/__init__.py backend/app/services/seed_service.py backend/tests/test_seed_service.py
git commit -m "feat(backend): add idempotent seed service with tests"
```

---

### Task C3: Bootstrap and seed scripts

**Files:**
- Create: `backend/app/scripts/__init__.py`, `backend/app/scripts/bootstrap.py`, `backend/app/scripts/seed.py`, `backend/app/scripts/set_admin_password.py`

- [ ] **Step 1: Create `backend/app/scripts/__init__.py`** (empty)

- [ ] **Step 2: Create `backend/app/scripts/seed.py`**

```python
"""Run all four index seeds against the configured DB."""
from pathlib import Path
from loguru import logger

from app.core.db import SessionLocal
from app.services.seed_service import seed_index_from_csv

SEEDS = [
    ("sp500.csv", "SP500", "S&P 500", "US"),
    ("nasdaq100.csv", "NDX", "Nasdaq-100", "US"),
    ("djia.csv", "DJI", "Dow Jones Industrial Average", "US"),
    ("ftsemib.csv", "FTSEMIB", "FTSE MIB", "IT"),
]

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"


def run() -> None:
    db = SessionLocal()
    try:
        for filename, code, name, country in SEEDS:
            path = SEED_DIR / filename
            if not path.exists():
                logger.warning(f"Seed file missing: {path}")
                continue
            with path.open(encoding="utf-8") as f:
                result = seed_index_from_csv(db, f, index_code=code, index_name=name, country=country)
            logger.info(f"{code}: added={result.added} updated={result.updated}")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    run()
```

- [ ] **Step 3: Create `backend/app/scripts/set_admin_password.py`**

```python
"""Generate a bcrypt hash to paste into ADMIN_PASSWORD_HASH."""
import getpass
import bcrypt


def main() -> None:
    pw = getpass.getpass("New admin password: ")
    pw2 = getpass.getpass("Confirm: ")
    if pw != pw2:
        raise SystemExit("Passwords do not match")
    if len(pw) < 8:
        raise SystemExit("Password must be at least 8 characters")
    hashed = bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
    print("\nPaste this into your .env as ADMIN_PASSWORD_HASH:\n")
    print(hashed)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Create `backend/app/scripts/bootstrap.py`**

```python
"""Idempotent first-run setup: ensure dirs, secret, migrations, seed, admin user."""
import secrets
from pathlib import Path
from loguru import logger
from sqlalchemy import select

from app.core.config import ensure_data_dir, settings
from app.core.db import SessionLocal
from app.models import User
from app.scripts import seed as seed_module


def ensure_secret_key() -> None:
    env_path = Path(".env")
    if not env_path.exists():
        logger.warning(".env file missing; copy .env.example first.")
        return
    text = env_path.read_text(encoding="utf-8")
    if "SECRET_KEY=" in text and "SECRET_KEY=\n" not in text and "SECRET_KEY=$" not in text:
        # already set (non-empty)
        for line in text.splitlines():
            if line.startswith("SECRET_KEY=") and line.split("=", 1)[1].strip():
                return
    new_key = secrets.token_urlsafe(48)
    new_text = []
    replaced = False
    for line in text.splitlines():
        if line.startswith("SECRET_KEY="):
            new_text.append(f"SECRET_KEY={new_key}")
            replaced = True
        else:
            new_text.append(line)
    if not replaced:
        new_text.append(f"SECRET_KEY={new_key}")
    env_path.write_text("\n".join(new_text) + "\n", encoding="utf-8")
    logger.info("Generated SECRET_KEY in .env")


def apply_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")


def ensure_admin_user() -> None:
    if not settings.admin_password_hash:
        logger.warning(
            "ADMIN_PASSWORD_HASH not set. Run: uv run python -m app.scripts.set_admin_password"
        )
        return
    db = SessionLocal()
    try:
        existing = db.execute(select(User).where(User.username == settings.admin_username)).scalar_one_or_none()
        if existing is None:
            db.add(User(username=settings.admin_username, password_hash=settings.admin_password_hash))
            db.commit()
            logger.info(f"Created admin user: {settings.admin_username}")
        elif existing.password_hash != settings.admin_password_hash:
            existing.password_hash = settings.admin_password_hash
            db.commit()
            logger.info(f"Updated admin password hash for: {settings.admin_username}")
    finally:
        db.close()


def main() -> None:
    ensure_data_dir()
    ensure_secret_key()
    apply_migrations()
    seed_module.run()
    ensure_admin_user()
    logger.info("Bootstrap complete.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run bootstrap end-to-end**

Generate password hash, paste into `.env`, then:

```bash
cd backend && uv run python -m app.scripts.bootstrap
```

Verify: `data/app.db` exists, contains seeded stocks, admin user.

- [ ] **Step 6: Commit**

```bash
git add backend/app/scripts/
git commit -m "feat(backend): add bootstrap, seed, and admin password scripts"
```

---

## Section D — Authentication

### Task D1: Security primitives (TDD)

**Files:**
- Create: `backend/app/core/security.py`, `backend/tests/test_security.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for password and session token primitives."""
import pytest

from app.core import security


def test_hash_and_verify_password() -> None:
    pw = "correct horse battery staple"
    h = security.hash_password(pw)
    assert security.verify_password(pw, h) is True
    assert security.verify_password("wrong", h) is False


def test_session_token_roundtrip() -> None:
    token = security.create_session_token("admin")
    assert security.read_session_token(token) == "admin"


def test_session_token_tampered_returns_none() -> None:
    token = security.create_session_token("admin")
    bad = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")
    assert security.read_session_token(bad) is None


def test_session_token_expired() -> None:
    with pytest.raises(ValueError):
        security.read_session_token("not.a.valid.token", max_age_seconds=1)
```

- [ ] **Step 2: Run, verify failure**

```bash
cd backend && uv run pytest tests/test_security.py -v
```

- [ ] **Step 3: Implement `backend/app/core/security.py`**

```python
"""Password hashing and signed session tokens."""
import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import settings

_SALT = "finance-alert-session-v1"


def _serializer() -> URLSafeTimedSerializer:
    if not settings.secret_key:
        raise RuntimeError("SECRET_KEY is not configured")
    return URLSafeTimedSerializer(settings.secret_key, salt=_SALT)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_session_token(username: str) -> str:
    return _serializer().dumps({"u": username})


def read_session_token(token: str, max_age_seconds: int | None = None) -> str | None:
    """Return the username if valid, None if signature is invalid, raise ValueError if expired."""
    if max_age_seconds is None:
        max_age_seconds = settings.session_max_age_days * 86400
    try:
        data = _serializer().loads(token, max_age=max_age_seconds)
    except SignatureExpired as e:
        raise ValueError("Session expired") from e
    except BadSignature:
        return None
    return data.get("u")
```

- [ ] **Step 4: Run tests**

The expired-token test passes a non-token string; let it raise. Adjust the test to use a real token + manipulated TTL; replace test:

```python
def test_session_token_expired() -> None:
    token = security.create_session_token("admin")
    with pytest.raises(ValueError):
        security.read_session_token(token, max_age_seconds=-1)
```

```bash
cd backend && uv run pytest tests/test_security.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/security.py backend/tests/test_security.py
git commit -m "feat(backend): add bcrypt password hashing and signed session tokens"
```

---

### Task D2: Auth schemas, service, and dependency

**Files:**
- Create: `backend/app/schemas/__init__.py`, `backend/app/schemas/auth.py`, `backend/app/services/auth_service.py`, `backend/app/api/__init__.py`, `backend/app/api/deps.py`

- [ ] **Step 1: Create `backend/app/schemas/__init__.py`** (empty)

- [ ] **Step 2: Create `backend/app/schemas/auth.py`**

```python
"""Auth request/response schemas."""
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)


class MeResponse(BaseModel):
    username: str
```

- [ ] **Step 3: Create `backend/app/services/auth_service.py`**

```python
"""Authentication business logic."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.models import User


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
```

- [ ] **Step 4: Create `backend/app/api/__init__.py`** (empty)

- [ ] **Step 5: Create `backend/app/api/deps.py`**

```python
"""FastAPI dependencies: DB session, current user."""
from collections.abc import Iterator
from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.security import read_session_token
from app.models import User


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        username = read_session_token(token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    if username is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_json(request: Request) -> None:
    """CSRF lite: enforce Content-Type: application/json on mutating routes."""
    if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
        ctype = request.headers.get("content-type", "").split(";")[0].strip()
        if request.method == "DELETE" and not ctype:
            return  # DELETE without body is fine
        if ctype != "application/json":
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Content-Type must be application/json",
            )
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/ backend/app/services/auth_service.py backend/app/api/
git commit -m "feat(backend): add auth schemas, service, and request dependencies"
```

---

### Task D3: Auth endpoints (TDD)

**Files:**
- Create: `backend/app/api/auth.py`, `backend/tests/test_api_auth.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write failing test `backend/tests/test_api_auth.py`**

```python
"""Auth endpoint tests."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.security import hash_password
from app.main import app
from app.models import User


@pytest.fixture
def client(db: Session) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    db.add(User(username="admin", password_hash=hash_password("secret123")))
    db.commit()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_login_sets_cookie(client: TestClient) -> None:
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})
    assert resp.status_code == 200
    assert "finance_alert_session" in resp.cookies


def test_login_rejects_bad_password(client: TestClient) -> None:
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_me_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_returns_username_when_logged_in(client: TestClient) -> None:
    client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json() == {"username": "admin"}


def test_logout_clears_cookie(client: TestClient) -> None:
    client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 204
    me = client.get("/api/auth/me")
    assert me.status_code == 401
```

- [ ] **Step 2: Run, verify failure**

```bash
cd backend && uv run pytest tests/test_api_auth.py -v
```

Expected: import error (auth router missing).

- [ ] **Step 3: Implement `backend/app/api/auth.py`**

```python
"""Auth router."""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.core.security import create_session_token
from app.models import User
from app.schemas.auth import LoginRequest, MeResponse
from app.services.auth_service import authenticate

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> dict[str, str]:
    user = authenticate(db, payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_session_token(user.username)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_max_age_days * 86400,
        httponly=True,
        samesite="strict",
        secure=not settings.is_dev,
        path="/",
    )
    return {"username": user.username}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> Response:
    response.delete_cookie(key=settings.session_cookie_name, path="/")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(username=user.username)
```

- [ ] **Step 4: Modify `backend/app/main.py`** to register the auth router

```python
"""FastAPI application entry point."""
from fastapi import FastAPI

from app.api import auth as auth_router

app = FastAPI(title="Finance Alert", version="0.1.0")
app.include_router(auth_router.router)


@app.get("/api/health")
def health() -> dict[str, object]:
    return {"status": "ok", "version": app.version}
```

- [ ] **Step 5: Run tests**

```bash
cd backend && uv run pytest tests/test_api_auth.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/auth.py backend/app/main.py backend/tests/test_api_auth.py
git commit -m "feat(backend): add login, logout, me endpoints with cookie session"
```

Update ARCHITECTURE.md changelog.

---

## Section E — Stocks API

### Task E1: Stock service (TDD)

**Files:**
- Create: `backend/app/services/stock_service.py`, `backend/tests/test_stock_service.py`

- [ ] **Step 1: Write failing test**

```python
"""Tests for stock search service."""
from sqlalchemy.orm import Session

from app.models import Index, Stock, StockIndex
from app.services.stock_service import StockFilter, search_stocks, get_filter_options


def _seed(db: Session) -> None:
    aapl = Stock(ticker="AAPL", exchange="NASDAQ", name="Apple Inc.", sector="Tech", country="US")
    msft = Stock(ticker="MSFT", exchange="NASDAQ", name="Microsoft", sector="Tech", country="US")
    eni = Stock(ticker="ENI.MI", exchange="BIT", name="Eni S.p.A.", sector="Energy", country="IT")
    db.add_all([aapl, msft, eni])
    db.flush()
    ndx = Index(code="NDX", name="Nasdaq-100", country="US")
    ftsemib = Index(code="FTSEMIB", name="FTSE MIB", country="IT")
    db.add_all([ndx, ftsemib])
    db.flush()
    db.add(StockIndex(stock_id=aapl.id, index_id=ndx.id))
    db.add(StockIndex(stock_id=msft.id, index_id=ndx.id))
    db.add(StockIndex(stock_id=eni.id, index_id=ftsemib.id))
    db.commit()


def test_search_by_ticker_prefix(db: Session) -> None:
    _seed(db)
    page = search_stocks(db, StockFilter(q="AA"))
    assert [s.ticker for s in page.items] == ["AAPL"]
    assert page.total == 1


def test_search_by_name_substring(db: Session) -> None:
    _seed(db)
    page = search_stocks(db, StockFilter(q="micro"))
    assert [s.ticker for s in page.items] == ["MSFT"]


def test_filter_by_exchange(db: Session) -> None:
    _seed(db)
    page = search_stocks(db, StockFilter(exchanges=["BIT"]))
    assert [s.ticker for s in page.items] == ["ENI.MI"]


def test_filter_by_index_code(db: Session) -> None:
    _seed(db)
    page = search_stocks(db, StockFilter(index_codes=["NDX"]))
    tickers = sorted(s.ticker for s in page.items)
    assert tickers == ["AAPL", "MSFT"]


def test_filter_options_distinct(db: Session) -> None:
    _seed(db)
    opts = get_filter_options(db)
    assert sorted(opts.exchanges) == ["BIT", "NASDAQ"]
    assert sorted(opts.sectors) == ["Energy", "Tech"]
    assert sorted(opts.countries) == ["IT", "US"]
    assert sorted(o.code for o in opts.indices) == ["FTSEMIB", "NDX"]
```

- [ ] **Step 2: Run, verify failure**

- [ ] **Step 3: Implement `backend/app/services/stock_service.py`**

```python
"""Stock search and filter options."""
from dataclasses import dataclass, field
from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session

from app.models import Index, Stock, StockIndex


@dataclass
class StockFilter:
    q: str | None = None
    exchanges: list[str] = field(default_factory=list)
    sectors: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    index_codes: list[str] = field(default_factory=list)
    limit: int = 50
    offset: int = 0


@dataclass
class StockPage:
    items: list[Stock]
    total: int
    has_more: bool


@dataclass
class IndexOption:
    code: str
    name: str


@dataclass
class FilterOptions:
    exchanges: list[str]
    sectors: list[str]
    countries: list[str]
    indices: list[IndexOption]


def _apply_filter(stmt, f: StockFilter):
    if f.q:
        like = f"{f.q.lower()}%"
        sub = f"%{f.q.lower()}%"
        stmt = stmt.where(
            or_(func.lower(Stock.ticker).like(like), func.lower(Stock.name).like(sub))
        )
    if f.exchanges:
        stmt = stmt.where(Stock.exchange.in_(f.exchanges))
    if f.sectors:
        stmt = stmt.where(Stock.sector.in_(f.sectors))
    if f.countries:
        stmt = stmt.where(Stock.country.in_(f.countries))
    if f.index_codes:
        stmt = (
            stmt.join(StockIndex, StockIndex.stock_id == Stock.id)
            .join(Index, Index.id == StockIndex.index_id)
            .where(Index.code.in_(f.index_codes))
            .distinct()
        )
    return stmt


def search_stocks(db: Session, f: StockFilter) -> StockPage:
    limit = max(1, min(f.limit, 500))
    base = select(Stock)
    base = _apply_filter(base, f)

    count_stmt = select(func.count()).select_from(base.subquery())
    total = db.execute(count_stmt).scalar_one()

    rows = db.execute(base.order_by(Stock.ticker).limit(limit + 1).offset(f.offset)).scalars().all()
    has_more = len(rows) > limit
    return StockPage(items=list(rows[:limit]), total=int(total), has_more=has_more)


def get_filter_options(db: Session) -> FilterOptions:
    exchanges = [r[0] for r in db.execute(select(distinct(Stock.exchange)).order_by(Stock.exchange)).all() if r[0]]
    sectors = [r[0] for r in db.execute(select(distinct(Stock.sector)).order_by(Stock.sector)).all() if r[0]]
    countries = [r[0] for r in db.execute(select(distinct(Stock.country)).order_by(Stock.country)).all() if r[0]]
    indices = [
        IndexOption(code=row.code, name=row.name)
        for row in db.execute(select(Index).order_by(Index.code)).scalars().all()
    ]
    return FilterOptions(exchanges=exchanges, sectors=sectors, countries=countries, indices=indices)
```

- [ ] **Step 4: Run tests, verify pass**

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/stock_service.py backend/tests/test_stock_service.py
git commit -m "feat(backend): add stock search service with filters and tests"
```

---

### Task E2: Stock API endpoints (TDD)

**Files:**
- Create: `backend/app/api/stocks.py`, `backend/app/schemas/stock.py`, `backend/tests/test_api_stocks.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create `backend/app/schemas/stock.py`**

```python
"""Stock response schemas."""
from pydantic import BaseModel, ConfigDict


class StockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ticker: str
    exchange: str
    name: str
    sector: str | None
    industry: str | None
    country: str | None
    currency: str | None
    market_cap: int | None


class StockSearchOut(BaseModel):
    items: list[StockOut]
    total: int
    has_more: bool


class IndexOptionOut(BaseModel):
    code: str
    name: str


class FilterOptionsOut(BaseModel):
    exchanges: list[str]
    sectors: list[str]
    countries: list[str]
    indices: list[IndexOptionOut]
```

- [ ] **Step 2: Write failing tests `backend/tests/test_api_stocks.py`**

```python
"""Stock API tests."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Index, Stock, StockIndex, User


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.flush()
    aapl = Stock(ticker="AAPL", exchange="NASDAQ", name="Apple Inc.", sector="Tech", country="US")
    db.add(aapl)
    db.flush()
    ndx = Index(code="NDX", name="Nasdaq-100", country="US")
    db.add(ndx)
    db.flush()
    db.add(StockIndex(stock_id=aapl.id, index_id=ndx.id))
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_search_returns_page(client: TestClient) -> None:
    resp = client.get("/api/stocks/search?q=AA")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["ticker"] == "AAPL"


def test_get_by_ticker(client: TestClient) -> None:
    resp = client.get("/api/stocks/AAPL")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Apple Inc."


def test_get_by_ticker_not_found(client: TestClient) -> None:
    resp = client.get("/api/stocks/UNKNOWN")
    assert resp.status_code == 404


def test_filters_endpoint(client: TestClient) -> None:
    resp = client.get("/api/stocks/filters")
    assert resp.status_code == 200
    data = resp.json()
    assert "NASDAQ" in data["exchanges"]
    assert {"code": "NDX", "name": "Nasdaq-100"} in data["indices"]
```

- [ ] **Step 3: Implement `backend/app/api/stocks.py`**

```python
"""Stock router."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import Stock, User
from app.schemas.stock import FilterOptionsOut, IndexOptionOut, StockOut, StockSearchOut
from app.services.stock_service import StockFilter, get_filter_options, search_stocks

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("/search", response_model=StockSearchOut)
def search(
    q: str | None = None,
    exchange: Annotated[list[str] | None, Query()] = None,
    sector: Annotated[list[str] | None, Query()] = None,
    country: Annotated[list[str] | None, Query()] = None,
    index: Annotated[list[str] | None, Query()] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> StockSearchOut:
    page = search_stocks(
        db,
        StockFilter(
            q=q,
            exchanges=exchange or [],
            sectors=sector or [],
            countries=country or [],
            index_codes=index or [],
            limit=limit,
            offset=offset,
        ),
    )
    return StockSearchOut(
        items=[StockOut.model_validate(s) for s in page.items],
        total=page.total,
        has_more=page.has_more,
    )


@router.get("/filters", response_model=FilterOptionsOut)
def filters(db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> FilterOptionsOut:
    opts = get_filter_options(db)
    return FilterOptionsOut(
        exchanges=opts.exchanges,
        sectors=opts.sectors,
        countries=opts.countries,
        indices=[IndexOptionOut(code=i.code, name=i.name) for i in opts.indices],
    )


@router.get("/{ticker}", response_model=StockOut)
def get_one(
    ticker: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> StockOut:
    stock = db.execute(select(Stock).where(Stock.ticker == ticker)).scalar_one_or_none()
    if stock is None:
        raise HTTPException(status_code=404, detail="Stock not found")
    return StockOut.model_validate(stock)
```

- [ ] **Step 4: Register router in `backend/app/main.py`**

Add `from app.api import stocks as stocks_router` and `app.include_router(stocks_router.router)`.

- [ ] **Step 5: Run tests**

```bash
cd backend && uv run pytest tests/test_api_stocks.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/stocks.py backend/app/schemas/stock.py backend/app/main.py backend/tests/test_api_stocks.py
git commit -m "feat(backend): add stock search, filters, and detail endpoints"
```

---

## Section F — Watchlists API

### Task F1: Watchlist service (TDD)

**Files:**
- Create: `backend/app/services/watchlist_service.py`, `backend/tests/test_watchlist_service.py`

- [ ] **Step 1: Write tests covering: create, list, get, update, delete, add items, remove item, bulk delete, duplicate name error**

```python
"""Watchlist service tests."""
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Stock, User, Watchlist
from app.services import watchlist_service as ws


@pytest.fixture
def setup(db: Session) -> tuple[User, Stock, Stock]:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.flush()
    s1 = Stock(ticker="AAPL", exchange="NASDAQ", name="Apple")
    s2 = Stock(ticker="MSFT", exchange="NASDAQ", name="Microsoft")
    db.add_all([s1, s2])
    db.commit()
    return user, s1, s2


def test_create_and_list(db: Session, setup) -> None:
    user, _, _ = setup
    wl = ws.create_watchlist(db, user_id=user.id, name="Tech", description="Tech USA")
    db.commit()
    rows = ws.list_watchlists(db, user_id=user.id)
    assert len(rows) == 1
    assert rows[0].id == wl.id
    assert rows[0].item_count == 0


def test_create_duplicate_name_raises(db: Session, setup) -> None:
    user, _, _ = setup
    ws.create_watchlist(db, user_id=user.id, name="Tech")
    db.commit()
    with pytest.raises(ws.DuplicateName):
        ws.create_watchlist(db, user_id=user.id, name="Tech")


def test_update(db: Session, setup) -> None:
    user, _, _ = setup
    wl = ws.create_watchlist(db, user_id=user.id, name="Old")
    db.commit()
    ws.update_watchlist(db, wl.id, name="New", description="d")
    db.commit()
    refreshed = ws.get_watchlist(db, wl.id)
    assert refreshed.name == "New"
    assert refreshed.description == "d"


def test_delete(db: Session, setup) -> None:
    user, _, _ = setup
    wl = ws.create_watchlist(db, user_id=user.id, name="Tech")
    db.commit()
    ws.delete_watchlist(db, wl.id)
    db.commit()
    assert ws.get_watchlist(db, wl.id) is None


def test_add_and_remove_items(db: Session, setup) -> None:
    user, s1, s2 = setup
    wl = ws.create_watchlist(db, user_id=user.id, name="Tech")
    db.commit()
    ws.add_items(db, wl.id, [s1.id, s2.id])
    db.commit()
    detail = ws.get_watchlist_detail(db, wl.id)
    assert {s.id for s in detail.stocks} == {s1.id, s2.id}
    ws.remove_item(db, wl.id, s1.id)
    db.commit()
    detail = ws.get_watchlist_detail(db, wl.id)
    assert {s.id for s in detail.stocks} == {s2.id}


def test_add_existing_item_is_idempotent(db: Session, setup) -> None:
    user, s1, _ = setup
    wl = ws.create_watchlist(db, user_id=user.id, name="Tech")
    db.commit()
    ws.add_items(db, wl.id, [s1.id])
    db.commit()
    ws.add_items(db, wl.id, [s1.id])
    db.commit()
    detail = ws.get_watchlist_detail(db, wl.id)
    assert len(detail.stocks) == 1


def test_bulk_delete_items(db: Session, setup) -> None:
    user, s1, s2 = setup
    wl = ws.create_watchlist(db, user_id=user.id, name="Tech")
    db.commit()
    ws.add_items(db, wl.id, [s1.id, s2.id])
    db.commit()
    ws.bulk_delete_items(db, wl.id, [s1.id, s2.id])
    db.commit()
    detail = ws.get_watchlist_detail(db, wl.id)
    assert detail.stocks == []
```

- [ ] **Step 2: Implement `backend/app/services/watchlist_service.py`**

```python
"""Watchlist business logic."""
from dataclasses import dataclass
from datetime import datetime
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Stock, Watchlist, WatchlistItem


class DuplicateName(Exception):
    pass


@dataclass
class WatchlistSummary:
    id: int
    name: str
    description: str | None
    item_count: int
    created_at: datetime
    updated_at: datetime


@dataclass
class WatchlistDetail:
    id: int
    name: str
    description: str | None
    stocks: list[Stock]
    created_at: datetime
    updated_at: datetime


def _exists_by_name(db: Session, name: str, exclude_id: int | None = None) -> bool:
    stmt = select(Watchlist.id).where(Watchlist.name == name)
    if exclude_id is not None:
        stmt = stmt.where(Watchlist.id != exclude_id)
    return db.execute(stmt).scalar_one_or_none() is not None


def create_watchlist(db: Session, *, user_id: int, name: str, description: str | None = None) -> Watchlist:
    if _exists_by_name(db, name):
        raise DuplicateName(name)
    wl = Watchlist(user_id=user_id, name=name, description=description)
    db.add(wl)
    db.flush()
    return wl


def list_watchlists(db: Session, *, user_id: int) -> list[WatchlistSummary]:
    stmt = (
        select(Watchlist, func.count(WatchlistItem.stock_id))
        .outerjoin(WatchlistItem, WatchlistItem.watchlist_id == Watchlist.id)
        .where(Watchlist.user_id == user_id)
        .group_by(Watchlist.id)
        .order_by(Watchlist.name)
    )
    return [
        WatchlistSummary(
            id=w.id,
            name=w.name,
            description=w.description,
            item_count=int(cnt),
            created_at=w.created_at,
            updated_at=w.updated_at,
        )
        for w, cnt in db.execute(stmt).all()
    ]


def get_watchlist(db: Session, wl_id: int) -> Watchlist | None:
    return db.execute(select(Watchlist).where(Watchlist.id == wl_id)).scalar_one_or_none()


def get_watchlist_detail(db: Session, wl_id: int) -> WatchlistDetail | None:
    wl = get_watchlist(db, wl_id)
    if wl is None:
        return None
    stocks = (
        db.execute(
            select(Stock)
            .join(WatchlistItem, WatchlistItem.stock_id == Stock.id)
            .where(WatchlistItem.watchlist_id == wl_id)
            .order_by(Stock.ticker)
        )
        .scalars()
        .all()
    )
    return WatchlistDetail(
        id=wl.id,
        name=wl.name,
        description=wl.description,
        stocks=list(stocks),
        created_at=wl.created_at,
        updated_at=wl.updated_at,
    )


def update_watchlist(
    db: Session, wl_id: int, *, name: str | None = None, description: str | None = None
) -> Watchlist | None:
    wl = get_watchlist(db, wl_id)
    if wl is None:
        return None
    if name is not None:
        if _exists_by_name(db, name, exclude_id=wl_id):
            raise DuplicateName(name)
        wl.name = name
    if description is not None:
        wl.description = description
    db.flush()
    return wl


def delete_watchlist(db: Session, wl_id: int) -> bool:
    res = db.execute(delete(Watchlist).where(Watchlist.id == wl_id))
    return res.rowcount > 0


def add_items(db: Session, wl_id: int, stock_ids: list[int]) -> int:
    if not stock_ids:
        return 0
    existing = set(
        db.execute(
            select(WatchlistItem.stock_id).where(
                WatchlistItem.watchlist_id == wl_id,
                WatchlistItem.stock_id.in_(stock_ids),
            )
        )
        .scalars()
        .all()
    )
    new_ids = [sid for sid in stock_ids if sid not in existing]
    db.add_all([WatchlistItem(watchlist_id=wl_id, stock_id=sid) for sid in new_ids])
    db.flush()
    return len(new_ids)


def remove_item(db: Session, wl_id: int, stock_id: int) -> bool:
    res = db.execute(
        delete(WatchlistItem).where(
            WatchlistItem.watchlist_id == wl_id, WatchlistItem.stock_id == stock_id
        )
    )
    return res.rowcount > 0


def bulk_delete_items(db: Session, wl_id: int, stock_ids: list[int]) -> int:
    if not stock_ids:
        return 0
    res = db.execute(
        delete(WatchlistItem).where(
            WatchlistItem.watchlist_id == wl_id,
            WatchlistItem.stock_id.in_(stock_ids),
        )
    )
    return res.rowcount
```

- [ ] **Step 3: Run tests, verify pass**

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/watchlist_service.py backend/tests/test_watchlist_service.py
git commit -m "feat(backend): add watchlist service with CRUD and item operations"
```

---

### Task F2: Watchlist API endpoints

**Files:**
- Create: `backend/app/api/watchlists.py`, `backend/app/schemas/watchlist.py`, `backend/tests/test_api_watchlists.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create `backend/app/schemas/watchlist.py`**

```python
"""Watchlist request/response schemas."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.stock import StockOut


class WatchlistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    stock_ids: list[int] | None = None


class WatchlistUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None


class WatchlistSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str | None
    item_count: int
    created_at: datetime
    updated_at: datetime


class WatchlistDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str | None
    stocks: list[StockOut]
    created_at: datetime
    updated_at: datetime


class AddItemsRequest(BaseModel):
    stock_ids: list[int] = Field(min_length=1)


class BulkDeleteRequest(BaseModel):
    stock_ids: list[int] = Field(min_length=1)


class AddItemsResponse(BaseModel):
    added: int


class BulkDeleteResponse(BaseModel):
    removed: int
```

- [ ] **Step 2: Implement `backend/app/api/watchlists.py`**

```python
"""Watchlist router."""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_json
from app.models import User
from app.schemas.stock import StockOut
from app.schemas.watchlist import (
    AddItemsRequest,
    AddItemsResponse,
    BulkDeleteRequest,
    BulkDeleteResponse,
    WatchlistCreate,
    WatchlistDetailOut,
    WatchlistSummaryOut,
    WatchlistUpdate,
)
from app.services import watchlist_service as ws

router = APIRouter(prefix="/api/watchlists", tags=["watchlists"], dependencies=[Depends(require_json)])


@router.get("", response_model=list[WatchlistSummaryOut], dependencies=[])
def list_all(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[WatchlistSummaryOut]:
    return [WatchlistSummaryOut.model_validate(s.__dict__) for s in ws.list_watchlists(db, user_id=user.id)]


@router.post("", response_model=WatchlistDetailOut, status_code=status.HTTP_201_CREATED)
def create(
    payload: WatchlistCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WatchlistDetailOut:
    try:
        wl = ws.create_watchlist(db, user_id=user.id, name=payload.name, description=payload.description)
    except ws.DuplicateName:
        raise HTTPException(status_code=409, detail="Watchlist name already exists")
    if payload.stock_ids:
        ws.add_items(db, wl.id, payload.stock_ids)
    db.commit()
    detail = ws.get_watchlist_detail(db, wl.id)
    assert detail is not None
    return _to_detail_out(detail)


@router.get("/{wl_id}", response_model=WatchlistDetailOut, dependencies=[])
def get_one(
    wl_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> WatchlistDetailOut:
    detail = ws.get_watchlist_detail(db, wl_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return _to_detail_out(detail)


@router.patch("/{wl_id}", response_model=WatchlistDetailOut)
def patch(
    wl_id: int,
    payload: WatchlistUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> WatchlistDetailOut:
    try:
        wl = ws.update_watchlist(db, wl_id, name=payload.name, description=payload.description)
    except ws.DuplicateName:
        raise HTTPException(status_code=409, detail="Watchlist name already exists")
    if wl is None:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    db.commit()
    detail = ws.get_watchlist_detail(db, wl_id)
    assert detail is not None
    return _to_detail_out(detail)


@router.delete("/{wl_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(
    wl_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> Response:
    if not ws.delete_watchlist(db, wl_id):
        raise HTTPException(status_code=404, detail="Watchlist not found")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{wl_id}/items", response_model=AddItemsResponse)
def add_items(
    wl_id: int,
    payload: AddItemsRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> AddItemsResponse:
    if ws.get_watchlist(db, wl_id) is None:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    added = ws.add_items(db, wl_id, payload.stock_ids)
    db.commit()
    return AddItemsResponse(added=added)


@router.delete("/{wl_id}/items/{stock_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_item(
    wl_id: int,
    stock_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Response:
    if not ws.remove_item(db, wl_id, stock_id):
        raise HTTPException(status_code=404, detail="Item not found")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{wl_id}/items/bulk-delete", response_model=BulkDeleteResponse)
def bulk_delete(
    wl_id: int,
    payload: BulkDeleteRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> BulkDeleteResponse:
    removed = ws.bulk_delete_items(db, wl_id, payload.stock_ids)
    db.commit()
    return BulkDeleteResponse(removed=removed)


def _to_detail_out(detail) -> WatchlistDetailOut:
    return WatchlistDetailOut(
        id=detail.id,
        name=detail.name,
        description=detail.description,
        stocks=[StockOut.model_validate(s) for s in detail.stocks],
        created_at=detail.created_at,
        updated_at=detail.updated_at,
    )
```

- [ ] **Step 2b: Note** — `dependencies=[]` on individual GET routes overrides the router-level `require_json`. We attach `require_json` only to mutating routes via per-route. Refactor: instead, drop the router-level dep and apply per-route:

Replace router declaration:

```python
router = APIRouter(prefix="/api/watchlists", tags=["watchlists"])
```

Apply `dependencies=[Depends(require_json)]` only on POST/PATCH/DELETE decorators. Remove the per-route `dependencies=[]` overrides.

- [ ] **Step 3: Write tests `backend/tests/test_api_watchlists.py`** covering: create, get, list, patch, delete, add items, remove item, bulk delete, duplicate name 409, unauth 401, missing JSON content-type 415.

(Patterned exactly like `test_api_stocks.py`. Reuse the `client` fixture pattern with `User` + dependency overrides.)

- [ ] **Step 4: Register router in `backend/app/main.py`**

- [ ] **Step 5: Run all tests**

```bash
cd backend && uv run pytest -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/watchlists.py backend/app/schemas/watchlist.py backend/app/main.py backend/tests/test_api_watchlists.py
git commit -m "feat(backend): add watchlist CRUD and item endpoints with CSRF guard"
```

Update ARCHITECTURE.md changelog.

---

## Section G — Catalog refresh

### Task G1: Catalog refresh service (TDD with mocked HTTP)

**Files:**
- Create: `backend/app/services/catalog_refresh_service.py`, `backend/tests/test_catalog_refresh_service.py`

- [ ] **Step 1: Write failing tests using mocked `pandas.read_html`**

```python
"""Catalog refresh service tests."""
from unittest.mock import patch
import pandas as pd
import pytest
from sqlalchemy.orm import Session

from app.models import CatalogRefreshLog, Index, Stock, StockIndex
from app.services.catalog_refresh_service import (
    INDEX_SOURCES,
    refresh_index,
    refresh_all,
)


SP500_TABLE = pd.DataFrame(
    {
        "Symbol": ["AAPL", "MSFT"],
        "Security": ["Apple Inc.", "Microsoft Corp."],
        "GICS Sector": ["IT", "IT"],
        "GICS Sub-Industry": ["Hardware", "Software"],
    }
)


def test_refresh_index_success(db: Session) -> None:
    with patch("app.services.catalog_refresh_service._fetch_table", return_value=SP500_TABLE):
        result = refresh_index(db, "SP500")
    db.commit()
    assert result.status == "success"
    assert result.stocks_added == 2
    assert db.query(Stock).count() == 2
    idx = db.query(Index).filter_by(code="SP500").one()
    assert db.query(StockIndex).filter_by(index_id=idx.id).count() == 2


def test_refresh_index_failure_logs_error(db: Session) -> None:
    with patch("app.services.catalog_refresh_service._fetch_table", side_effect=RuntimeError("boom")):
        result = refresh_index(db, "SP500")
    db.commit()
    assert result.status == "failed"
    assert "boom" in (result.error_message or "")
    log = db.query(CatalogRefreshLog).filter_by(status="failed").one()
    assert log.index_code == "SP500"


def test_refresh_index_unknown_code_raises(db: Session) -> None:
    with pytest.raises(KeyError):
        refresh_index(db, "DOES_NOT_EXIST")


def test_refresh_all_continues_on_failure(db: Session) -> None:
    def selective(url: str, **_kwargs):
        if "S%26P_500" in url:
            return SP500_TABLE
        raise RuntimeError("source down")

    with patch("app.services.catalog_refresh_service._fetch_table", side_effect=selective):
        results = refresh_all(db)
    db.commit()
    by_code = {r.index_code: r for r in results}
    assert by_code["SP500"].status == "success"
    assert by_code["NDX"].status == "failed"
    assert db.query(Stock).count() >= 2  # SP500 succeeded
```

- [ ] **Step 2: Implement `backend/app/services/catalog_refresh_service.py`**

```python
"""Refresh stock catalog from Wikipedia constituent tables."""
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd
from loguru import logger
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from app.models import CatalogRefreshLog, Index, Stock, StockIndex


USER_AGENT = "FinanceAlert/0.1 (personal use)"

INDEX_SOURCES: dict[str, dict[str, object]] = {
    "SP500": {
        "url": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "name": "S&P 500",
        "country": "US",
        "table_index": 0,
        "ticker_col": "Symbol",
        "name_col": "Security",
        "sector_col": "GICS Sector",
        "industry_col": "GICS Sub-Industry",
        "default_exchange": "NASDAQ",  # mixed; left as-is in seed for finer control
        "currency": "USD",
    },
    "NDX": {
        "url": "https://en.wikipedia.org/wiki/Nasdaq-100",
        "name": "Nasdaq-100",
        "country": "US",
        "table_index": 4,
        "ticker_col": "Ticker",
        "name_col": "Company",
        "sector_col": "GICS Sector",
        "industry_col": "GICS Sub-Industry",
        "default_exchange": "NASDAQ",
        "currency": "USD",
    },
    "DJI": {
        "url": "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average",
        "name": "Dow Jones Industrial Average",
        "country": "US",
        "table_index": 1,
        "ticker_col": "Symbol",
        "name_col": "Company",
        "sector_col": "Industry",
        "industry_col": None,
        "default_exchange": "NYSE",
        "currency": "USD",
    },
    "FTSEMIB": {
        "url": "https://en.wikipedia.org/wiki/FTSE_MIB",
        "name": "FTSE MIB",
        "country": "IT",
        "table_index": 1,
        "ticker_col": "Ticker",
        "name_col": "Company",
        "sector_col": "ICB Sector",
        "industry_col": None,
        "default_exchange": "BIT",
        "currency": "EUR",
    },
}


@dataclass
class RefreshResult:
    index_code: str
    status: str
    stocks_added: int = 0
    stocks_updated: int = 0
    stocks_removed: int = 0
    error_message: str | None = None


def _fetch_table(url: str, table_index: int) -> pd.DataFrame:
    """Wrap pandas.read_html with retry. Patchable for tests."""
    last: Exception | None = None
    for attempt, delay in enumerate([0, 30, 120]):
        if delay:
            time.sleep(delay)
        try:
            tables = pd.read_html(url, storage_options={"User-Agent": USER_AGENT})
            return tables[table_index]
        except Exception as e:  # noqa: BLE001
            last = e
            logger.warning(f"read_html failed for {url} (attempt {attempt + 1}): {e}")
    assert last is not None
    raise last


def _normalize_ticker(raw: str, default_exchange: str) -> tuple[str, str]:
    t = str(raw).strip().upper()
    if "." in t:
        # FTSE MIB ".MI"; keep as-is for BIT
        return t, "BIT" if t.endswith(".MI") else default_exchange
    return t, default_exchange


def _start_log(db: Session, index_code: str) -> CatalogRefreshLog:
    log = CatalogRefreshLog(index_code=index_code, status="in_progress")
    db.add(log)
    db.flush()
    return log


def _finalize_log(log: CatalogRefreshLog, result: RefreshResult) -> None:
    log.status = result.status
    log.stocks_added = result.stocks_added
    log.stocks_updated = result.stocks_updated
    log.stocks_removed = result.stocks_removed
    log.error_message = result.error_message
    log.completed_at = datetime.now(timezone.utc)


def _ensure_index(db: Session, code: str, name: str, country: str) -> Index:
    idx = db.execute(select(Index).where(Index.code == code)).scalar_one_or_none()
    if idx is None:
        idx = Index(code=code, name=name, country=country)
        db.add(idx)
        db.flush()
    return idx


def refresh_index(db: Session, index_code: str) -> RefreshResult:
    if index_code not in INDEX_SOURCES:
        raise KeyError(index_code)
    src = INDEX_SOURCES[index_code]
    log = _start_log(db, index_code)
    result = RefreshResult(index_code=index_code, status="in_progress")
    try:
        df = _fetch_table(src["url"], src["table_index"])  # type: ignore[arg-type]
        idx = _ensure_index(db, index_code, str(src["name"]), str(src["country"]))
        added = updated = 0
        seen_stock_ids: set[int] = set()
        for _, row in df.iterrows():
            ticker_raw = row.get(src["ticker_col"])
            if pd.isna(ticker_raw):
                continue
            ticker, exchange = _normalize_ticker(ticker_raw, str(src["default_exchange"]))
            name_val = str(row.get(src["name_col"]) or ticker)
            sector_val = (
                str(row.get(src["sector_col"]))
                if src["sector_col"] and not pd.isna(row.get(src["sector_col"]))
                else None
            )
            industry_val = (
                str(row.get(src["industry_col"]))
                if src.get("industry_col") and not pd.isna(row.get(src.get("industry_col")))
                else None
            )
            stmt = select(Stock).where(Stock.ticker == ticker, Stock.exchange == exchange)
            stock = db.execute(stmt).scalar_one_or_none()
            if stock is None:
                stock = Stock(
                    ticker=ticker,
                    exchange=exchange,
                    name=name_val,
                    sector=sector_val,
                    industry=industry_val,
                    country=str(src["country"]),
                    currency=str(src["currency"]),
                )
                db.add(stock)
                db.flush()
                added += 1
            else:
                stock.name = name_val
                if sector_val:
                    stock.sector = sector_val
                if industry_val:
                    stock.industry = industry_val
                updated += 1
            seen_stock_ids.add(stock.id)
            existing_link = db.execute(
                select(StockIndex).where(
                    StockIndex.stock_id == stock.id, StockIndex.index_id == idx.id
                )
            ).scalar_one_or_none()
            if existing_link is None:
                db.add(StockIndex(stock_id=stock.id, index_id=idx.id))

        # remove stale memberships for this index
        stale = db.execute(
            delete(StockIndex)
            .where(StockIndex.index_id == idx.id)
            .where(~StockIndex.stock_id.in_(seen_stock_ids))
        )
        removed = stale.rowcount

        result = RefreshResult(
            index_code=index_code,
            status="success",
            stocks_added=added,
            stocks_updated=updated,
            stocks_removed=removed,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception(f"Catalog refresh failed for {index_code}")
        result = RefreshResult(index_code=index_code, status="failed", error_message=str(e))
    _finalize_log(log, result)
    return result


def refresh_all(db: Session) -> list[RefreshResult]:
    results: list[RefreshResult] = []
    for code in INDEX_SOURCES:
        results.append(refresh_index(db, code))
    return results
```

- [ ] **Step 3: Run tests, verify pass**

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/catalog_refresh_service.py backend/tests/test_catalog_refresh_service.py
git commit -m "feat(backend): add catalog refresh service scraping Wikipedia tables"
```

---

### Task G2: Scheduler setup and refresh job wiring

**Files:**
- Create: `backend/app/scheduler/__init__.py`, `backend/app/scheduler/jobs/__init__.py`, `backend/app/scheduler/jobs/refresh_catalog.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create `backend/app/scheduler/jobs/refresh_catalog.py`**

```python
"""APScheduler job: weekly catalog refresh."""
from loguru import logger

from app.core.db import SessionLocal
from app.services.catalog_refresh_service import refresh_all


def run_refresh_all() -> None:
    logger.info("catalog refresh job: starting")
    db = SessionLocal()
    try:
        results = refresh_all(db)
        db.commit()
        for r in results:
            logger.info(
                f"  {r.index_code}: status={r.status} added={r.stocks_added} "
                f"updated={r.stocks_updated} removed={r.stocks_removed}"
            )
    finally:
        db.close()
    logger.info("catalog refresh job: done")
```

- [ ] **Step 2: Create `backend/app/scheduler/__init__.py`**

```python
"""APScheduler setup and lifecycle bound to FastAPI."""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from app.scheduler.jobs.refresh_catalog import run_refresh_all

_scheduler: BackgroundScheduler | None = None


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone="Europe/Rome")
        _scheduler.add_job(
            run_refresh_all,
            trigger=CronTrigger(day_of_week="sat", hour=3, minute=0),
            id="refresh_catalog",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    return _scheduler


def start_scheduler() -> None:
    s = get_scheduler()
    if not s.running:
        s.start()
        logger.info("Scheduler started with jobs: " + ", ".join(j.id for j in s.get_jobs()))


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
```

- [ ] **Step 3: Modify `backend/app/main.py`** to start/stop the scheduler with FastAPI lifespan

```python
"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from fastapi import FastAPI

from app.api import auth as auth_router
from app.api import stocks as stocks_router
from app.api import watchlists as watchlists_router
from app.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(title="Finance Alert", version="0.1.0", lifespan=lifespan)
app.include_router(auth_router.router)
app.include_router(stocks_router.router)
app.include_router(watchlists_router.router)


@app.get("/api/health")
def health() -> dict[str, object]:
    from app.scheduler import get_scheduler
    return {"status": "ok", "scheduler_running": get_scheduler().running, "version": app.version}
```

- [ ] **Step 4: Verify the app starts cleanly**

```bash
cd backend && uv run uvicorn app.main:app --port 8000
# In another terminal:
curl http://localhost:8000/api/health
```

Expected: `scheduler_running: true`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/scheduler/ backend/app/main.py
git commit -m "feat(backend): wire APScheduler with weekly catalog refresh job"
```

Update ARCHITECTURE.md.

---

### Task G3: Catalog API endpoints

**Files:**
- Create: `backend/app/api/catalog.py`, `backend/app/schemas/catalog.py`, `backend/tests/test_api_catalog.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create `backend/app/schemas/catalog.py`**

```python
"""Catalog refresh schemas."""
from datetime import datetime
from pydantic import BaseModel


class RefreshRequest(BaseModel):
    index_code: str | None = None


class RefreshAccepted(BaseModel):
    accepted: bool = True


class IndexStatusOut(BaseModel):
    index_code: str
    last_started_at: datetime | None
    last_completed_at: datetime | None
    last_status: str | None
    stocks_added: int | None
    stocks_updated: int | None
    stocks_removed: int | None
    error_message: str | None


class CatalogStatusOut(BaseModel):
    indices: list[IndexStatusOut]
```

- [ ] **Step 2: Implement `backend/app/api/catalog.py`**

```python
"""Catalog refresh endpoints."""
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_json
from app.core.db import SessionLocal
from app.models import CatalogRefreshLog, User
from app.schemas.catalog import CatalogStatusOut, IndexStatusOut, RefreshAccepted, RefreshRequest
from app.services.catalog_refresh_service import INDEX_SOURCES, refresh_all, refresh_index

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


def _run_refresh(index_code: str | None) -> None:
    db = SessionLocal()
    try:
        if index_code is None:
            refresh_all(db)
        else:
            refresh_index(db, index_code)
        db.commit()
    finally:
        db.close()


@router.post("/refresh", status_code=202, response_model=RefreshAccepted, dependencies=[Depends(require_json)])
def trigger(
    payload: RefreshRequest,
    background: BackgroundTasks,
    _user: User = Depends(get_current_user),
) -> RefreshAccepted:
    background.add_task(_run_refresh, payload.index_code)
    return RefreshAccepted(accepted=True)


@router.get("/status", response_model=CatalogStatusOut)
def status(db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> CatalogStatusOut:
    items: list[IndexStatusOut] = []
    for code in INDEX_SOURCES:
        last = db.execute(
            select(CatalogRefreshLog)
            .where(CatalogRefreshLog.index_code == code)
            .order_by(CatalogRefreshLog.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        items.append(
            IndexStatusOut(
                index_code=code,
                last_started_at=last.started_at if last else None,
                last_completed_at=last.completed_at if last else None,
                last_status=last.status if last else None,
                stocks_added=last.stocks_added if last else None,
                stocks_updated=last.stocks_updated if last else None,
                stocks_removed=last.stocks_removed if last else None,
                error_message=last.error_message if last else None,
            )
        )
    return CatalogStatusOut(indices=items)
```

- [ ] **Step 3: Tests** — minimal coverage: status returns entries for all 4 indices; trigger returns 202.

- [ ] **Step 4: Register router**, run tests, commit.

```bash
git add backend/app/api/catalog.py backend/app/schemas/catalog.py backend/app/main.py backend/tests/test_api_catalog.py
git commit -m "feat(backend): add catalog refresh trigger and status endpoints"
```

---

## Section H — Frontend foundation

### Task H1: Install React Router, TanStack Query, shadcn/ui

**Files:**
- Modify: `frontend/package.json`, `frontend/components.json` (created by shadcn)
- Create: `frontend/src/lib/utils.ts`, `frontend/src/lib/query-client.ts`

- [ ] **Step 1: Install runtime deps**

```bash
cd frontend
npm install react-router-dom @tanstack/react-query react-hook-form zod @hookform/resolvers
npm install -D @types/node
```

- [ ] **Step 2: Initialize shadcn/ui**

```bash
cd frontend
npx shadcn@latest init
```

Choices: TypeScript yes, default style, base color slate, CSS variables yes, alias `@/components`, alias `@/lib/utils`.

- [ ] **Step 3: Add the components needed for Fase 1**

```bash
cd frontend
npx shadcn@latest add button input label dialog select tabs table card badge separator dropdown-menu sonner
```

- [ ] **Step 4: Create `frontend/src/lib/query-client.ts`**

```typescript
import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000, refetchOnWindowFocus: false },
    mutations: { retry: 0 },
  },
});
```

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "chore(frontend): install router, query, and shadcn/ui components"
```

---

### Task H2: API client and auth hook

**Files:**
- Create: `frontend/src/api/client.ts`, `frontend/src/api/types.ts`, `frontend/src/api/auth.ts`, `frontend/src/api/stocks.ts`, `frontend/src/api/watchlists.ts`, `frontend/src/hooks/useAuth.ts`

- [ ] **Step 1: Create `frontend/src/api/client.ts`**

```typescript
export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(`HTTP ${status}: ${detail}`);
  }
}

export async function api<T>(
  path: string,
  init?: RequestInit & { signal?: AbortSignal }
): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const resp = await fetch(path, {
    ...init,
    headers,
    credentials: "same-origin",
  });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const data = await resp.json();
      detail = data.detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(resp.status, detail);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}
```

- [ ] **Step 2: Create `frontend/src/api/types.ts`** with TypeScript types matching backend Pydantic schemas (Stock, WatchlistSummary, WatchlistDetail, FilterOptions, MeResponse, IndexStatus).

- [ ] **Step 3: Create per-domain API modules** — `auth.ts`, `stocks.ts`, `watchlists.ts` — each with thin wrappers around `api()` returning typed responses.

Example `auth.ts`:

```typescript
import { api } from "./client";
import type { Me } from "./types";

export const auth = {
  login: (username: string, password: string) =>
    api<{ username: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: () => api<void>("/api/auth/logout", { method: "POST", body: "{}" }),
  me: () => api<Me>("/api/auth/me"),
};
```

- [ ] **Step 4: Create `frontend/src/hooks/useAuth.ts`** — thin wrapper around `useQuery` + `useMutation` for login/logout/me.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/ frontend/src/hooks/useAuth.ts
git commit -m "feat(frontend): add typed API client and auth hooks"
```

---

### Task H3: Routing, layout, ProtectedRoute

**Files:**
- Modify: `frontend/src/App.tsx`, `frontend/src/main.tsx`
- Create: `frontend/src/components/Layout.tsx`, `frontend/src/components/ProtectedRoute.tsx`, `frontend/src/pages/LoginPage.tsx`

- [ ] **Step 1: Wire QueryClientProvider and Router in `frontend/src/main.tsx`**

```typescript
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { queryClient } from "@/lib/query-client";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>
);
```

- [ ] **Step 2: Implement `frontend/src/App.tsx`** with routes

```typescript
import { Navigate, Route, Routes } from "react-router-dom";
import LoginPage from "@/pages/LoginPage";
import WatchlistListPage from "@/pages/WatchlistListPage";
import WatchlistDetailPage from "@/pages/WatchlistDetailPage";
import Layout from "@/components/Layout";
import ProtectedRoute from "@/components/ProtectedRoute";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
        <Route path="/" element={<Navigate to="/watchlists" replace />} />
        <Route path="/watchlists" element={<WatchlistListPage />} />
        <Route path="/watchlists/new" element={<WatchlistDetailPage />} />
        <Route path="/watchlists/:id" element={<WatchlistDetailPage />} />
      </Route>
      <Route path="*" element={<div className="p-8">404</div>} />
    </Routes>
  );
}
```

- [ ] **Step 3: Implement `frontend/src/components/ProtectedRoute.tsx`**

```typescript
import { Navigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { auth } from "@/api/auth";

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["me"],
    queryFn: () => auth.me(),
    retry: false,
  });
  if (isLoading) return <div className="p-8">Caricamento…</div>;
  if (isError || !data) return <Navigate to="/login" replace />;
  return <>{children}</>;
}
```

- [ ] **Step 4: Implement `frontend/src/components/Layout.tsx`** — sidebar (Watchlists active; Dashboard/Stocks/Alerts/Rules/Settings disabled with tooltip "Disponibile nelle prossime fasi"), header with username + logout button, `<Outlet />` in main.

- [ ] **Step 5: Implement `frontend/src/pages/LoginPage.tsx`** — React Hook Form + Zod, POST `/api/auth/login`, on success invalidate `me` and `navigate('/watchlists')`. UI strings in Italian.

- [ ] **Step 6: Smoke test**

```bash
cd backend && uv run uvicorn app.main:app --port 8000 &
cd frontend && npm run dev
```

Open http://localhost:5173, redirected to /login, type credentials, redirected to /watchlists (empty).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): add routing, layout, ProtectedRoute, and LoginPage"
```

---

## Section I — Frontend watchlist pages

### Task I1: WatchlistListPage

**Files:**
- Create: `frontend/src/pages/WatchlistListPage.tsx`, `frontend/src/hooks/useWatchlists.ts`

- [ ] **Step 1: Implement hooks**

```typescript
// useWatchlists.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { watchlists } from "@/api/watchlists";

export function useWatchlists() {
  return useQuery({ queryKey: ["watchlists"], queryFn: () => watchlists.list() });
}

export function useDeleteWatchlist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => watchlists.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlists"] }),
  });
}
```

- [ ] **Step 2: Implement `WatchlistListPage.tsx`**

- Header with "Le mie watchlist" + button "Nuova watchlist" → navigate to `/watchlists/new`
- shadcn Table: columns nome, descrizione, n. stock, ultimo aggiornamento, azioni (Apri, Elimina con conferma Dialog)
- Empty state card with CTA when list is empty
- Loading skeleton

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/WatchlistListPage.tsx frontend/src/hooks/useWatchlists.ts
git commit -m "feat(frontend): add WatchlistListPage with delete confirmation"
```

---

### Task I2: WatchlistDetailPage — selection panel

**Files:**
- Create: `frontend/src/pages/WatchlistDetailPage.tsx`, `frontend/src/components/StockSearchTab.tsx`, `frontend/src/components/StockFiltersTab.tsx`, `frontend/src/hooks/useStocks.ts`

- [ ] **Step 1: Implement `useStocks.ts`** with `useStockSearch(filters)` (TanStack `keepPreviousData`, `enabled: boolean`) and `useStockFilters()` (cached infinitely until catalog refresh).

- [ ] **Step 2: Implement `StockSearchTab.tsx`** — input with 300ms debounce, fetch results, render chips with "+ aggiungi" callback prop.

- [ ] **Step 3: Implement `StockFiltersTab.tsx`** — multi-select shadcn Select for exchange/sector/country/index from `useStockFilters()`. Live count via `useStockSearch({...filters, limit: 0})` (or limit=1 reading `total`). "Aggiungi tutti i selezionati" button calls back with all stock_ids fetched in pages.

- [ ] **Step 4: Wire shell of `WatchlistDetailPage.tsx`** with two-column layout, Tabs from shadcn for left panel, placeholder right panel for next task.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/WatchlistDetailPage.tsx frontend/src/components/StockSearchTab.tsx frontend/src/components/StockFiltersTab.tsx frontend/src/hooks/useStocks.ts
git commit -m "feat(frontend): add stock search/filters panel in watchlist editor"
```

---

### Task I3: WatchlistDetailPage — autosave logic

**Files:**
- Modify: `frontend/src/pages/WatchlistDetailPage.tsx`
- Create: `frontend/src/components/SaveIndicator.tsx`, `frontend/src/hooks/useDebouncedCallback.ts`, `frontend/src/hooks/useWatchlistDetail.ts`

- [ ] **Step 1: Implement `useDebouncedCallback.ts`** — 500ms debounce wrapper with `flush()` and `cancel()`.

- [ ] **Step 2: Implement `useWatchlistDetail.ts`** — query for the detail; mutations for create, patch, addItems, removeItem; uses AbortController to cancel in-flight on new mutation.

- [ ] **Step 3: Implement `SaveIndicator.tsx`** — props: `state: 'idle' | 'saving' | 'saved' | 'error'`, render with Italian strings, fade-out after 2s on `'saved'`.

- [ ] **Step 4: Implement autosave in `WatchlistDetailPage.tsx`**

State machine:

```
mode: 'create' | 'edit'
saveState: 'idle' | 'saving' | 'saved' | 'error'

onNameChange(value):
  setName(value)
  if (value.trim().length === 0) {
    if (mode === 'edit') setSaveState('idle')  // no save with empty name
    return
  }
  debouncedSave({ name: value })

onDescriptionChange(value):
  setDescription(value)
  debouncedSave({ description: value })

debouncedSave(patch):
  if (mode === 'create') {
    setMode('edit')
    POST /api/watchlists { name, description, stock_ids: [] }
    -> response.id, history.replaceState(`/watchlists/${id}`)
  } else {
    PATCH /api/watchlists/:id patch
  }

onAddStock(stockId):
  if (mode === 'create') {
    if (name.trim() === '') { showHint('Inserisci un nome per iniziare'); return }
    flush debouncedSave first  // ensure watchlist exists
  }
  POST /api/watchlists/:id/items { stock_ids: [stockId] }  // immediate

onRemoveStock(stockId):
  DELETE /api/watchlists/:id/items/:stockId  // immediate
```

Cleanup on unmount: cancel pending debounce, abort in-flight requests.

- [ ] **Step 5: Manual end-to-end test**

Open http://localhost:5173/watchlists/new, type name "Test", verify after 500ms the URL becomes `/watchlists/<id>` and indicator shows "Salvato". Add stock from search panel, verify it appears immediately. Reload page, all data still there.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/WatchlistDetailPage.tsx frontend/src/components/SaveIndicator.tsx frontend/src/hooks/useDebouncedCallback.ts frontend/src/hooks/useWatchlistDetail.ts
git commit -m "feat(frontend): implement autosave with debounce and create-on-first-edit flow"
```

Update ARCHITECTURE.md.

---

## Section J — Operations

### Task J1: Logging configuration

**Files:**
- Create: `backend/app/core/logging.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create `backend/app/core/logging.py`**

```python
"""Loguru configuration: console + rotated file."""
import sys
from pathlib import Path
from loguru import logger

from app.core.config import settings


def configure_logging() -> None:
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )
    logs_dir = Path("./data/logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        logs_dir / "app.log",
        level=settings.log_level,
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
    )
```

- [ ] **Step 2: Add request middleware in `backend/app/main.py`**

```python
import time
from fastapi import Request
from loguru import logger
from app.core.logging import configure_logging

configure_logging()

# ... after app definition:
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    dur_ms = (time.perf_counter() - start) * 1000
    logger.info(f"{request.method} {request.url.path} -> {response.status_code} ({dur_ms:.1f}ms)")
    return response
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/logging.py backend/app/main.py
git commit -m "feat(backend): configure loguru with console + rotated file and request middleware"
```

---

### Task J2: Production-local mode (FastAPI serves built frontend)

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add StaticFiles mount with SPA fallback**

```python
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# After all routers are included:
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            return {"detail": "Not Found"}, 404  # FastAPI handles its own 404 for /api
        index = FRONTEND_DIST / "index.html"
        return FileResponse(index)
```

- [ ] **Step 2: End-to-end test**

```bash
cd frontend && npm run build
cd ../backend && uv run uvicorn app.main:app --port 8000
```

Open http://localhost:8000 — see login page, log in, create a watchlist, all from one origin.

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(backend): serve built frontend in prod-local mode with SPA fallback"
```

Update ARCHITECTURE.md.

---

### Task J3: Windows startup scripts

**Files:**
- Create: `scripts/windows/Run-FinanceAlert.ps1`, `Register-FinanceAlertStartup.ps1`, `Unregister-FinanceAlertStartup.ps1`

- [ ] **Step 1: Create `scripts/windows/Run-FinanceAlert.ps1`**

```powershell
# Run-FinanceAlert.ps1 — invoked by Task Scheduler at user logon
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $ProjectRoot

$LogDir = Join-Path $ProjectRoot "backend\data\logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$LogFile = Join-Path $LogDir "windows-task.log"

# Simple rotation: rename if >10 MB
if (Test-Path $LogFile) {
    $size = (Get-Item $LogFile).Length
    if ($size -gt 10MB) {
        $rotated = "$LogFile.1"
        if (Test-Path $rotated) { Remove-Item $rotated -Force }
        Rename-Item $LogFile $rotated
    }
}

Set-Location (Join-Path $ProjectRoot "backend")
& uv run uvicorn app.main:app --port 8000 *>> $LogFile
```

- [ ] **Step 2: Create `scripts/windows/Register-FinanceAlertStartup.ps1`**

```powershell
$ErrorActionPreference = "Stop"
$ScriptToRun = Join-Path $PSScriptRoot "Run-FinanceAlert.ps1"
if (-not (Test-Path $ScriptToRun)) { throw "Run-FinanceAlert.ps1 not found at $ScriptToRun" }

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$ScriptToRun`""

$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask `
    -TaskName "FinanceAlert" `
    -Description "Avvia l'app Finance Alert al logon utente" `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Force | Out-Null

Write-Host "Task FinanceAlert registrato. Verra' avviato al prossimo logon."
Write-Host "Per avviarlo subito: Start-ScheduledTask -TaskName FinanceAlert"
```

- [ ] **Step 3: Create `scripts/windows/Unregister-FinanceAlertStartup.ps1`**

```powershell
$ErrorActionPreference = "Stop"
$task = Get-ScheduledTask -TaskName "FinanceAlert" -ErrorAction SilentlyContinue
if ($null -eq $task) {
    Write-Host "Task FinanceAlert non registrato."
    exit 0
}
Stop-ScheduledTask -TaskName "FinanceAlert" -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "FinanceAlert" -Confirm:$false
Write-Host "Task FinanceAlert rimosso."
```

- [ ] **Step 4: Manual test**

In PowerShell:

```powershell
.\scripts\windows\Register-FinanceAlertStartup.ps1
Start-ScheduledTask -TaskName FinanceAlert
Start-Sleep -Seconds 5
Invoke-WebRequest -UseBasicParsing http://localhost:8000/api/health
.\scripts\windows\Unregister-FinanceAlertStartup.ps1
```

Expected: health endpoint responds; task is removed cleanly.

- [ ] **Step 5: Commit**

```bash
git add scripts/windows/
git commit -m "feat(ops): add Windows Task Scheduler startup scripts"
```

Update ARCHITECTURE.md.

---

### Task J4: README finalization and Definition of Done

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Expand `README.md` with full setup guide**

Sections: Prerequisites, First-time setup (clone, copy `.env`, generate password hash, `just install`, `just up`), Daily development (commands), Production-local mode (build + run), Windows auto-start, Troubleshooting.

Reference `docs/ARCHITECTURE.md` and the spec.

- [ ] **Step 2: End-to-end smoke test**

Fresh clone in a temp dir, follow README from scratch, confirm everything works.

- [ ] **Step 3: Run full test suite**

```bash
just test
just lint
```

Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: finalize README with full setup, dev, and Windows auto-start guide"
```

---

## Self-review checklist

Before marking the plan complete, verify against the spec:

- [ ] §3 (out of scope): no Fase 2/3 features bled into tasks (no fetchers, indicators, rules, notifiers)
- [ ] §5 (data model): all 7 tables (users, stocks, indices, stock_indices, watchlists, watchlist_items, catalog_refresh_log) created in B2/B3
- [ ] §6 (seed): CSV files in C1, idempotent service in C2, periodic refresh in G1/G2
- [ ] §7 (API): all endpoints covered — auth (D3), stocks search/filters/detail (E2), watchlists CRUD/items/bulk-delete (F2), catalog refresh/status (G3), health (J1 area)
- [ ] §8 (frontend): LoginPage (H3), WatchlistListPage (I1), WatchlistDetailPage with autosave (I2/I3), Layout with sidebar placeholders (H3)
- [ ] §9 (config): `.env.example` (A1), pydantic-settings (B1), bcrypt utility (C3)
- [ ] §10 (repo structure): all paths align
- [ ] §11 (justfile + quality gates): justfile in A1, gates checked in J4
- [ ] §12 (security): bcrypt cost 12 (D1), SameSite=Strict cookie (D3), CSRF via JSON content-type (D2 deps)
- [ ] §12.5 (Windows): scripts in J3
- [ ] §13 (logging): J1
- [ ] §14 (DoD): J4 final integration verifies the full flow described in spec

---

## Execution Handoff

Plan complete and saved to [docs/superpowers/plans/2026-04-30-finance-alert-fase1.md](docs/superpowers/plans/2026-04-30-finance-alert-fase1.md). Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration with full context isolation.

**2. Inline Execution** — I execute tasks sequentially in this same session using the `executing-plans` skill, with checkpoints for your review at the end of each section.

Which approach?

