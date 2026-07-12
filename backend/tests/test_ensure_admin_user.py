"""ensure_admin_user: provisioning boot-time dell'admin da ADMIN_PASSWORD_HASH.

La funzione è il percorso 12-factor con cui un deploy fresco (PVC vuoto su K8s)
diventa loggabile senza passi manuali: il chart inietta l'hash bcrypt via
Secret e il lifespan la invoca all'avvio. Qui si verifica l'upsert idempotente.
"""
from sqlalchemy import select

from app.core.config import settings
from app.models import User
from app.services.auth_service import ensure_admin_user

HASH_A = "$2b$12$" + "a" * 53
HASH_B = "$2b$12$" + "b" * 53


def test_noop_when_env_unset(db, monkeypatch):
    monkeypatch.setattr(settings, "admin_password_hash", "")
    assert ensure_admin_user() is None
    assert db.execute(select(User)).scalars().all() == []


def test_creates_admin_when_missing(db, monkeypatch):
    monkeypatch.setattr(settings, "admin_username", "admin")
    monkeypatch.setattr(settings, "admin_password_hash", HASH_A)
    assert ensure_admin_user() == "created"
    user = db.execute(select(User).where(User.username == "admin")).scalar_one()
    assert user.password_hash == HASH_A


def test_updates_hash_when_changed(db, monkeypatch):
    db.add(User(username="admin", password_hash=HASH_A))
    db.commit()
    monkeypatch.setattr(settings, "admin_username", "admin")
    monkeypatch.setattr(settings, "admin_password_hash", HASH_B)
    assert ensure_admin_user() == "updated"
    db.expire_all()
    user = db.execute(select(User).where(User.username == "admin")).scalar_one()
    assert user.password_hash == HASH_B


def test_noop_when_in_sync(db, monkeypatch):
    db.add(User(username="admin", password_hash=HASH_A))
    db.commit()
    monkeypatch.setattr(settings, "admin_username", "admin")
    monkeypatch.setattr(settings, "admin_password_hash", HASH_A)
    assert ensure_admin_user() is None
