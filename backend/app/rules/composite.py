"""Composite expression tree evaluator (AND/OR/atomic)."""
from typing import Any

import pandas as pd

from app.rules.registry import RULES

MAX_DEPTH = 5
MAX_ATOMIC = 8


def evaluate_expression(node: dict, ohlcv: pd.DataFrame) -> bool:
    """Walk tree; True iff the expression evaluates True on the last OHLCV bar."""
    op = node.get("op")
    if op == "atomic":
        kind = node.get("kind")
        if kind not in RULES:
            raise ValueError(f"Unknown rule kind in expression: {kind}")
        return RULES[kind].evaluate(ohlcv, node.get("params", {}))
    if op == "and":
        children = node.get("children") or []
        return all(evaluate_expression(c, ohlcv) for c in children)
    if op == "or":
        children = node.get("children") or []
        return any(evaluate_expression(c, ohlcv) for c in children)
    raise ValueError(f"Invalid expression op: {op!r}")


def snapshot_expression(node: dict, ohlcv: pd.DataFrame) -> dict:
    """Mirror the tree, attaching `.snapshot` and `.matched` to each atomic node."""
    op = node.get("op")
    if op == "atomic":
        kind = node.get("kind")
        params = node.get("params", {})
        if kind not in RULES:
            return {"op": "atomic", "kind": kind, "params": params, "error": "unknown_kind"}
        rule_obj = RULES[kind]
        try:
            matched = rule_obj.evaluate(ohlcv, params)
            snap = rule_obj.snapshot(ohlcv, params)
        except Exception as e:  # noqa: BLE001
            return {"op": "atomic", "kind": kind, "params": params, "error": str(e)}
        return {"op": "atomic", "kind": kind, "params": params, "matched": matched, "snapshot": snap}
    children = [snapshot_expression(c, ohlcv) for c in (node.get("children") or [])]
    matched = all(c.get("matched", False) for c in children) if op == "and" else any(c.get("matched", False) for c in children)
    return {"op": op, "matched": matched, "children": children}


def validate_expression(node: Any, *, max_depth: int = MAX_DEPTH, max_atomic: int = MAX_ATOMIC) -> None:
    """Raise ValueError if tree violates structural constraints."""
    if not isinstance(node, dict):
        raise ValueError("Expression node must be an object")

    def walk(n: Any, depth: int, counter: dict[str, int]) -> None:
        if depth > max_depth:
            raise ValueError(f"Expression depth exceeds {max_depth}")
        if not isinstance(n, dict):
            raise ValueError("Expression node must be an object")
        op = n.get("op")
        if op == "atomic":
            counter["atomic"] += 1
            if counter["atomic"] > max_atomic:
                raise ValueError(f"Too many atomic conditions (max {max_atomic})")
            kind = n.get("kind")
            if kind not in RULES:
                raise ValueError(f"Unknown rule kind: {kind}")
            return
        if op in ("and", "or"):
            children = n.get("children")
            if not isinstance(children, list) or not children:
                raise ValueError(f"'{op}' node must have non-empty children list")
            for c in children:
                walk(c, depth + 1, counter)
            return
        raise ValueError(f"Invalid expression op: {op!r}")

    walk(node, depth=1, counter={"atomic": 0})
