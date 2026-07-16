"""normalize_db_url: consume CloudNativePG's URI verbatim (M7-P4).

The chart wires DATABASE_URL straight from the operator-generated `pg-app`
Secret, whose `uri` key is a bare `postgresql://…`. SQLAlchemy maps that scheme
to psycopg2 — not installed here — so Settings normalises it to psycopg3.
"""
from app.core.config import Settings, normalize_db_url


def test_bare_postgresql_scheme_becomes_psycopg3():
    out = normalize_db_url("postgresql://fa_app:pw@pg-rw:5432/finance_alert")
    assert out == "postgresql+psycopg://fa_app:pw@pg-rw:5432/finance_alert"


def test_only_the_scheme_is_rewritten():
    # a password containing the literal scheme text must not be mangled
    out = normalize_db_url("postgresql://u:postgresql://x@h:5432/db")
    assert out.startswith("postgresql+psycopg://u:postgresql://x@h:5432/db")
    assert out.count("postgresql+psycopg://") == 1


def test_explicit_driver_untouched():
    url = "postgresql+psycopg://u:pw@h:5432/db"
    assert normalize_db_url(url) == url


def test_sqlite_untouched():
    assert normalize_db_url("sqlite:///./data/app.db") == "sqlite:///./data/app.db"


def test_settings_validator_applies_normalization(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:pw@pg-rw:5432/finance_alert")
    s = Settings()
    assert s.database_url == "postgresql+psycopg://u:pw@pg-rw:5432/finance_alert"
