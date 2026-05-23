"""Technical score: dimension monotonicity, relative-strength ranking, upsert."""
import pandas as pd

from app.models import Stock, TechnicalScore
from app.services import technical_score_service as svc


def _df(prices):
    n = len(prices)
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "open": [float(p) for p in prices],
        "high": [float(p) + 1 for p in prices],
        "low": [float(p) - 1 for p in prices],
        "close": [float(p) for p in prices],
        "volume": [1000.0] * n,
    })


def test_uptrend_scores_higher_than_downtrend():
    up = svc.partial_for(_df([100 + i for i in range(120)]))
    down = svc.partial_for(_df([300 - i for i in range(120)]))
    assert up is not None and down is not None
    assert up["trend"] > down["trend"]
    assert up["momentum"] > down["momentum"]
    assert up["structure"] > down["structure"]


def test_short_history_returns_none():
    assert svc.partial_for(_df([100, 101, 102])) is None


def test_finalize_ranks_rel_strength_and_upserts(db):
    s1 = Stock(ticker="TUP", exchange="NASDAQ", name="Up", country="US")
    s2 = Stock(ticker="TDN", exchange="NASDAQ", name="Dn", country="US")
    db.add_all([s1, s2])
    db.flush()
    p_up = svc.partial_for(_df([100 + i for i in range(120)]))
    p_dn = svc.partial_for(_df([300 - i for i in range(120)]))
    n = svc.finalize(db, {s1.id: p_up, s2.id: p_dn})
    db.commit()
    assert n == 2
    ts_up = db.get(TechnicalScore, s1.id)
    ts_dn = db.get(TechnicalScore, s2.id)
    assert ts_up is not None and ts_dn is not None
    # The uptrend stock has the stronger blended return, so higher rel strength.
    assert ts_up.rel_strength > ts_dn.rel_strength
    assert ts_up.composite > ts_dn.composite
    assert ts_up.posture in ("Forte", "Neutro", "Debole")


def test_finalize_empty_is_noop(db):
    assert svc.finalize(db, {}) == 0
