"""Tests for rule_compaction_service."""
import json

from sqlalchemy.orm import Session

from app.models import Rule
from app.services.rule_compaction_service import compact_rules


def _seed(db: Session, **kwargs) -> Rule:
    defaults = {"kind": "composite", "params": "{}", "enabled": True}
    defaults.update(kwargs)
    r = Rule(**defaults)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def test_compact_rewrites_single_atomic_wrapped_in_and(db: Session) -> None:
    expr = {
        "op": "and",
        "children": [
            {"op": "atomic", "kind": "volume_spike", "params": {"window": 20, "threshold": 2.0}},
        ],
    }
    r = _seed(db, expression=json.dumps(expr))
    res = compact_rules(db)
    db.refresh(r)
    assert res.rules_rewritten == 1
    assert r.id in res.rewritten_ids
    assert r.kind == "volume_spike"
    assert json.loads(r.params) == {"window": 20, "threshold": 2.0}
    assert r.expression is None


def test_compact_rewrites_naked_atomic_expression(db: Session) -> None:
    expr = {"op": "atomic", "kind": "rsi_oversold", "params": {"period": 14, "threshold": 30}}
    r = _seed(db, expression=json.dumps(expr))
    res = compact_rules(db)
    db.refresh(r)
    assert res.rules_rewritten == 1
    assert r.kind == "rsi_oversold"
    assert r.expression is None


def test_compact_unwraps_nested_single_child_chain(db: Session) -> None:
    expr = {
        "op": "and",
        "children": [
            {
                "op": "or",
                "children": [
                    {"op": "atomic", "kind": "breakout", "params": {"period": 20}},
                ],
            },
        ],
    }
    r = _seed(db, expression=json.dumps(expr))
    res = compact_rules(db)
    db.refresh(r)
    assert res.rules_rewritten == 1
    assert r.kind == "breakout"
    assert r.expression is None


def test_compact_leaves_genuine_composite_alone(db: Session) -> None:
    expr = {
        "op": "and",
        "children": [
            {"op": "atomic", "kind": "rsi_oversold", "params": {"period": 14, "threshold": 30}},
            {"op": "atomic", "kind": "volume_spike", "params": {"window": 20, "threshold": 2.0}},
        ],
    }
    r = _seed(db, expression=json.dumps(expr))
    res = compact_rules(db)
    db.refresh(r)
    assert res.rules_rewritten == 0
    assert r.kind == "composite"
    assert r.expression is not None


def test_compact_skips_rules_without_expression(db: Session) -> None:
    r = _seed(db, kind="rsi_oversold", params=json.dumps({"period": 14, "threshold": 30}), expression=None)
    res = compact_rules(db)
    db.refresh(r)
    assert res.rules_inspected == 0
    assert r.kind == "rsi_oversold"


def test_compact_is_idempotent(db: Session) -> None:
    expr = {
        "op": "and",
        "children": [
            {"op": "atomic", "kind": "breakout", "params": {"period": 20}},
        ],
    }
    r = _seed(db, expression=json.dumps(expr))
    res1 = compact_rules(db)
    res2 = compact_rules(db)
    db.refresh(r)
    assert res1.rules_rewritten == 1
    assert res2.rules_rewritten == 0
    assert r.kind == "breakout"
