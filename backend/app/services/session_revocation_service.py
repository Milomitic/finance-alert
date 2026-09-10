"""Persistence for the session revocation list.

Layering: `app.core.security` owns the revocation DECISION and the in-memory
set it is checked against, and stays free of any database import. This module
owns the row. `app.api.auth` wires the two on logout, where a DB session is
already in hand, and `main.lifespan` rehydrates on boot.

⚠️ **Reads stay in memory, deliberately.** `read_session_token` runs on every
authenticated request, and `/api/health` alone is ~18k of the ~20k daily
requests because it is the liveness probe. A per-request SELECT to answer a
question whose answer is almost always "no" would be a real cost for no gain.
So the table is read ONCE at startup and written through on every revoke.

⚠️ **What this therefore does NOT solve: more than one replica.** A revoke
reaches the database immediately, but the other replica's in-memory set only
learns about it at its next restart. The app runs one replica today and
FA-014's stated gap is the restart, not distribution. If a second replica is
ever added, this becomes a shared-store problem again and the honest fix is a
short TTL re-read or a pub/sub, not pretending the current design covers it.
"""
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.revoked_session import RevokedSession


def persist(db: Session, token_hash: str, expires_at: datetime) -> None:
    """Record one revoked token. Idempotent: revoking twice is not an error.

    Best-effort by design. A logout must still clear the cookie and drop the
    token from the in-memory set even if the write fails — refusing to log
    someone out because a table is unreachable is the worse failure.
    """
    try:
        existing = db.get(RevokedSession, token_hash)
        if existing is None:
            db.add(RevokedSession(token_hash=token_hash, expires_at=expires_at))
            db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning(f"[auth] could not persist revocation: {e}")


def load_active(db: Session) -> dict[str, float]:
    """Every revocation still in force, as {token_hash: expiry unix seconds}.

    Shaped for `security.hydrate_revoked`, which holds the same mapping.
    """
    now = datetime.now(UTC)
    rows = db.execute(
        select(RevokedSession.token_hash, RevokedSession.expires_at)
        .where(RevokedSession.expires_at > now)
    ).all()
    out: dict[str, float] = {}
    for token_hash, expires_at in rows:
        # SQLite hands back naive datetimes; Postgres tz-aware. Both mean UTC
        # here, and `.timestamp()` on a naive value would silently apply the
        # SERVER's local zone — an hour or two of extra or missing revocation.
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        out[token_hash] = expires_at.timestamp()
    return out


def purge_expired(db: Session) -> int:
    """Drop rows whose token has expired on its own. Returns the count."""
    try:
        result = db.execute(
            delete(RevokedSession).where(RevokedSession.expires_at <= datetime.now(UTC))
        )
        db.commit()
        return int(result.rowcount or 0)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning(f"[auth] could not purge revocations: {e}")
        return 0
