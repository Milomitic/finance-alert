import pandas as pd
from app.signals.runner import detect_signals


def test_runner_returns_match_for_confirmed_breakout():
    rows = [{"date": f"2026-04-{i:02d}", "open": 100, "high": 101, "low": 99,
             "close": 100, "volume": 1000} for i in range(1, 21)]
    rows.append({"date": "2026-05-01", "open": 100, "high": 112, "low": 100,
                 "close": 110, "volume": 4000})
    matches = detect_signals(pd.DataFrame(rows))
    assert any(m.name == "volume_breakout" for m in matches)


def test_runner_isolates_a_failing_detector(monkeypatch):
    class Boom:
        name = "boom"; min_bars = 1
        def detect(self, *a, **k): raise RuntimeError("nope")
    monkeypatch.setattr("app.signals.runner.DETECTORS", [Boom()])
    # Must not raise; just returns no matches.
    assert detect_signals(pd.DataFrame([{"date": "2026-05-01", "open": 1,
        "high": 1, "low": 1, "close": 1, "volume": 1}])) == []
