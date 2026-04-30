"""Password hashing and signed session tokens."""
import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import settings

_SALT = "finance-alert-session-v1"


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


def create_session_token(username: str) -> str:
    return _serializer().dumps({"u": username})


def read_session_token(token: str, max_age_seconds: int | None = None) -> str | None:
    """Return the username if valid, None if signature is invalid, raise ValueError if expired."""
    if max_age_seconds is None:
        max_age_seconds = settings.session_max_age_days * 86400
    try:
        data = _serializer().loads(token, max_age=max_age_seconds)
    except SignatureExpired as e:
        raise ValueError("Session expired") from e
    except BadSignature:
        return None
    return data.get("u")
