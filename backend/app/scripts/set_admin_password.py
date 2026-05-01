"""Set the admin password: hash it, write to .env, create/update the user.

Usage:
    uv run python -m app.scripts.set_admin_password
    uv run python -m app.scripts.set_admin_password --password "MyPassword123"

The --password flag is useful when running through wrappers (just, cmd /C, etc.)
where getpass may not read terminal input reliably.
"""
import argparse
import getpass
from pathlib import Path

import bcrypt
from loguru import logger
from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.models import User

MIN_PASSWORD_LENGTH = 8


def _write_hash_to_env(hashed: str) -> Path:
    """Update ADMIN_PASSWORD_HASH= in ./.env (relative to CWD).

    Creates the file if missing. Returns the path written.
    """
    env_path = Path(".env")
    if not env_path.exists():
        # Try the repo-root sibling .env.example as a fallback template.
        template = Path("../.env.example")
        if template.exists():
            env_path.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            env_path.write_text("", encoding="utf-8")

    text = env_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    new_lines: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith("ADMIN_PASSWORD_HASH="):
            new_lines.append(f"ADMIN_PASSWORD_HASH={hashed}")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.append(f"ADMIN_PASSWORD_HASH={hashed}")
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return env_path.resolve()


def _upsert_admin_user(username: str, hashed: str) -> str:
    """Create or update the admin user. Returns 'created' or 'updated'."""
    db = SessionLocal()
    try:
        existing = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if existing is None:
            db.add(User(username=username, password_hash=hashed))
            db.commit()
            return "created"
        existing.password_hash = hashed
        db.commit()
        return "updated"
    finally:
        db.close()


def _prompt_password() -> str:
    """Prompt twice and validate. Loops until a valid password is entered."""
    while True:
        pw = getpass.getpass("New admin password (min 8 chars): ")
        if len(pw) < MIN_PASSWORD_LENGTH:
            print(f"Too short ({len(pw)} chars). Try again.")
            continue
        pw2 = getpass.getpass("Confirm: ")
        if pw != pw2:
            print("Passwords do not match. Try again.")
            continue
        return pw


def main() -> None:
    parser = argparse.ArgumentParser(description="Set the Finance Alert admin password")
    parser.add_argument(
        "--password",
        help=(
            "Password to set non-interactively. If omitted, prompts via getpass. "
            "Use this when running through wrappers (just, cmd /C) where getpass "
            "may not read terminal input reliably."
        ),
    )
    args = parser.parse_args()

    if args.password:
        if len(args.password) < MIN_PASSWORD_LENGTH:
            raise SystemExit(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
        pw = args.password
    else:
        pw = _prompt_password()

    hashed = bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

    env_path = _write_hash_to_env(hashed)
    logger.info(f"ADMIN_PASSWORD_HASH written to {env_path}")

    username = settings.admin_username or "admin"
    action = _upsert_admin_user(username, hashed)
    logger.info(f"Admin user {username!r} {action} in DB.")
    print(f"\nDone. Log in as {username!r} with the password you just entered.")


if __name__ == "__main__":
    main()
