"""Idempotent first-run setup: ensure dirs, secret, migrations, seed, admin user."""
import secrets
from pathlib import Path

from loguru import logger

from app.core.config import ensure_data_dir, settings
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
    # The DB upsert lives in auth_service so the app's boot path (lifespan)
    # shares the exact same logic instead of mirroring it here.
    from app.services.auth_service import ensure_admin_user as _ensure

    action = _ensure()
    if action:
        logger.info(f"Admin user {settings.admin_username!r} {action}.")


def main() -> None:
    ensure_data_dir()
    ensure_secret_key()
    apply_migrations()
    seed_module.run()
    ensure_admin_user()
    logger.info("Bootstrap complete.")


if __name__ == "__main__":
    main()
