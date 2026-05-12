"""Idempotent bootstrap of the global rules.

Pre-May-2026 these used to be "Tier 1" globals (with the watchlist
override layer). The watchlist feature was removed — these are just
"the rules" now. The script seeds one row per kind in the registry
with the rule's default params. Safe to re-run.
"""
import json

from loguru import logger
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Rule
from app.rules.registry import RULES


def ensure_global_rules() -> None:
    """Create one global rule per registry kind. Existing rows untouched."""
    db = SessionLocal()
    try:
        for kind, rule_obj in RULES.items():
            existing = db.execute(
                select(Rule).where(Rule.kind == kind)
            ).scalar_one_or_none()
            if existing is not None:
                continue
            db.add(
                Rule(
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
