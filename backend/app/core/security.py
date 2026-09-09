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


def _token_key(token: str) -> str:
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


def revoke_session_token(token: str) -> None:
    """Revoke one token until its normal expiry; only a SHA-256 digest is kept."""
    _purge_revoked()
    _REVOKED[_token_key(token)] = time.time() + settings.session_max_age_days * 86400


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
    if _token_key(token) in _REVOKED:
        return None
    if not isinstance(data, dict):
        return None
    username = data.get("u")
    return username if isinstance(username, str) and 0 < len(username) <= 64 else None
