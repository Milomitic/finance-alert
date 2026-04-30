# Finance Alert

Local-first single-user stock watchlist manager.

## Setup

Prerequisites: Python 3.11+, Node 20+, [uv](https://docs.astral.sh/uv/), [just](https://github.com/casey/just).

```bash
cp .env.example .env
# After `just install`, generate ADMIN_PASSWORD_HASH and paste it into .env:
#   cd backend && uv run python -m app.scripts.set_admin_password
just install
just up
```

Open http://localhost:5173.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for technical reference.
