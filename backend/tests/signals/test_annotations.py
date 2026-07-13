import json

import pandas as pd

from app.models import Alert, Stock
from app.signals.signal_scan_service import evaluate_signals


def _confirmed_df():
    rows = [{"date": f"2026-04-{i:02d}", "open": 100, "high": 101, "low": 99,
             "close": 100, "volume": 1000} for i in range(1, 21)]
    rows.append({"date": "2026-05-01", "open": 100, "high": 112, "low": 100,
                 "close": 110, "volume": 4000})
    return pd.DataFrame(rows)


def test_snapshot_carries_annotations_with_stop(db, monkeypatch):
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_min_confidence", 0)
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_require_follow_through", False)
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_require_trend_alignment", False)
    s = Stock(ticker="ANN", exchange="NASDAQ", name="Ann", country="US")
    db.add(s); db.flush()
    evaluate_signals(db, s, _confirmed_df()); db.commit()
    a = db.query(Alert).filter(Alert.stock_id == s.id,
                               Alert.signal_name == "volume_breakout").first()
    assert a is not None
    snap = json.loads(a.snapshot)
    assert "annotations" in snap
    ann = snap["annotations"]
    assert isinstance(ann.get("levels"), list) and isinstance(ann.get("points"), list)
    # volume_breakout has an invalidation level -> an auto-derived stop level.
    assert any(l.get("kind") == "stop" for l in ann["levels"])
