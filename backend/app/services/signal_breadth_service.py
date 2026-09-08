"""Was this signal about this stock, or about the market that morning?

Measured over the live alert table, the answer varies enormously by detector:

    trend_pullback    fires alongside 43 other stocks on average (max 127)
    candle_reversal   29
    gap_and_go         2.7 (max 8)

A `trend_pullback` is therefore almost never idiosyncratic — it is a
market-wide condition that happened to touch this name — while a `gap_and_go`
really is about the stock. The platform has always known this and never said
it, so every alert reads the same whether one stock moved or a hundred did.

⚠️ IT IS CONTEXT, NEVER CONFIRMATION. CLAUDE.md records two independent
studies finding concurrence NULL at h=1/2/3/5 — knowing that forty names did
the same thing does not make the signal better, and it must not touch Forza or
Probabilità. What it changes is what the READER concludes: if the move is
sector-wide, the stock is telling you nothing of its own. That is the whole
value, and it is available precisely because no prediction is attached to it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import case, func, select, tuple_
from sqlalchemy.orm import Session

from app.models import Alert, Stock


@dataclass(frozen=True)
class Breadth:
    """How much company a signal had on the day it fired."""

    others: int
    same_sector: int


def breadth_for(
    db: Session,
    alerts: Sequence[Alert],
    *,
    stock_id: int,
    sector: str | None,
) -> dict[int, Breadth]:
    """Per-alert breadth, keyed by alert id. One query for the whole page.

    Alerts without a `signal_date` are ABSENT from the result rather than
    present with a zero: legacy rows predate the column, and there is no "that
    day" to compare them against. A zero would read as "it fired alone", which
    is a claim the data cannot make.

    ARCHIVED ALERTS ARE COUNTED, deliberately. CLAUDE.md's rule — never filter
    a measurement on a field the USER writes — was learned the expensive way
    when the outcome warehouse ended up showing 19 of its 4,880 rows because
    three consumers excluded archived alerts and archival tracks AGE. Breadth
    is not an efficacy metric, but it would drift identically: "38 other
    stocks" would quietly become "12" months later with nothing having changed
    in the market.
    """
    pairs = {
        (a.signal_name, a.signal_date) for a in alerts if a.signal_date is not None
    }
    if not pairs:
        return {}

    rows = db.execute(
        select(
            Alert.signal_name,
            Alert.signal_date,
            func.count(func.distinct(Alert.stock_id)),
            # NULL for a peer in another sector, so COUNT DISTINCT skips it.
            # With `sector` None nothing matches and the split is 0, which is
            # right: a stock with no sector has no sector peers.
            func.count(
                func.distinct(
                    case((Stock.sector == sector, Alert.stock_id), else_=None)
                )
            ),
        )
        .join(Stock, Stock.id == Alert.stock_id)
        .where(
            tuple_(Alert.signal_name, Alert.signal_date).in_(pairs),
            Alert.stock_id != stock_id,
        )
        .group_by(Alert.signal_name, Alert.signal_date)
    ).all()

    by_pair = {(n, d): (others, same) for n, d, others, same in rows}
    return {
        a.id: Breadth(*by_pair.get((a.signal_name, a.signal_date), (0, 0)))
        for a in alerts
        if a.signal_date is not None
    }
