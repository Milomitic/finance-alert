"""Compact composite rules whose expression is really a single atomic.

Pre-fix UI saved every rule with kind="composite" + expression tree, even when
the user composed only one condition. This service rewrites those rules to
their atomic form (kind=<atomic_kind>, params=<atomic_params>, expression=NULL)
so the table and alert labels reflect the actual semantics.

Idempotent: running on already-compacted rules is a no-op.
"""
import json
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Rule


@dataclass
class CompactionResult:
    rules_inspected: int = 0
    rules_rewritten: int = 0
    rewritten_ids: list[int] = field(default_factory=list)


def _innermost_atomic(node: dict[str, Any]) -> dict[str, Any] | None:
    """Walk single-child wrappers; return the inner atomic node if present, else None."""
    current = node
    while isinstance(current, dict) and current.get("op") in ("and", "or"):
        children = current.get("children") or []
        if len(children) != 1:
            return None
        current = children[0]
    if isinstance(current, dict) and current.get("op") == "atomic":
        return current
    return None


def compact_rules(db: Session) -> CompactionResult:
    """Find Rule rows where expression simplifies to a single atomic and rewrite them."""
    result = CompactionResult()
    rows = db.execute(
        select(Rule).where(Rule.expression.isnot(None))
    ).scalars().all()
    for r in rows:
        result.rules_inspected += 1
        try:
            expr = json.loads(r.expression)
        except (TypeError, ValueError):
            logger.warning(f"[compact] rule {r.id}: invalid JSON expression, skipping")
            continue
        atomic = _innermost_atomic(expr)
        if atomic is None:
            continue  # genuinely composite, leave alone
        new_kind = atomic.get("kind")
        if not isinstance(new_kind, str):
            continue
        new_params = atomic.get("params") or {}
        r.kind = new_kind
        r.params = json.dumps(new_params)
        r.expression = None
        result.rules_rewritten += 1
        result.rewritten_ids.append(r.id)
        logger.info(f"[compact] rule {r.id}: composite → {new_kind}")
    db.commit()
    logger.info(
        f"[compact] done: inspected={result.rules_inspected} "
        f"rewritten={result.rules_rewritten}"
    )
    return result
