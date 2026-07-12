"""Authentication business logic."""
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.models import User


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def ensure_admin_user() -> str | None:
    """Provision/refresh the admin row from ADMIN_PASSWORD_HASH (12-factor).

    Returns "created" / "updated" / None (no-op). Called at boot (lifespan) so
    a fresh deployment with an empty DB gets its login without a manual step —
    the K8s chart feeds the env var via its Secret. Also the workhorse behind
    ``app.scripts.bootstrap.ensure_admin_user``.

    Imports resolved at call time on purpose: tests monkeypatch
    ``app.core.db.SessionLocal`` onto an isolated engine, and a module-level
    binding would freeze the production one.
    """
    from app.core.config import settings
    from app.core.db import SessionLocal

    if not settings.admin_password_hash:
        return None
    db = SessionLocal()
    try:
        user = db.execute(
            select(User).where(User.username == settings.admin_username)
        ).scalar_one_or_none()
        if user is None:
            db.add(
                User(
                    username=settings.admin_username,
                    password_hash=settings.admin_password_hash,
                )
            )
            db.commit()
            logger.info(f"admin user {settings.admin_username!r} created from ADMIN_PASSWORD_HASH")
            return "created"
        if user.password_hash != settings.admin_password_hash:
            user.password_hash = settings.admin_password_hash
            db.commit()
            logger.info(f"admin user {settings.admin_username!r} hash refreshed from ADMIN_PASSWORD_HASH")
            return "updated"
        return None
    finally:
        db.close()
