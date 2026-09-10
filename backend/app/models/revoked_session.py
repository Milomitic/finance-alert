"""Session tokens revoked by an explicit logout.

The revocation list lived in a process dict, so a pod restart un-revoked every
token. `session_max_age_days` is 7, which is how long a token someone
deliberately logged out of stayed usable — and a restart is not a rare event
here: every deploy is one, and the GitOps loop deploys on every push.

⚠️ Only the SHA-256 DIGEST of a token is stored, never the token. A row here is
therefore useless to anyone who reads the table: it can answer "has this exact
token been revoked" and cannot produce a token. The same rule the in-memory
list already followed, and the reason this table can live in the ordinary
application database instead of needing a secret store.

Rows are self-expiring. A revoked token stops being dangerous the moment its
own signature expires, so `expires_at` is the token's natural expiry and
anything past it is deleted rather than kept — an append-only audit trail of
who logged out is not what this is for.
"""
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class RevokedSession(Base):
    __tablename__ = "revoked_sessions"

    # SHA-256 hex digest of the session token. Primary key: revoking the same
    # token twice is not an error and must not create a second row.
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    # When the token would have expired on its own. Past this, the row is
    # dead weight and the purge removes it.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
