"""Idempotent first-run setup: ensure dirs, secret, migrations, seed, admin user."""
import secrets
from pathlib import Path

from loguru import logger
from sqlalchemy import select

from app.core.config import ensure_data_dir, settings
from app.core.db import SessionLocal
from app.models import User
from app.scripts import bootstrap_rules, bootstrap_watchlists
from app.scripts import seed as seed_module


def ensure_secret_key() -> None:
    env_path = Path(".env")
    if not env_path.exists():
        logger.warning(".env file missing; copy .env.example first.")
        return
    text = env_path.read_text(encoding="utf-8")
    if "SECRET_KEY=" in text and "SECRET_KEY=\n" not in text and "SECRET_KEY=$" not in text:
        # already set (non-empty)
        for line in text.splitlines():
            if line.startswith("SECRET_KEY=") and line.split("=", 1)[1].strip():
                return
    new_key = secrets.token_urlsafe(48)
    new_text = []
    replaced = False
    for line in text.splitlines():
        if line.startswith("SECRET_KEY="):
            new_text.append(f"SECRET_KEY={new_key}")
            replaced = True
        else:
            new_text.append(line)
    if not replaced:
        new_text.append(f"SECRET_KEY={new_key}")
    env_path.write_text("\n".join(new_text) + "\n", encoding="utf-8")
    logger.info("Generated SECRET_KEY in .env")


def apply_migrations() -> None:
    from alembic.config import Config

    from alembic import command

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")


def ensure_admin_user() -> None:
    if not settings.admin_password_hash:
        logger.warning(
            "ADMIN_PASSWORD_HASH not set. Run: uv run python -m app.scripts.set_admin_password"
        )
        return
    db = SessionLocal()
    try:
        existing = db.execute(
            select(User).where(User.username == settings.admin_username)
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                User(
                    username=settings.admin_username,
                    password_hash=settings.admin_password_hash,
                )
            )
            db.commit()
            logger.info(f"Created admin user: {settings.admin_username}")
        elif existing.password_hash != settings.admin_password_hash:
            existing.password_hash = settings.admin_password_hash
            db.commit()
            logger.info(f"Updated admin password hash for: {settings.admin_username}")
    finally:
        db.close()


def main() -> None:
    ensure_data_dir()
    ensure_secret_key()
    apply_migrations()
    seed_module.run()
    bootstrap_rules.ensure_global_rules()
    ensure_admin_user()
    # Curated watchlists must run AFTER admin user is ensured (the lists
    # need an owner) and AFTER seeds are applied (otherwise tickers
    # resolve as missing).
    bootstrap_watchlists.ensure_curated_watchlists()
    logger.info("Bootstrap complete.")


if __name__ == "__main__":
    main()
