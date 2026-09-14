"""Alembic environment configured for SQLAlchemy 2.0 + our settings."""
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401  (register all models)
from alembic import context
from app.core.config import settings
from app.core.db import Base

config = context.config
# ⚠️ Questa riga SOVRASCRIVE qualunque `sqlalchemy.url` il chiamante abbia
# impostato, ed e' deliberato: `alembic.ini` la lascia vuota perche' la
# configurazione del database ha un proprietario solo, `settings`.
#
# Ne segue una cosa che costa un'ora a chi non la sa: per far girare una
# migrazione contro un ALTRO database non serve a niente passare l'url a
# `Config` — bisogna cambiare `settings.database_url`. Vedi
# `tests/test_postgres_integration.py`, dove la prima versione del giro di
# migrazioni ci e' cascata e PASSAVA misurando niente.
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
