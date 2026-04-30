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
