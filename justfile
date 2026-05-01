# Use copy-mode for venv creation: avoids Windows hardlink failures on
# default-config systems (no Developer Mode). Harmless on Linux/macOS.
export UV_LINK_MODE := "copy"

# On Windows, use cmd.exe (always available, supports `&&`) instead of looking
# for `sh` which is not on PATH unless Git Bash exposes it. On Unix-like systems
# just defaults to `sh -cu`, which is fine.
set windows-shell := ["cmd.exe", "/C"]

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

# `up` runs both servers in parallel. POSIX backgrounding (`&`) on Linux/macOS;
# `start /B` on Windows (cmd) so the second command does not block.
[unix]
up:
	just be & just fe

[windows]
up:
	start /B "be" cmd /C "just be"
	just fe

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
