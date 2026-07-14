"""Tiny atomic-JSON store for runtime operational state that should survive a
backend restart (data-source health counters, scheduler job stats).

Mirrors the atomic temp+rename pattern of `breaker_state.py`. Best-effort: any
IO/parse error → log + treat as "no state". Persistence here is an optimization
for UI continuity (the Salute page), never a correctness guarantee.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from loguru import logger

# Lives next to the SQLite DB so it travels with the app's durable state and the
# user's existing backup of `data/`.
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def data_path(filename: str) -> Path:
    return _DATA_DIR / filename


def _replace_with_retry(tmp: str, path: Path, attempts: int = 8) -> None:
    """`os.replace` is atomic even under concurrent writers on POSIX (the cloud
    target). On Windows, though, a replace of a target another thread is
    concurrently replacing/reading raises PermissionError (WinError 5, a sharing
    violation) — retry briefly; the window is microseconds. No-op cost on POSIX."""
    for attempt in range(attempts):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.005 * (attempt + 1))


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
    """Atomically write `obj` as JSON to `path` (unique tmp + rename).

    A crash mid-write can never leave a half-truncated file, AND concurrent
    writers never collide: each call gets its OWN tmp via `mkstemp`, and the
    last `os.replace` wins (fine for latest-state semantics). The old code used
    a FIXED `"<name>.tmp"`, which raced — two scheduler-job threads persisting
    at the same 5-min tick would share that tmp; the first renamed it into
    place, the second hit `ENOENT` on replace (the recurring "[persist_json]
    failed to write … No such file or directory" warning on the Salute page).
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(obj, fh, separators=(",", ":"))
            _replace_with_retry(tmp, path)
        except BaseException:
            with suppress(OSError):
                os.unlink(tmp)  # never leave our unique tmp behind on failure
            raise
    except OSError as e:
        logger.warning(f"[persist_json] failed to write {path}: {e}")
