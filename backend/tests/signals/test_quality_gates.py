"""Quality gates in evaluate_signals: regime (trend) gate + follow-through."""
import pandas as pd

from app.models import Stock
from app.signals import signal_scan_service as svc
from app.signals.detectors.base import SignalMatch


def _df(prices):
    dates = pd.date_range("2026-01-01", periods=len(prices), freq="D")
    return pd.DataFrame({
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "open": [float(p) for p in prices],
        "high": [float(p) + 1 for p in prices],
        "low": [float(p) - 1 for p in prices],
        "close": [float(p) for p in prices],
        "volume": [1000.0] * len(prices),
    })


def _match(signal_date, *, tone="bull", name="volume_breakout", invalidation=None):
    return SignalMatch(name=name, tone=tone, confidence=90, signal_date=signal_date,
                       chain=[], invalidation=invalidation, factors={})


def _stock(db, ticker):
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US")
    db.add(s)
    db.flush()
    return s


def test_regime_gate_drops_countertrend(db, monkeypatch):
    monkeypatch.setattr(svc.settings, "signal_min_confidence", 0)
    monkeypatch.setattr(svc.settings, "signal_require_follow_through", False)
    monkeypatch.setattr(svc.settings, "signal_require_trend_alignment", True)
    df = _df([200 - i for i in range(60)])  # steady downtrend -> trend_sign < 0
    m = _match(df["date"].iloc[-1], tone="bull")  # bull signal against the trend
    monkeypatch.setattr(svc, "detect_signals", lambda *a, **k: [m])
    s = _stock(db, "RGT")
    assert svc.evaluate_signals(db, s, df) == 0
    db.commit()
    monkeypatch.setattr(svc.settings, "signal_require_trend_alignment", False)
    assert svc.evaluate_signals(db, s, df) == 1


def test_regime_gate_exempts_reversal(db, monkeypatch):
    monkeypatch.setattr(svc.settings, "signal_min_confidence", 0)
    monkeypatch.setattr(svc.settings, "signal_require_follow_through", False)
    monkeypatch.setattr(svc.settings, "signal_require_trend_alignment", True)
    df = _df([200 - i for i in range(60)])  # downtrend
    m = _match(df["date"].iloc[-1], tone="bull", name="oversold_reversal")
    monkeypatch.setattr(svc, "detect_signals", lambda *a, **k: [m])
    s = _stock(db, "REV")
    assert svc.evaluate_signals(db, s, df) == 1  # reversal detector is exempt


def test_follow_through_passes_last_bar(db, monkeypatch):
    monkeypatch.setattr(svc.settings, "signal_min_confidence", 0)
    monkeypatch.setattr(svc.settings, "signal_require_trend_alignment", False)
    monkeypatch.setattr(svc.settings, "signal_require_follow_through", True)
    df = _df([100] * 30 + [110])  # trigger on the last bar (no next bar yet)
    m = _match(df["date"].iloc[-1], tone="bull", invalidation={"level": 105.0, "reason": "x"})
    monkeypatch.setattr(svc, "detect_signals", lambda *a, **k: [m])
    # Last-bar trigger is NOT suppressed (cannot be a confirmed fakeout yet).
    assert svc.evaluate_signals(db, _stock(db, "FTL"), df) == 1


def test_follow_through_confirms_when_next_bar_holds(db, monkeypatch):
    monkeypatch.setattr(svc.settings, "signal_min_confidence", 0)
    monkeypatch.setattr(svc.settings, "signal_require_trend_alignment", False)
    monkeypatch.setattr(svc.settings, "signal_require_follow_through", True)
    df = _df([100] * 30 + [110, 112])  # past-dated trigger, next bar holds
    m = _match(df["date"].iloc[30], tone="bull", invalidation={"level": 105.0, "reason": "x"})
    monkeypatch.setattr(svc, "detect_signals", lambda *a, **k: [m])
    assert svc.evaluate_signals(db, _stock(db, "FTH"), df) == 1


def test_follow_through_drops_fakeout(db, monkeypatch):
    monkeypatch.setattr(svc.settings, "signal_min_confidence", 0)
    monkeypatch.setattr(svc.settings, "signal_require_trend_alignment", False)
    monkeypatch.setattr(svc.settings, "signal_require_follow_through", True)
    df = _df([100] * 30 + [110, 101])  # next bar closes back below the level
    m = _match(df["date"].iloc[30], tone="bull", invalidation={"level": 105.0, "reason": "x"})
    monkeypatch.setattr(svc, "detect_signals", lambda *a, **k: [m])
    s = _stock(db, "FAK")
    assert svc.evaluate_signals(db, s, df) == 0  # fakeout dropped
