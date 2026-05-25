"""Tests for signal horizon classification (span primary, prior fallback)."""
from app.signals.horizon import classify_horizon


def test_span_short_medium_long():
    assert classify_horizon("x", [{"date": "2026-05-20"}, {"date": "2026-05-22"}]) == "short"   # 2d
    assert classify_horizon("x", [{"date": "2026-05-01"}, {"date": "2026-05-25"}]) == "medium"  # 24d
    assert classify_horizon("x", [{"date": "2026-01-15"}, {"date": "2026-05-22"}]) == "long"    # >35d


def test_span_boundaries():
    assert classify_horizon("x", [{"date": "2026-05-15"}, {"date": "2026-05-22"}]) == "short"   # exactly 7d
    assert classify_horizon("x", [{"date": "2026-05-15"}, {"date": "2026-05-23"}]) == "medium"  # 8d
    assert classify_horizon("x", [{"date": "2026-04-17"}, {"date": "2026-05-22"}]) == "medium"  # 35d
    assert classify_horizon("x", [{"date": "2026-04-16"}, {"date": "2026-05-22"}]) == "long"    # 36d


def test_prior_fallback_on_mono_date():
    assert classify_horizon("trend_pullback", [{"date": "2026-05-22"}]) == "long"
    assert classify_horizon("candle_reversal", [{"date": "2026-05-22"}]) == "short"
    assert classify_horizon("sr_flip", [{"date": "2026-05-22"}]) == "medium"


def test_default_medium_when_unknown():
    assert classify_horizon(None, []) == "medium"
    assert classify_horizon("nonexistent_detector", None) == "medium"


def test_ignores_unparseable_dates():
    # one valid date only -> mono -> prior
    assert classify_horizon("gap_and_go", [{"date": "bad"}, {"date": "2026-05-22"}]) == "short"
