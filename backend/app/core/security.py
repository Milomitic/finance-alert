"""Password hashing and revocable signed session tokens."""
import hashlib
import secrets
import time

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import settings

_SALT = "finance-alert-session-v1"
_REVOKED: dict[str, float] = {}


def _serializer() -> URLSafeTimedSerializer:
    if not settings.secret_key:
        raise RuntimeError("SECRET_KEY is not configured")
    return URLSafeTimedSerializer(settings.secret_key, salt=_SALT)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def token_key(token: str) -> str:
    """The stored identity of a token: its SHA-256 digest, never the token.

    Public because the persistence layer needs the same digest and must not
    re-derive it — two definitions of "the key" would drift and a revocation
    written under one would be checked under the other.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _purge_revoked(now: float | None = None) -> None:
    cutoff = time.time() if now is None else now
    for key, expires_at in list(_REVOKED.items()):
        if expires_at <= cutoff:
            _REVOKED.pop(key, None)


def create_session_token(username: str) -> str:
    # A random nonce makes every login independently revocable, even when the
    # same user logs in from multiple tabs or devices.
    return _serializer().dumps({"u": username, "jti": secrets.token_urlsafe(16)})


def revocation_expiry(now: float | None = None) -> float:
    """Unix seconds at which a revocation stops mattering.

    A revoked token is only dangerous while its own signature is still valid,
    so the list never needs to outlive the token.
    """
    base = time.time() if now is None else now
    return base + settings.session_max_age_days * 86400


def revoke_session_token(token: str) -> float:
    """Revoke one token until its normal expiry; only a SHA-256 digest is kept.

    Returns the expiry so the caller can persist the SAME value rather than
    computing a second one a few milliseconds later.
    """
    _purge_revoked()
    expires_at = revocation_expiry()
    _REVOKED[token_key(token)] = expires_at
    return expires_at


def hydrate_revoked(entries: dict[str, float]) -> int:
    """Load persisted revocations into the in-memory set at startup.

    ⚠️ The in-memory set is the ONLY thing `read_session_token` consults, on
    purpose: it runs on every authenticated request and a per-request SELECT
    to answer a question whose answer is almost always "no" would be a real
    cost. So this is what makes a revocation survive a restart — and every
    deploy is a restart here, on a branch whose GitOps loop deploys on every
    push.

    Merges rather than replaces: a token revoked between process start and
    this call must not be forgotten.
    """
    _REVOKED.update(entries)
    _purge_revoked()
    return len(_REVOKED)


def read_session_token(token: str, max_age_seconds: int | None = None) -> str | None:
    """Return the username if valid and not revoked, raise ValueError if expired."""
    if max_age_seconds is None:
        max_age_seconds = settings.session_max_age_days * 86400
    _purge_revoked()
    try:
        data = _serializer().loads(token, max_age=max_age_seconds)
    except SignatureExpired as e:
        raise ValueError("Session expired") from e
    except BadSignature:
        return None
    if token_key(token) in _REVOKED:
        return None
    if not isinstance(data, dict):
        return None
    username = data.get("u")
    return username if isinstance(username, str) and 0 < len(username) <= 64 else None
