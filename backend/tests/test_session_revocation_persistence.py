"""A logout must still hold after the pod restarts.

The revocation list lived in a process dict. `session_max_age_days` is 7, so a
token someone deliberately logged out of came back to life on the next restart
and stayed usable for up to a week. A restart is not a rare event on this
branch: every deploy is one, and the GitOps loop deploys on every push.

The test that matters is the last class here, which simulates the restart by
clearing the in-memory set and rehydrating from the table -- exactly what
`main._hydrate_revoked_sessions` does at boot. Everything above it is the
supporting cast.

⚠️ What this does NOT cover, on purpose: a second replica. A revoke reaches the
database immediately but the other replica's memory only learns about it when
IT restarts. One replica runs today; the honest fix for two is a TTL re-read
or pub/sub, not a test pretending otherwise.
"""
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core import security
from app.core.security import (
    create_session_token,
    hydrate_revoked,
    read_session_token,
    revocation_expiry,
    revoke_session_token,
    token_key,
)
from app.models.revoked_session import RevokedSession
from app.services import session_revocation_service as svc


def _restart() -> None:
    """Everything a process restart does to the revocation list."""
    security._REVOKED.clear()


class TestOnlyTheDigestIsStored:
    def test_the_token_itself_never_reaches_the_table(self, db: Session):
        token = create_session_token("admin")

        svc.persist(db, token_key(token), datetime.now(UTC) + timedelta(days=7))

        rows = db.query(RevokedSession).all()
        assert len(rows) == 1
        # The row must be useless to whoever reads the table: it can confirm a
        # token, not produce one.
        assert token not in rows[0].token_hash
        assert rows[0].token_hash == token_key(token)

    def test_the_digest_has_one_definition(self):
        # `token_key` is public precisely so the persistence layer cannot grow
        # a second one: a revocation written under one and checked under the
        # other would silently never match.
        token = create_session_token("admin")
        assert token_key(token) == security.token_key(token)


class TestRevokingTwiceIsNotAnError:
    def test_a_second_logout_does_not_add_a_row(self, db: Session):
        token = create_session_token("admin")
        expiry = datetime.now(UTC) + timedelta(days=7)

        svc.persist(db, token_key(token), expiry)
        svc.persist(db, token_key(token), expiry)

        assert db.query(RevokedSession).count() == 1


class TestRowsExpireWithTheirToken:
    def test_an_expired_revocation_is_not_loaded(self, db: Session):
        # A revoked token stops being dangerous when its own signature dies.
        svc.persist(db, "a" * 64, datetime.now(UTC) - timedelta(seconds=1))
        svc.persist(db, "b" * 64, datetime.now(UTC) + timedelta(days=7))

        active = svc.load_active(db)

        assert "b" * 64 in active
        assert "a" * 64 not in active

    def test_the_purge_removes_them(self, db: Session):
        svc.persist(db, "a" * 64, datetime.now(UTC) - timedelta(seconds=1))
        svc.persist(db, "b" * 64, datetime.now(UTC) + timedelta(days=7))

        removed = svc.purge_expired(db)

        assert removed == 1
        assert db.query(RevokedSession).count() == 1

    def test_the_expiry_survives_the_round_trip(self, db: Session):
        # ⚠️ SQLite returns naive datetimes and Postgres tz-aware ones. Both
        # mean UTC, and `.timestamp()` on a naive value silently applies the
        # SERVER's local zone — an hour or two of extra or missing revocation,
        # invisible on a UTC machine and wrong on the developer's.
        expiry = datetime.now(UTC) + timedelta(days=7)
        svc.persist(db, "c" * 64, expiry)

        active = svc.load_active(db)

        assert abs(active["c" * 64] - expiry.timestamp()) < 2


class TestTheRevocationSurvivesARestart:
    """The whole point of the table."""

    def test_a_logged_out_token_stays_dead_after_a_restart(self, db: Session):
        token = create_session_token("admin")
        assert read_session_token(token) == "admin"

        # The logout: memory + table, exactly as the router does it.
        expires_at = revoke_session_token(token)
        svc.persist(db, token_key(token), datetime.fromtimestamp(expires_at, tz=UTC))
        assert read_session_token(token) is None

        _restart()
        # Without the rehydrate below the token is alive again — which is the
        # bug this closes, and it is asserted so the setup cannot be vacuous.
        assert read_session_token(token) == "admin"

        hydrate_revoked(svc.load_active(db))

        assert read_session_token(token) is None

    def test_a_token_that_was_never_revoked_still_works(self, db: Session):
        # The negative control. Without it, a rehydrate that revoked
        # everything would pass every assertion above.
        good = create_session_token("admin")
        bad = create_session_token("admin")
        expires_at = revoke_session_token(bad)
        svc.persist(db, token_key(bad), datetime.fromtimestamp(expires_at, tz=UTC))

        _restart()
        hydrate_revoked(svc.load_active(db))

        assert read_session_token(bad) is None
        assert read_session_token(good) == "admin"

    def test_hydration_merges_instead_of_replacing(self, db: Session):
        # A token revoked between process start and the hydrate call must not
        # be forgotten by it — startup is not instantaneous and the app serves
        # requests from the moment it binds.
        early = create_session_token("admin")
        revoke_session_token(early)
        svc.persist(db, "d" * 64, datetime.now(UTC) + timedelta(days=7))

        hydrate_revoked(svc.load_active(db))

        assert read_session_token(early) is None


class TestALogoutIsNeverBlockedByTheDatabase:
    def test_a_failed_write_does_not_raise(self, db: Session, monkeypatch):
        # Refusing to log someone out because a table is unreachable is the
        # worse failure: the cookie must still be cleared and the token must
        # still leave the in-memory set.
        def boom(*_a, **_k):
            raise RuntimeError("db down")

        monkeypatch.setattr(db, "add", boom)

        svc.persist(db, "e" * 64, datetime.now(UTC) + timedelta(days=7))

    def test_the_in_memory_revoke_still_took_effect(self, db: Session, monkeypatch):
        token = create_session_token("admin")
        revoke_session_token(token)

        monkeypatch.setattr(db, "add", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError()))
        svc.persist(db, token_key(token), datetime.now(UTC) + timedelta(days=7))

        assert read_session_token(token) is None


class TestTheExpiryIsComputedOnce:
    def test_revoke_returns_the_value_it_stored(self):
        # The router persists what `revoke_session_token` returns rather than
        # calling `revocation_expiry()` again a few milliseconds later, so the
        # memory and the row can never disagree about when it lapses.
        token = create_session_token("admin")

        returned = revoke_session_token(token)

        assert abs(returned - revocation_expiry()) < 2
        assert security._REVOKED[token_key(token)] == returned
