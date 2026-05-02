"""Tests for VolumeSpikeRule."""
import pandas as pd

from app.rules.volume_rules import VolumeSpikeRule


def _ohlcv(volumes: list[int]) -> pd.DataFrame:
    n = len(volumes)
    return pd.DataFrame({
        "open": [100.0] * n,
        "high": [101.0] * n,
        "low": [99.0] * n,
        "close": [100.0] * n,
        "volume": volumes,
    })


def test_volume_spike_true_when_today_above_threshold_x_avg() -> None:
    rule = VolumeSpikeRule()
    vols = [1000] * 20 + [3000]
    df = _ohlcv(vols)
    assert rule.evaluate(df, {"window": 20, "threshold": 2.0}) is True


def test_volume_spike_false_when_today_below_threshold() -> None:
    rule = VolumeSpikeRule()
    vols = [1000] * 20 + [1500]
    df = _ohlcv(vols)
    assert rule.evaluate(df, {"window": 20, "threshold": 2.0}) is False


def test_volume_spike_kind_and_defaults() -> None:
    r = VolumeSpikeRule()
    assert r.kind == "volume_spike"
    assert r.default_params == {"window": 20, "threshold": 2.0}


def test_volume_spike_snapshot_has_ratio() -> None:
    rule = VolumeSpikeRule()
    vols = [1000] * 20 + [3000]
    df = _ohlcv(vols)
    snap = rule.snapshot(df, {"window": 20, "threshold": 2.0})
    assert "ratio" in snap and snap["ratio"] >= 2.9
    assert snap["window"] == 20
    assert snap["threshold"] == 2.0
