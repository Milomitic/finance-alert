"""institutional holdings repair and unique

Revision ID: 390120b342e6
Revises: 9fc31644b13b
Create Date: 2026-07-07 12:46:39.412258

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '390120b342e6'
down_revision: Union[str, Sequence[str], None] = '9fc31644b13b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Data repair + integrity for institutional_holdings (audit 2026-07-07).

    Order matters:
    1. DOT-TICKER NORMALIZE: BRK.B/BF.B-style tickers → dashed form, but only
       when the dashed form exists in the catalog (472 candidate rows) — the
       June catalog rename (BRK-B etc.) severed fund↔stock joins both ways.
    2. DEDUP (filing_id, ticker): merge duplicates (sum shares/value/pct into
       the lowest id, delete the rest) — 108 pre-existing groups, plus any
       collisions minted by step 1.
    3. ACTION REPAIR: holdings of SINGLE-filing funds get action=NULL and
       qoq_change_pct=NULL — first-snapshot rows are not purchases (61.5k
       rows seeded before the compute_qoq fix claimed action='new'; the
       'Acquisti recenti' card sorted Vanguard's whole book as fresh buys).
    4. UNIQUE(filing_id, ticker) index so the docstring promise is enforced.
    """
    bind = op.get_bind()

    # 1. Dot → dash where the dashed ticker is a real catalog symbol.
    bind.execute(sa.text(
        """
        UPDATE institutional_holdings
        SET ticker = REPLACE(ticker, '.', '-')
        WHERE ticker LIKE '%.%'
          AND ticker NOT LIKE 'CUSIP:%'
          AND REPLACE(ticker, '.', '-') IN (SELECT ticker FROM stocks)
        """
    ))

    # 2. Merge duplicates: keep MIN(id), sum the numeric columns, drop the rest.
    dups = bind.execute(sa.text(
        """
        SELECT filing_id, ticker, MIN(id) AS keep_id,
               SUM(shares) AS s, SUM(value_usd) AS v, SUM(portfolio_pct) AS p
        FROM institutional_holdings
        GROUP BY filing_id, ticker
        HAVING COUNT(*) > 1
        """
    )).fetchall()
    for filing_id, ticker, keep_id, s, v, p in dups:
        bind.execute(
            sa.text(
                "UPDATE institutional_holdings "
                "SET shares = :s, value_usd = :v, portfolio_pct = :p "
                "WHERE id = :keep"
            ),
            {"s": s, "v": v, "p": p, "keep": keep_id},
        )
        bind.execute(
            sa.text(
                "DELETE FROM institutional_holdings "
                "WHERE filing_id = :f AND ticker = :t AND id != :keep"
            ),
            {"f": filing_id, "t": ticker, "keep": keep_id},
        )

    # 3. First-snapshot rows of single-filing funds are NOT trades.
    bind.execute(sa.text(
        """
        UPDATE institutional_holdings
        SET action = NULL, qoq_change_pct = NULL
        WHERE filing_id IN (
            SELECT f.id FROM institutional_filings f
            WHERE (SELECT COUNT(*) FROM institutional_filings f2
                   WHERE f2.institutional_id = f.institutional_id) = 1
        )
        """
    ))

    # 4. Enforce what the model docstring already promised.
    op.create_index(
        "uq_inst_holdings_filing_ticker",
        "institutional_holdings",
        ["filing_id", "ticker"],
        unique=True,
    )


def downgrade() -> None:
    """Data repair is not reversible; only the index is dropped."""
    op.drop_index(
        "uq_inst_holdings_filing_ticker", table_name="institutional_holdings"
    )
