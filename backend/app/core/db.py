"""SQLAlchemy engine, session, and Base."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


_IS_SQLITE = settings.database_url.startswith("sqlite")

# Pool tuning applies to Postgres only. SQLite is single-writer and local, so
# a bigger pool buys nothing there and would change every test's behaviour for
# no reason.
_pool_kwargs: dict = {}
if not _IS_SQLITE:
    _pool_kwargs = {
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout_seconds,
        # CloudNativePG can fail the instance over, and a pooled connection to
        # the old primary then looks fine until it is used. pre_ping spends one
        # trivial round-trip to find out first — far cheaper than surfacing a
        # dead connection as a 500 to the user.
        "pool_pre_ping": True,
        # Recycle before anything upstream (Postgres idle timeouts, a k8s
        # NetworkPolicy conntrack entry) decides to drop a long-idle socket
        # without telling us.
        "pool_recycle": 1800,
    }

engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False} if _IS_SQLITE else {},
    **_pool_kwargs,
)


if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
        # Wait up to 15s for a write lock instead of failing instantly. With WAL
        # this lets the small periodic writers (cleanup_orphan_scans, the live
        # sweep) wait out a scan's brief write bursts rather than raise
        # 'database is locked'. Defense-in-depth behind the single-scan mutex.
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
