"""provenienza: versione delle regole su conversioni ed esiti

Revision ID: d9e4b6a1c7f2
Revises: c4f1a7d20e93
Create Date: 2026-09-16

Negli 8.554 alert del motore nessuno snapshot portava una versione delle
regole, e nessuna riga d'esito il metodo con cui era stata etichettata: una
modifica al motore mescolava in silenzio le popolazioni di prima e di dopo.

Solo colonne nullable e nessun riempimento: lo storico resta NULL, cioe'
dichiaratamente senza versione. Scriverci la versione di oggi affermerebbe una
regola che quelle righe non hanno necessariamente seguito. La versione vive in
`app/core/provenance.py`; l'alert la porta nello snapshot JSON, che non chiede
schema.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d9e4b6a1c7f2"
down_revision: str | None = "c4f1a7d20e93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("signal_outcomes") as batch:
        batch.add_column(sa.Column("method_version", sa.String(16), nullable=True))
    with op.batch_alter_table("stock_setups") as batch:
        batch.add_column(sa.Column("conversion_version", sa.String(16), nullable=True))
        batch.add_column(sa.Column("outcome_method_version", sa.String(16), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("stock_setups") as batch:
        batch.drop_column("outcome_method_version")
        batch.drop_column("conversion_version")
    with op.batch_alter_table("signal_outcomes") as batch:
        batch.drop_column("method_version")
