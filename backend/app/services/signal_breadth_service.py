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

⚠️ FA-064 — THE COUNT IS PER DIRECTION. It used to group on (detector, day)
and ignore the tone, so «38 altri titoli» summed the stocks that fired the
same detector UPWARD with those that fired it DOWNWARD. Measured in production
on 2026-09-15, that was not an edge case:

    alerts with a signal_date                     8.397
    detector/day groups holding BOTH directions     560 of 953
    alerts whose count included the opposite      7.088   (84,4%)
    opposite stocks folded in                     median 6, p90 22, max 93
    VISIBLE alerts affected                       2.910 of 3.740

A detector that fired both ways on the same morning is the opposite of a
market condition in one direction — and the number on screen said the reverse.
The opposite count is now its own field rather than discarded: that the same
detector fired the other way on N names is information, not noise.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import case, func, select, tuple_
from sqlalchemy.orm import Session

from app.core.db_json import json_text
from app.models import Alert, Stock

_tono_sql = json_text(Alert.snapshot, "tone")


def tone_of(alert: Alert) -> str | None:
    """The direction stored in the alert's snapshot, or None.

    The snapshot column is Text holding JSON on SQLite and a JSON string on
    Postgres reads; both arrive here as `str`. A dict is accepted too, because
    a freshly built ORM object may carry one before it is flushed.
    """
    raw = alert.snapshot
    if isinstance(raw, dict):
        dati = raw
    else:
        try:
            dati = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            return None
    tono = dati.get("tone") if isinstance(dati, dict) else None
    return tono if isinstance(tono, str) and tono else None


@dataclass(frozen=True)
class Breadth:
    """How much company a signal had on the day it fired, per direction."""

    same_tone: int
    opposite_tone: int
    #: Same-direction peers in the stock's own sector — a subset of `same_tone`.
    same_tone_sector: int


@dataclass(frozen=True)
class Peer:
    """One stock that fired the same detector, the same day, the same way."""

    alert_id: int
    stock_id: int
    ticker: str
    name: str | None
    sector: str | None


def _peers_clause(name: str, day, tone: str, stock_id: int):
    """The definition of a peer, for ONE alert.

    ⚠️ The count in `breadth_for` applies the same four conditions GROUPED over
    a whole page, so it cannot call this per alert — the two are equivalent by
    reading, not by construction. What keeps them in agreement is
    `test_la_lista_e_il_numero_contano_la_stessa_popolazione`, over the edge
    cases where a drift would hide: archived peers, a re-fire by the same
    stock, a peer with no direction, another detector or day. The list is the
    «collegamento ai componenti» FA-064 asks for, and a list that disagreed
    with the number beside it would be the defect this project keeps closing —
    a count describing one population and a view showing another. The obvious
    link, `/alerts` filtered by detector and date, would have been exactly that:
    its date filter reads `triggered_at`, the breadth reads `signal_date`, and
    2.807 visible alerts carry a different value in the two.

    ARCHIVED ALERTS ARE COUNTED, deliberately. CLAUDE.md's rule — never filter
    a measurement on a field the USER writes — was learned the expensive way
    when the outcome warehouse ended up showing 19 of its 4,880 rows because
    three consumers excluded archived alerts and archival tracks AGE.
    """
    return (
        Alert.signal_name == name,
        Alert.signal_date == day,
        _tono_sql == tone,
        Alert.stock_id != stock_id,
    )


def breadth_for(
    db: Session,
    alerts: Sequence[Alert],
    *,
    stock_id: int,
    sector: str | None,
) -> dict[int, Breadth]:
    """Per-alert breadth, keyed by alert id. One query for the whole page.

    Alerts without a `signal_date` — or without a tone — are ABSENT from the
    result rather than present with a zero: legacy rows predate the column, and
    a signal with no direction has no «same direction» to compare against. A
    zero would read as "it fired alone", which is a claim the data cannot make.
    """
    mine = [
        (a, tone_of(a)) for a in alerts
        if a.signal_date is not None and tone_of(a) is not None
    ]
    if not mine:
        return {}
    pairs = {(a.signal_name, a.signal_date) for a, _ in mine}

    rows = db.execute(
        select(
            Alert.signal_name,
            Alert.signal_date,
            _tono_sql,
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
            # A peer with no direction is neither same nor opposite.
            _tono_sql.is_not(None),
        )
        .group_by(Alert.signal_name, Alert.signal_date, _tono_sql)
    ).all()

    per_tono: dict[tuple, dict[str, tuple[int, int]]] = defaultdict(dict)
    for name, day, tono, tutti, settore in rows:
        per_tono[(name, day)][tono] = (tutti, settore)

    out: dict[int, Breadth] = {}
    for a, tono in mine:
        gruppo = per_tono.get((a.signal_name, a.signal_date), {})
        stessi, stessi_settore = gruppo.get(tono, (0, 0))
        opposti = sum(n for t, (n, _) in gruppo.items() if t != tono)
        out[a.id] = Breadth(
            same_tone=stessi, opposite_tone=opposti, same_tone_sector=stessi_settore,
        )
    return out


def peers_for(db: Session, alert: Alert) -> list[Peer]:
    """The stocks counted in `breadth_for(...).same_tone`, one row per stock.

    A stock that fired the detector twice the same day is ONE peer, exactly as
    the count's `COUNT(DISTINCT stock_id)` treats it; the lowest alert id is
    the one linked. Empty when the alert has no date or no direction, which is
    the same condition under which the breadth is absent.
    """
    tono = tone_of(alert)
    if alert.signal_date is None or tono is None:
        return []
    primo = (
        select(Alert.stock_id, func.min(Alert.id).label("alert_id"))
        .where(*_peers_clause(alert.signal_name, alert.signal_date, tono, alert.stock_id))
        .group_by(Alert.stock_id)
        .subquery()
    )
    rows = db.execute(
        select(primo.c.alert_id, Stock.id, Stock.ticker, Stock.name, Stock.sector)
        .join(Stock, Stock.id == primo.c.stock_id)
        .order_by(Stock.ticker)
    ).all()
    return [
        Peer(alert_id=aid, stock_id=sid, ticker=t, name=n, sector=s)
        for aid, sid, t, n, s in rows
    ]
