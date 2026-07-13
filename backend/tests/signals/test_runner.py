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
    called = {"hit": False}

    class Boom:
        name = "boom"
        min_bars = 1

        def detect(self, *a, **k):
            called["hit"] = True
            raise RuntimeError("nope")

    monkeypatch.setattr("app.signals.runner.DETECTORS", [Boom()])
    # Two rows so we clear the short-frame guard (len >= 2) and actually reach
    # the detector loop; the crashing detector must be caught, not propagated.
    df = pd.DataFrame([
        {"date": "2026-05-01", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
        {"date": "2026-05-02", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
    ])
    assert detect_signals(df) == []
    assert called["hit"], "failing detector was never invoked - guard short-circuited"
