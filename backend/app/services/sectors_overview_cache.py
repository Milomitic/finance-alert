"""Module-level TTL cache for the /api/sectors/overview payload.

Lives in the services layer (not in `app/api/sectors.py`, where it was
born) so that `score_service.recompute_all` can invalidate it at the
end of a recompute WITHOUT a service→API import — the API router
imports services all over the place, so the reverse edge would be a
circular-import time bomb.

Why cache at all: the overview data is cheap to compute (SQL-only +
L1-only fundamentals, ~50-150ms on a warm process) but the /sectors
hub is the first stop after login for many sessions, so memoizing it
for 60s collapses the dozens of duplicate hits during a single
browsing burst (multiple tabs, F5, navigating in-and-out) to a single
SQL pass.

Why invalidate on recompute: composite scores are the headline number
on every sector tile. Without the hook, a user who clicks "Ricalcola
score" and lands on /sectors within the TTL sees the pre-recompute
averages — the exact "fix didn't work" phantom this repo keeps
re-learning. The TTL stays as a safety net for every OTHER write path.

The payload is stored as an opaque object (the API layer owns the
Pydantic model) — this module deliberately knows nothing about its
shape, keeping the dependency arrow pointing API → service only.
"""
from __future__ import annotations

import time
from typing import Any

_CACHE: dict[str, tuple[float, Any]] = {}
_TTL_SECONDS = 60.0


def get_cached() -> Any | None:
    """Return the memoized payload if within TTL, else None."""
    cached = _CACHE.get("default")
    if cached is None:
        return None
    ts, payload = cached
    if time.time() - ts >= _TTL_SECONDS:
        return None
    return payload


def store(payload: Any) -> None:
    """Memoize `payload` under the singleton key with a fresh timestamp."""
    _CACHE["default"] = (time.time(), payload)


def clear_overview_cache() -> None:
    """Drop the memoized payload so the next hit recomputes from scratch.

    Called by tests and by `score_service.recompute_all` at the end of
    every recompute (the post-recompute hook).
    """
    _CACHE.clear()
