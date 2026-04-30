# Use copy-mode for venv creation: avoids Windows hardlink failures on
# default-config systems (no Developer Mode). Harmless on Linux/macOS.
export UV_LINK_MODE := "copy"

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
