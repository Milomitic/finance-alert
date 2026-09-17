"""plan_outcomes: la gara fra stop e target

Revision ID: 23dd791cdf51
Revises: d9e4b6a1c7f2
Create Date: 2026-09-18

Il magazzino degli esiti di PIANO, accanto a `signal_outcomes` e non dentro.

La ragione e' temporale prima che concettuale. Una riga di `signal_outcomes`
nasce solo quando l'orizzonte fisso del detector e' trascorso — per
`analyst_momentum` sono 63 sedute — mentre un esito di piano si risolve quando
stop o target vengono toccati, di regola molto prima. Appendere queste colonne
a quella tabella le farebbe aspettare l'orizzonte, cioe' riprodurrebbe
esattamente il difetto che questa tabella esiste per chiudere.

Tabella NUOVA e nessun riempimento: nasce vuota e la maturazione la riempie da
li' in avanti. Il ricalcolo dello storico e' un passo separato e dichiarato,
perche' scrivere righe all'indietro dentro una migrazione le renderebbe
indistinguibili da quelle vere.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "23dd791cdf51"
down_revision: str | None = "d9e4b6a1c7f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plan_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alert_id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("detector", sa.String(64), nullable=False),
        sa.Column("signal_date", sa.Date(), nullable=False),
        sa.Column("tone", sa.String(8), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        # La geometria congelata: e' tarata, e quelle costanti cambieranno.
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("entry", sa.Float(), nullable=False),
        sa.Column("stop", sa.Float(), nullable=False),
        sa.Column("tp1", sa.Float(), nullable=False),
        sa.Column("tp2", sa.Float(), nullable=True),
        sa.Column("r", sa.Float(), nullable=False),
        # L'esito. ⚠️ String(16) e non String(8): "ambigua" e "scaduto" stanno
        # in otto per un pelo, e in questo repo una costante piu' lunga della
        # sua colonna ha gia' fermato ogni scansione per ~19 ore. Un test
        # confronta le costanti con questa lunghezza e gira su ogni push.
        sa.Column("esito", sa.String(16), nullable=False),
        sa.Column("resolved_date", sa.Date(), nullable=False),
        sa.Column("bars_to_outcome", sa.Integer(), nullable=False),
        sa.Column("r_multiple", sa.Float(), nullable=False),
        sa.Column("mae_r", sa.Float(), nullable=False),
        sa.Column("mfe_r", sa.Float(), nullable=False),
        sa.Column("tp2_reached", sa.Boolean(), nullable=False,
                  # ⚠️ `false()` e non `sa_text("0")`: e' dialect-aware e rende
                  # `false` su Postgres, dove un DEFAULT 0 su una colonna
                  # booleana e' un errore di tipo. La stessa nota sta su
                  # `stocks.ohlcv_in_pounds`, dove e' gia' costata una volta.
                  server_default=sa.false()),
        sa.Column("source", sa.String(16), nullable=False,
                  server_default=sa.text("'emesso'")),
        sa.Column("method_version", sa.String(16), nullable=True),
        sa.Column("matured_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="CASCADE"),
    )
    # Un esito per alert, imposto dal database: la maturazione gira a ogni
    # scansione e un controllo «esiste gia'?» in Python ha una finestra di
    # corsa. Righe doppie conterebbero due volte lo stesso trade.
    op.create_index("ix_plan_outcomes_alert", "plan_outcomes", ["alert_id"], unique=True)
    op.create_index("ix_plan_outcomes_detector", "plan_outcomes", ["detector"])
    op.create_index("ix_plan_outcomes_signal_date", "plan_outcomes", ["signal_date"])


def downgrade() -> None:
    # ⚠️ Il ritorno si prova, non si presume: una migrazione che non si
    # ripercorre all'indietro va scoperta adesso e non durante un ripristino —
    # il drill del lunedi' esiste per questa ragione.
    #
    # Qui perdere dati e' la scelta GIUSTA e va detta: `plan_outcomes` e'
    # ricalcolabile per intero dagli alert e dalle barre, quindi tornare
    # indietro non distrugge niente di irrecuperabile.
    op.drop_index("ix_plan_outcomes_signal_date", table_name="plan_outcomes")
    op.drop_index("ix_plan_outcomes_detector", table_name="plan_outcomes")
    op.drop_index("ix_plan_outcomes_alert", table_name="plan_outcomes")
    op.drop_table("plan_outcomes")
