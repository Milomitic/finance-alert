"""Tests for composite expression evaluator."""
import pandas as pd
import pytest

from app.rules.composite import (
    MAX_ATOMIC,
    MAX_DEPTH,
    evaluate_expression,
    snapshot_expression,
    validate_expression,
)


def _ohlcv_oversold() -> pd.DataFrame:
    closes = [100.0 - i * 0.5 for i in range(40)]
    return pd.DataFrame({"close": closes, "open": closes, "high": closes, "low": closes, "volume": [1000] * 40})


def _ohlcv_overbought() -> pd.DataFrame:
    closes = [100.0 + i * 0.5 for i in range(40)]
    return pd.DataFrame({"close": closes, "open": closes, "high": closes, "low": closes, "volume": [1000] * 40})


def test_atomic_evaluates_via_registry() -> None:
    expr = {"op": "atomic", "kind": "rsi_oversold", "params": {"period": 14, "threshold": 30}}
    assert evaluate_expression(expr, _ohlcv_oversold()) is True
    assert evaluate_expression(expr, _ohlcv_overbought()) is False


def test_and_returns_true_only_if_all_children_true() -> None:
    expr = {
        "op": "and",
        "children": [
            {"op": "atomic", "kind": "rsi_oversold", "params": {"period": 14, "threshold": 30}},
            {"op": "atomic", "kind": "rsi_overbought", "params": {"period": 14, "threshold": 70}},
        ],
    }
    assert evaluate_expression(expr, _ohlcv_oversold()) is False


def test_or_returns_true_if_any_child_true() -> None:
    expr = {
        "op": "or",
        "children": [
            {"op": "atomic", "kind": "rsi_oversold", "params": {"period": 14, "threshold": 30}},
            {"op": "atomic", "kind": "rsi_overbought", "params": {"period": 14, "threshold": 70}},
        ],
    }
    assert evaluate_expression(expr, _ohlcv_oversold()) is True


def test_nested_and_or_evaluates_correctly() -> None:
    expr = {
        "op": "and",
        "children": [
            {"op": "atomic", "kind": "rsi_oversold", "params": {"period": 14, "threshold": 30}},
            {
                "op": "or",
                "children": [
                    {"op": "atomic", "kind": "rsi_overbought", "params": {"period": 14, "threshold": 70}},
                    {"op": "atomic", "kind": "volume_spike", "params": {"window": 5, "threshold": 0.0}},
                ],
            },
        ],
    }
    assert evaluate_expression(expr, _ohlcv_oversold()) is True


def test_unknown_kind_raises() -> None:
    with pytest.raises(ValueError, match="Unknown rule kind"):
        evaluate_expression({"op": "atomic", "kind": "totally_made_up", "params": {}}, _ohlcv_oversold())


def test_invalid_op_raises() -> None:
    with pytest.raises(ValueError, match="Invalid expression op"):
        evaluate_expression({"op": "xor", "children": []}, _ohlcv_oversold())


def test_validate_rejects_too_deep() -> None:
    leaf = {"op": "atomic", "kind": "rsi_oversold", "params": {}}
    expr = leaf
    for _ in range(MAX_DEPTH + 1):
        expr = {"op": "and", "children": [expr]}
    with pytest.raises(ValueError, match="depth"):
        validate_expression(expr)


def test_validate_rejects_too_many_atomic() -> None:
    leaves = [{"op": "atomic", "kind": "rsi_oversold", "params": {}} for _ in range(MAX_ATOMIC + 1)]
    expr = {"op": "and", "children": leaves}
    with pytest.raises(ValueError, match="atomic"):
        validate_expression(expr)


def test_validate_accepts_well_formed() -> None:
    expr = {
        "op": "and",
        "children": [
            {"op": "atomic", "kind": "rsi_oversold", "params": {}},
            {"op": "atomic", "kind": "volume_spike", "params": {}},
        ],
    }
    validate_expression(expr)


def test_snapshot_mirrors_tree_with_atomic_snapshots() -> None:
    expr = {
        "op": "and",
        "children": [
            {"op": "atomic", "kind": "rsi_oversold", "params": {"period": 14, "threshold": 30}},
            {"op": "atomic", "kind": "volume_spike", "params": {"window": 20, "threshold": 2.0}},
        ],
    }
    snap = snapshot_expression(expr, _ohlcv_oversold())
    assert snap["op"] == "and"
    assert len(snap["children"]) == 2
    assert snap["children"][0]["op"] == "atomic"
    assert "snapshot" in snap["children"][0]
