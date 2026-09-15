"""stock_setups.tone: da 8 a 16 caratteri

FA-061 ha dato a `squeeze_expansion` un terzo tono, `undetermined`, che ha 12
caratteri. La colonna ne teneva 8. Su Postgres ogni scrittura di quel valore
solleva `StringDataRightTruncation`, la transazione resta abortita e la
scansione non avanza piu': **dalle 19:53 UTC del 2026-09-14 tutte le scansioni
sono fallite**, la prima due minuti dopo il rilascio. In produzione non esisteva
una sola riga con quel tono.

⚠️ SQLite la lunghezza di un VARCHAR non la fa rispettare, quindi la suite
intera era verde. Il test che lo riproduce sta nella corsia Postgres.

Allargare un `varchar` su Postgres tocca solo il catalogo: nessuna riscrittura
della tabella, nessun blocco lungo.

⚠️ SUL RIPRISTINO. Lo schema di destinazione non puo' contenere
`undetermined`, e le alternative a rifiutare sono tutte peggiori: troncarlo in
`undeterm` produce un tono che nessuno riconosce, e riscriverlo in `bull` o
`bear` e' esattamente l'invenzione di una direzione che FA-061 ha tolto. Quindi
il `downgrade` RIFIUTA se trova righe che non entrano, e dice quante sono.
Su Postgres la migrazione gira in una transazione, quindi il rifiuto non lascia
lo schema a meta'.

Revision ID: 5e2f0b7c9d41
Revises: 78d64d497ae0
Create Date: 2026-09-15
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5e2f0b7c9d41"
down_revision: str | Sequence[str] | None = "78d64d497ae0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("stock_setups") as batch:
        batch.alter_column(
            "tone",
            existing_type=sa.String(8),
            type_=sa.String(16),
            existing_nullable=False,
        )


def downgrade() -> None:
    troppo_lunghi = op.get_bind().execute(
        sa.text("SELECT count(*) FROM stock_setups WHERE length(tone) > 8")
    ).scalar_one()
    if troppo_lunghi:
        raise RuntimeError(
            f"stock_setups: {troppo_lunghi} righe hanno un tono piu' lungo di 8 "
            f"caratteri (es. 'undetermined') e non entrano nello schema di "
            f"destinazione. Troncarle o riscriverle in bull/bear inventerebbe "
            f"una direzione: decidi tu cosa farne, poi ripeti il downgrade."
        )
    with op.batch_alter_table("stock_setups") as batch:
        batch.alter_column(
            "tone",
            existing_type=sa.String(16),
            type_=sa.String(8),
            existing_nullable=False,
        )
