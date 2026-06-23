"""Tiny atomic-JSON store for runtime operational state that should survive a
backend restart (data-source health counters, scheduler job stats).

Mirrors the atomic temp+rename pattern of `breaker_state.py`. Best-effort: any
IO/parse error → log + treat as "no state". Persistence here is an optimization
for UI continuity (the Salute page), never a correctness guarantee.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

# Lives next to the SQLite DB so it travels with the app's durable state and the
# user's existing backup of `data/`.
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def data_path(filename: str) -> Path:
    return _DATA_DIR / filename


def read_json(path: Path) -> dict | None:
    """Load a JSON object from `path`, or None on missing/corrupt/non-dict."""
    try:
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"[persist_json] failed to read {path}: {e}")
        return None


def write_json(path: Path, obj: dict[str, Any]) -> None:
    """Atomically write `obj` as JSON to `path` (tmp + rename), so a crash
    mid-write can never leave a half-truncated file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(obj, fh, separators=(",", ":"))
        tmp.replace(path)
    except OSError as e:
        logger.warning(f"[persist_json] failed to write {path}: {e}")
