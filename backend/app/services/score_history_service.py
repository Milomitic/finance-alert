"""Daily snapshot of the Qualità + Tecnico composites into score_history.

Called best-effort at the end of a scan (after recompute). Idempotent per day:
if a snapshot already exists for `on`, it's a no-op. This is the substrate for
the score-IC backtest (roadmap #9) — without it neither lens has any history to
validate against forward returns.
"""
from __future__ import annotations

import json
from datetime import date

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ScoreHistory, StockScore, TechnicalScore

_QUALITA_PILLARS = ("quality", "profitability", "sustainability", "growth", "value", "sentiment")
_TECNICO_DIMS = ("trend", "momentum", "structure", "volume", "rel_strength", "signals")


def capture(db: Session, *, on: date | None = None, commit: bool = True) -> int:
    """Snapshot both lenses for `on` (default today). Returns rows written (0 if
    a snapshot for the day already exists)."""
    day = on or date.today()
    already = db.execute(
        select(ScoreHistory.id).where(ScoreHistory.captured_on == day).limit(1)
    ).first()
    if already is not None:
        return 0

    rows: list[ScoreHistory] = []
    for sc in db.execute(select(StockScore)).scalars():
        rows.append(ScoreHistory(
            stock_id=sc.stock_id, lens="qualita", captured_on=day,
            composite=float(sc.composite),
            pillars=json.dumps({p: getattr(sc, p) for p in _QUALITA_PILLARS}),
        ))
    for tc in db.execute(select(TechnicalScore)).scalars():
        rows.append(ScoreHistory(
            stock_id=tc.stock_id, lens="tecnico", captured_on=day,
            composite=float(tc.composite),
            pillars=json.dumps({d: getattr(tc, d) for d in _TECNICO_DIMS}),
        ))
    if rows:
        db.add_all(rows)
        if commit:
            db.commit()
    logger.info(f"[score-history] captured {len(rows)} rows for {day}")
    return len(rows)
