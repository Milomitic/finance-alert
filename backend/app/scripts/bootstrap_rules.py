"""Idempotent bootstrap of the 4 Tier 1 (global) rules."""
import json

from loguru import logger
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Rule
from app.rules.registry import RULES


def ensure_global_rules() -> None:
    """Create the 4 global rules with default params if not present.

    Re-run is safe: existing globals are not modified.
    """
    db = SessionLocal()
    try:
        for kind, rule_obj in RULES.items():
            existing = db.execute(
                select(Rule).where(Rule.watchlist_id.is_(None), Rule.kind == kind)
            ).scalar_one_or_none()
            if existing is not None:
                continue
            db.add(
                Rule(
                    watchlist_id=None,
                    kind=kind,
                    params=json.dumps(rule_obj.default_params),
                    enabled=True,
                )
            )
            logger.info(f"[bootstrap_rules] created global rule: {kind}")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    ensure_global_rules()
