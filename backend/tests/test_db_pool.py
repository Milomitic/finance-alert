"""Connection-pool sizing.

Production ran on SQLAlchemy's defaults (5 + 10) until a QueuePool timeout
surfaced as a 500. The cause is not database load: every endpoint is a sync
`def`, so it holds its connection for the whole request including the seconds
spent waiting on yfinance. These tests pin the two properties that keep that
from recurring — enough connections, and never more than Postgres allows.
"""
from app.core.config import Settings

# CloudNativePG is configured with max_connections=50. Everything the app takes
# is unavailable to backups, monitoring, and a human with psql — so the app's
# ceiling has to stay meaningfully below it.
_PG_MAX_CONNECTIONS = 50
_RESERVED_FOR_OPERATIONS = 10


def test_the_pool_is_larger_than_sqlalchemys_default():
    """15 was measured to be too few. A regression to the default would
    reintroduce the exact 500 this was found from."""
    s = Settings()
    assert s.db_pool_size + s.db_max_overflow > 15


def test_the_pool_cannot_exhaust_postgres():
    """Raising the app's pool past the server's ceiling does not fix
    exhaustion, it moves it: instead of the app queuing, Postgres starts
    refusing connections — including the operator's."""
    s = Settings()
    assert (
        s.db_pool_size + s.db_max_overflow
        <= _PG_MAX_CONNECTIONS - _RESERVED_FOR_OPERATIONS
    ), "the pool must leave room for CNPG, backups, monitoring and a psql session"


def test_sqlite_is_left_alone():
    """SQLite is single-writer and local; pool sizing there is meaningless and
    would alter every test's behaviour for nothing."""
    from app.core import db as db_mod

    if db_mod._IS_SQLITE:
        assert db_mod._pool_kwargs == {}


def test_postgres_gets_pre_ping_and_recycle():
    """A CNPG failover leaves pooled sockets pointing at the old primary; they
    look healthy until used. Both guards must be on for the Postgres path."""
    import app.core.db as db_mod

    if not db_mod._IS_SQLITE:
        assert db_mod._pool_kwargs["pool_pre_ping"] is True
        assert db_mod._pool_kwargs["pool_recycle"] > 0
