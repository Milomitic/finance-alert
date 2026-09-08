"""Where a stock's technical posture sits among its SECTOR peers.

The Qualità card has carried a sector percentile for a while; the Tecnico lens
never did, and the gap matters because the two answer different questions.

`rel_strength` is ALREADY measured against the whole universe — CLAUDE.md's
worked example is TIT.MI reading 100.0, "the HIGHEST in the whole universe" —
so a universe percentile of it would be a percentile of a percentile, and none
is offered here. The SECTOR rank is the genuinely missing part: a stock can be
unremarkable across the catalogue and still be the strongest name in a weak
sector, and those are different things to know.

Ranking is on the technical COMPOSITE, which is what the card leads with.
"""

from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import Stock, TechnicalScore


def sector_rank(
    db: Session,
    stock_id: int,
    sector: str | None,
    composite: float | None,
) -> tuple[int | None, int | None]:
    """`(rank, peers)` with rank 1 = strongest, or `(None, None)`.

    Ties take the BETTER rank — two stocks at 90.0 are both joint first, not
    first and second, because the alternative makes the answer depend on
    insertion order.

    The peer count comes back beside the rank and is not optional dressing: a
    stock alone in its sector ranks "1 of 1", which is not a ranking at all,
    and only the denominator lets the UI say so instead of showing a proud
    first place. Same rule as the Setups tile that read 100% on six resolved
    setups (CLAUDE.md): a position needs a field.
    """
    if sector is None or composite is None:
        return (None, None)

    peers, stronger = db.execute(
        select(
            func.count(),
            func.sum(case((
                (TechnicalScore.composite > composite)
                & (TechnicalScore.stock_id != stock_id), 1,
            ), else_=0)),
        )
        .select_from(TechnicalScore)
        .join(Stock, Stock.id == TechnicalScore.stock_id)
        .where(Stock.sector == sector)
    ).one()
    if not peers:
        return (None, None)

    return ((stronger or 0) + 1, peers)
