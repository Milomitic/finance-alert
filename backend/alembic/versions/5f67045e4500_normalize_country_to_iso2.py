"""normalize country to iso2

Revision ID: 5f67045e4500
Revises: 91d8c40e0e08
Create Date: 2026-07-08 22:30:44.492364

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5f67045e4500'
down_revision: Union[str, Sequence[str], None] = '91d8c40e0e08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Full-name → ISO-2 for the non-ISO values found in the live catalog
# (2026-07-08 census). 'US'=632 coexisted with 'United States'=32 → the
# screener's exact-match country filter silently missed 32 US stocks.
# Cayman Islands / South Africa map to their ISO-2 (KY/ZA) even though no
# ISO twin exists yet — consistency prevents a future split.
_COUNTRY_MAP = {
    "United States": "US",
    "Ireland": "IE",
    "Cayman Islands": "KY",
    "South Africa": "ZA",
}


def upgrade() -> None:
    """One-off repair; the ingestion-side normalization (preventing future
    full-name inserts) lands with lane SCR-2's code."""
    bind = op.get_bind()
    for src, dst in _COUNTRY_MAP.items():
        bind.execute(
            sa.text("UPDATE stocks SET country = :dst WHERE country = :src"),
            {"src": src, "dst": dst},
        )


def downgrade() -> None:
    """Data repair — not reversible."""
    pass
