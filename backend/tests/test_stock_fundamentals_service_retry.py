"""Il fetch fundamentals deve ri-tentare su timeout simulato."""
from unittest.mock import patch

import pytest

from app.core.errors import UpstreamTimeout
from app.services.stock_fundamentals_service import _yf_fetch_with_retry


def test_yf_fetch_retries_on_timeout_then_succeeds():
    calls = {"n": 0}

    def fake_do(_t: str):
        calls["n"] += 1
        if calls["n"] < 2:
            raise TimeoutError("simulated network timeout")
        return {"ok": True}

    with patch(
        "app.services.stock_fundamentals_service._do_yf_call", side_effect=fake_do
    ):
        result = _yf_fetch_with_retry("AAPL")
    assert result == {"ok": True}
    assert calls["n"] == 2


def test_yf_fetch_gives_up_after_retries():
    def fake_do(_t: str):
        raise TimeoutError("persistent")

    with patch(
        "app.services.stock_fundamentals_service._do_yf_call", side_effect=fake_do
    ):
        with pytest.raises(UpstreamTimeout):
            _yf_fetch_with_retry("AAPL")
