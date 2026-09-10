"""revoked sessions table

The revocation list lived in a process dict, so a restart un-revoked every
token for the rest of its `session_max_age_days` (7). A restart is not a rare
event on this branch: every deploy is one and the GitOps loop deploys on every
push.

Only the SHA-256 digest of a token is stored, never the token, so a row is
useless to anyone who reads the table -- it can answer "has this exact token
been revoked" and cannot produce a token.

Revision ID: 50c3faa68285
Revises: 8fc285de13e2
Create Date: 2026-09-10

"""
import sqlalchemy as sa

from alembic import op

revision = "50c3faa68285"
down_revision = "8fc285de13e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "revoked_sessions",
        # The digest is the identity: revoking the same token twice must not
        # create a second row.
        sa.Column("token_hash", sa.String(length=64), primary_key=True),
        # The token's own expiry. Past it the row is dead weight; startup
        # purges rather than accumulating an audit trail, which is not what
        # this table is for.
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "revoked_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )
    # The purge and the startup load both filter on expiry, and nothing else
    # ever queries this table by anything but the primary key.
    op.create_index(
        "ix_revoked_sessions_expires_at", "revoked_sessions", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_revoked_sessions_expires_at", table_name="revoked_sessions")
    op.drop_table("revoked_sessions")
