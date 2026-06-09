"""quality_extras: read-time informational enrichment (governance + analyst)
for the Qualità score. Additive only — never part of the composite."""
from __future__ import annotations

from types import SimpleNamespace

from app.services.score_service import quality_extras


def _f(**micro):
    pt = SimpleNamespace(current_price_target=micro.pop("target", None))
    return SimpleNamespace(micro=SimpleNamespace(**{
        "audit_risk": None, "board_risk": None, "compensation_risk": None,
        "overall_risk": None, "recommendation_mean": None,
        "number_of_analyst_opinions": None, **micro,
    }), price_target=pt)


def test_none_fundamentals():
    assert quality_extras(None) is None


def test_governance_and_analyst_surfaced():
    f = _f(audit_risk=2, board_risk=5, compensation_risk=3, overall_risk=4,
           recommendation_mean=1.8, number_of_analyst_opinions=27, target=130.0)
    out = quality_extras(f, current_price=100.0)
    assert out["governance"] == {"audit": 2.0, "board": 5.0, "compensation": 3.0, "overall": 4.0}
    assert out["analyst"]["recommendation_mean"] == 1.8
    assert out["analyst"]["n_analysts"] == 27
    assert out["analyst"]["price_target"] == 130.0
    assert out["analyst"]["target_upside_pct"] == 30.0   # 130/100 - 1


def test_upside_omitted_without_price():
    out = quality_extras(_f(target=130.0))
    assert "target_upside_pct" not in out["analyst"]
    assert out["analyst"]["price_target"] == 130.0


def test_returns_none_when_nothing_available():
    assert quality_extras(_f()) is None
