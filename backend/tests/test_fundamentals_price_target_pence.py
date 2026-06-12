"""LSE pence scaling on analyst price targets (HLMA.L regression).

yfinance returns .L analyst targets in PENCE (currency GBp) while all our
price paths normalize to POUNDS — unscaled, the analyst card showed a 4276
"target" next to a 39.40 price. The fetch-time extractors take a `scale`."""
import pytest

from app.services.stock_fundamentals_service import (
    _extract_price_target,
)


def test_price_target_scaled_pence_to_pounds():
    pt = {"current": 4300.0, "low": 3050.0, "mean": 4276.56, "median": 4300.0, "high": 5060.0}
    out = _extract_price_target(pt, scale=0.01)
    assert out.mean == pytest.approx(42.7656)
    assert out.low == pytest.approx(30.50)
    assert out.high == pytest.approx(50.60)


def test_price_target_default_scale_is_identity():
    pt = {"mean": 250.0, "low": 200.0, "high": 300.0}
    out = _extract_price_target(pt)
    assert out.mean == 250.0 and out.low == 200.0 and out.high == 300.0


def test_price_target_none_fields_stay_none():
    out = _extract_price_target({"mean": 4000.0}, scale=0.01)
    assert out.mean == pytest.approx(40.0)
    assert out.low is None and out.high is None
