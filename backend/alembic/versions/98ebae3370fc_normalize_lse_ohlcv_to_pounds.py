"""normalize_lse_ohlcv_to_pounds

Revision ID: 98ebae3370fc
Revises: fdf9a913832b
Create Date: 2026-05-08 18:13:49.974020

For LSE-listed stocks (ticker ending in .L), divide every ohlcv_daily
{open, high, low, close} by 100 to convert from pence to pounds. Set
the new `stocks.ohlcv_in_pounds` flag to TRUE so future runs are no-ops
and so ohlcv_service._upsert_one_stock can skip an additional check.

EXCLUSION LIST (per audit `docs/superpowers/audits/2026-05-08-price-units-audit.md`):
the following .L tickers are quoted natively in GBP (not GBp) by yfinance
and their existing ohlcv_daily rows are ALREADY in pounds. They must NOT
be scaled -- doing so would corrupt their data. They are flagged
ohlcv_in_pounds = 1 directly without touching their OHLCV.

  CPG.L  - Compass Group     (29.30 pounds, ratio ~1.00 vs live_quote)
  IHG.L  - InterContinental  (149.35 pounds, ratio ~1.00)
  MTLN.L - Metalrota          (37.00 pounds, ratio ~1.02)

Idempotent: WHERE ohlcv_in_pounds = 0 ensures re-runs are no-ops.

Side effect: drops stock_scores rows for the 96 SCALED tickers, so the
next scan_alerts run rebuilds them against pounds-scale OHLCV. The 3
outliers' scores were already correct and are kept.

See docs/superpowers/specs/2026-05-08-price-units-data-integrity-design.md
Phase 3.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '98ebae3370fc'
down_revision: Union[str, Sequence[str], None] = 'fdf9a913832b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tickers that are LSE-listed but quoted natively in GBP (not GBp).
# Their existing ohlcv_daily rows are already in pounds -- skip scaling.
ALREADY_IN_POUNDS_LSE: tuple[str, ...] = ("CPG.L", "IHG.L", "MTLN.L")


def upgrade() -> None:
    """Upgrade schema."""
    # 1) Add the flag column to stocks (default 0 = needs backfill).
    with op.batch_alter_table("stocks") as batch_op:
        batch_op.add_column(
            sa.Column(
                "ohlcv_in_pounds", sa.Boolean(),
                nullable=False, server_default=sa.text("0"),
            )
        )

    conn = op.get_bind()

    # 2) Mark the 3 already-in-pounds outliers as flag=1 without scaling.
    if ALREADY_IN_POUNDS_LSE:
        placeholders = ",".join(f":t{i}" for i in range(len(ALREADY_IN_POUNDS_LSE)))
        params = {f"t{i}": v for i, v in enumerate(ALREADY_IN_POUNDS_LSE)}
        conn.execute(sa.text(
            f"UPDATE stocks SET ohlcv_in_pounds = 1 "
            f"WHERE ticker IN ({placeholders}) AND ohlcv_in_pounds = 0"
        ), params)

    # 3) Backfill: every other .L stock with flag=0 gets O/H/L/C divided by 100.
    affected = conn.execute(sa.text(f"""
        SELECT id FROM stocks
        WHERE ticker LIKE '%.L'
          AND ohlcv_in_pounds = 0
          AND ticker NOT IN ({",".join(repr(t) for t in ALREADY_IN_POUNDS_LSE)})
    """)).fetchall()
    affected_ids = [row[0] for row in affected]

    for stock_id in affected_ids:
        conn.execute(sa.text("""
            UPDATE ohlcv_daily
            SET open  = open  / 100.0,
                high  = high  / 100.0,
                low   = low   / 100.0,
                close = close / 100.0
            WHERE stock_id = :sid
        """), {"sid": stock_id})
        conn.execute(sa.text(
            "UPDATE stocks SET ohlcv_in_pounds = 1 WHERE id = :sid"
        ), {"sid": stock_id})

    # 4) Clear stale stock_scores for the SCALED stocks only. The 3 outliers'
    #    scores were already correct and stay.
    if affected_ids:
        placeholders = ",".join(f":id{i}" for i in range(len(affected_ids)))
        params = {f"id{i}": v for i, v in enumerate(affected_ids)}
        conn.execute(
            sa.text(f"DELETE FROM stock_scores WHERE stock_id IN ({placeholders})"),
            params,
        )


def downgrade() -> None:
    """Reverse the backfill: multiply scaled rows by 100 and drop the flag.

    Note: stock_scores rows that were dropped on upgrade are NOT restored
    (they get recomputed by scan_alerts). The 3 outliers (CPG.L, IHG.L,
    MTLN.L) had their flag flipped without scaling, so the inverse is just
    flag=0 -- no multiplication.
    """
    conn = op.get_bind()
    rows = conn.execute(sa.text(f"""
        SELECT id FROM stocks
        WHERE ticker LIKE '%.L'
          AND ohlcv_in_pounds = 1
          AND ticker NOT IN ({",".join(repr(t) for t in ALREADY_IN_POUNDS_LSE)})
    """)).fetchall()
    for (stock_id,) in rows:
        conn.execute(sa.text("""
            UPDATE ohlcv_daily
            SET open  = open  * 100.0,
                high  = high  * 100.0,
                low   = low   * 100.0,
                close = close * 100.0
            WHERE stock_id = :sid
        """), {"sid": stock_id})

    with op.batch_alter_table("stocks") as batch_op:
        batch_op.drop_column("ohlcv_in_pounds")
