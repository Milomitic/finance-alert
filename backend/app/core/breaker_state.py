"""Persistent circuit-breaker state across backend restarts.

The Marketaux / Finnhub circuit breakers in their respective services
live in module globals (`_BLOCKED_UNTIL`). That means a restart blanks
them: a breaker that tripped one minute before `uvicorn --reload` (or
a deploy) reopens immediately on the next call — wasting the first
HTTP round-trip to discover the upstream is still rate-limited and
re-tripping all over again.

This module is the tiny JSON file backing store used by the breakers
to survive restart. Format:

    {
      "marketaux.news":  {"until": "2026-05-21T00:00:00+00:00",
                          "reason": "HTTP 429 — quota/rate-limit"},
      "finnhub.news":    {"until": "2026-05-20T15:42:11+00:00",
                          "reason": "probe HTTP 429"}
    }

Concurrency: a module-level RLock serializes writes. Reads load the
whole file (a few hundred bytes), so even concurrent reads are cheap.

Failure mode: any IO error → log + treat as "no persisted state".
Production-safe — the breaker logic on top will trip again on the
next live rate-limit signal; persistence is an OPTIMIZATION, not a
correctness guarantee.
"""
from __future__ import annotations

import datetime as _dt
import json
import threading
from pathlib import Path

from loguru import logger


# State file lives next to the SQLite DB so it travels with the app's
# durable state (and gets picked up by the same backup mechanism the
# user already has for `app.db`).
_STATE_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_STATE_FILE = _STATE_DIR / "breakers.json"
_LOCK = threading.RLock()


def _read_all() -> dict[str, dict]:
    """Load the JSON file. Returns {} on any read error — callers
    treat empty dict as "no persisted state, start fresh"."""
    try:
        if not _STATE_FILE.exists():
            return {}
        with _STATE_FILE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {}
        return data
    except (OSError, json.JSONDecodeError) as e:
        # Corrupted file would block ALL persisted breakers from working
        # — log loudly so the operator notices, then return empty so we
        # don't poison the in-memory state with garbage.
        logger.warning(f"[breaker_state] failed to read {_STATE_FILE}: {e}")
        return {}


def _write_all(state: dict[str, dict]) -> None:
    """Write the JSON file atomically (tmp + rename). The atomic swap
    means a crash mid-write can't leave the file half-truncated and
    `_read_all` parsing as `{}` on the next boot — either we have the
    old file or the new file, never a partial."""
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _STATE_FILE.with_suffix(_STATE_FILE.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, sort_keys=True)
        tmp.replace(_STATE_FILE)
    except OSError as e:
        logger.warning(f"[breaker_state] failed to write {_STATE_FILE}: {e}")


def load(source_key: str) -> _dt.datetime | None:
    """Return the persisted `blocked_until` for `source_key` if it's
    still in the future; otherwise None (and prune the stale entry).

    `source_key` is a free-form identifier — convention:
    `"<source>.<op>"`, e.g. `"marketaux.news"`, `"finnhub.news"`.
    """
    with _LOCK:
        state = _read_all()
        entry = state.get(source_key)
        if not entry:
            return None
        raw_until = entry.get("until")
        if not isinstance(raw_until, str):
            return None
        try:
            until = _dt.datetime.fromisoformat(raw_until)
        except ValueError:
            return None
        # Discard stale entries — once the breaker window has passed,
        # remove from disk so we don't keep parsing it on every boot.
        now = _dt.datetime.now(_dt.UTC)
        if until <= now:
            state.pop(source_key, None)
            _write_all(state)
            return None
        return until


def save(source_key: str, until: _dt.datetime, *, reason: str = "") -> None:
    """Persist a breaker-open timestamp + reason. Idempotent."""
    with _LOCK:
        state = _read_all()
        state[source_key] = {
            "until": until.isoformat(),
            "reason": reason or "",
        }
        _write_all(state)


def clear(source_key: str) -> None:
    """Remove the persisted entry for `source_key`. Called when a
    breaker resets cleanly (window passed without re-trip)."""
    with _LOCK:
        state = _read_all()
        if source_key in state:
            state.pop(source_key)
            _write_all(state)
