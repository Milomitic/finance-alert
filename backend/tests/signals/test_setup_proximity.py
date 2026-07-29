"""Per-detector proximity: the pre-trigger state each detector can expose.

The contract every one of these must honour: `proximity()` returns a setup
ONLY while `detect()` would return None. The moment the trigger gate closes,
the thing is a signal and the setup must step aside — otherwise the same event
would be reported twice, once as a forecast and once as a fact.
"""
import pandas as pd

from app.signals.context import SignalContext
from app.signals.detectors.candle_reversal import CandleReversal
from app.signals.detectors.oversold_reversal import OversoldReversal
from app.signals.detectors.squeeze_expansion import SqueezeExpansion
from app.signals.detectors.trend_pullback import TrendPullback
from app.signals.events import Event


def _ctx(last_close: float, trend_sign: int = 1) -> SignalContext:
    return SignalContext(last_close=last_close, trend_sign=trend_sign, atr=1.0,
                         trend_age=50, regime="bull")


def _frame(closes: list[float], last_open: float | None = None) -> pd.DataFrame:
    rows = []
    for i, c in enumerate(closes):
        o = c * 0.99
        rows.append({"date": f"2026-01-{1 + i % 28:02d}", "open": o, "high": max(o, c) * 1.01,
                     "low": min(o, c) * 0.99, "close": c, "volume": 1_000_000})
    if last_open is not None:
        rows[-1]["open"] = last_open
        rows[-1]["high"] = max(last_open, rows[-1]["close"]) * 1.01
        rows[-1]["low"] = min(last_open, rows[-1]["close"]) * 0.99
    return pd.DataFrame(rows)


# ─── oversold_reversal: extreme + at level, awaiting the turn ───────────────

def _oversold_events(level: float) -> list[Event]:
    return [
        Event(date="2026-01-20", type="rsi_extreme", direction="bull", payload={"rsi": 18.0}),
        Event(date="2026-01-20", type="sr_level", payload={"kind": "support", "level": level}),
    ]


def test_oversold_setup_when_at_support_but_bar_has_not_turned():
    det = OversoldReversal()
    df = _frame([100.0] * 24 + [50.5], last_open=52.0)   # red bar: close < open
    events = _oversold_events(50.0)

    assert det.detect(events, df, _ctx(50.5)) is None, "the trigger has not fired"
    sm = det.proximity(events, df, _ctx(50.5))
    assert sm is not None
    assert sm.proximity == 0.85
    assert "girare" in sm.missing


def test_oversold_setup_steps_aside_once_the_bar_turns():
    """The moment detect() fires there must be no setup — one event, one row."""
    det = OversoldReversal()
    df = _frame([100.0] * 24 + [50.5], last_open=49.0)   # green bar: close > open
    events = _oversold_events(50.0)

    assert det.detect(events, df, _ctx(50.5)) is not None
    assert det.proximity(events, df, _ctx(50.5)) is None


def test_oversold_setup_ranks_an_approach_below_being_at_the_level():
    """Farther from the level = less imminent = lower in the list."""
    det = OversoldReversal()
    at = _frame([100.0] * 24 + [50.5], last_open=52.0)
    near = _frame([100.0] * 24 + [53.5], last_open=55.0)   # ~7% away
    a = det.proximity(_oversold_events(50.0), at, _ctx(50.5))
    b = det.proximity(_oversold_events(50.0), near, _ctx(53.5))
    assert a is not None and b is not None
    assert a.proximity > b.proximity


def test_oversold_setup_ignores_a_level_too_far_to_be_in_play():
    det = OversoldReversal()
    df = _frame([100.0] * 24 + [80.0], last_open=82.0)     # 60% above the level
    assert det.proximity(_oversold_events(50.0), df, _ctx(80.0)) is None


# ─── squeeze_expansion: coiled, awaiting the release ────────────────────────

def test_squeeze_setup_while_the_coil_has_not_expanded():
    det = SqueezeExpansion()
    df = _frame([100.0] * 30)
    events = [Event(date="2026-01-28", type="bb_squeeze", magnitude=1.6)]

    assert det.detect(events, df, _ctx(100.0)) is None
    sm = det.proximity(events, df, _ctx(100.0))
    assert sm is not None
    assert 0.45 <= sm.proximity <= 0.75
    assert "direzione" in sm.missing, "an unresolved squeeze must not imply a direction"


def test_squeeze_setup_steps_aside_once_the_bands_expand():
    det = SqueezeExpansion()
    df = _frame([100.0] * 30)
    events = [
        Event(date="2026-01-20", type="bb_squeeze", magnitude=1.6),
        Event(date="2026-01-22", type="bb_expansion", direction="bull", magnitude=0.08),
    ]
    assert det.proximity(events, df, _ctx(100.0)) is None


def test_a_tighter_coil_ranks_higher():
    det = SqueezeExpansion()
    df = _frame([100.0] * 30)
    tight = det.proximity([Event(date="2026-01-28", type="bb_squeeze", magnitude=1.9)],
                          df, _ctx(100.0))
    loose = det.proximity([Event(date="2026-01-28", type="bb_squeeze", magnitude=1.0)],
                          df, _ctx(100.0))
    assert tight.proximity > loose.proximity


def test_a_stale_squeeze_is_not_presented_as_still_loaded():
    """Past the expansion window the coil never resolved into this signal;
    keeping it on the list would be clutter that never converts."""
    det = SqueezeExpansion()
    df = _frame([100.0] * 30)   # last bar 2026-01-02 (wraps at 28)
    old = [Event(date="2025-06-01", type="bb_squeeze", magnitude=1.6)]
    assert det.proximity(old, df, _ctx(100.0)) is None


# ─── trend_pullback: pulled back, awaiting the resumption ───────────────────

def test_pullback_setup_when_price_sits_on_the_ema_without_resuming():
    det = TrendPullback()
    # min_bars is 210 and the "fast" EMA is EMA50, so the fixture needs a long
    # uptrend followed by a pullback deep enough to close BELOW that EMA.
    closes = [50.0 + i * 0.5 for i in range(240)] + [169.5 - (i + 1) * 2.0 for i in range(20)]
    df = _frame(closes)
    events = [Event(date="2026-01-10", type="ema_cross", direction="bull")]

    assert det.detect(events, df, _ctx(closes[-1])) is None, "resumption has not happened"
    sm = det.proximity(events, df, _ctx(closes[-1]))
    assert sm is not None
    assert sm.tone == "bull"
    assert "EMA" in sm.missing
    # The EMA is the level to plan against — it must be on the chart.
    assert sm.annotations["levels"], "the pullback level must be drawable"


def test_pullback_setup_steps_aside_once_price_resumes():
    det = TrendPullback()
    closes = [50.0 + i * 0.5 for i in range(260)]    # still rising: above the EMA50
    df = _frame(closes)
    events = [Event(date="2026-01-10", type="ema_cross", direction="bull")]
    assert det.proximity(events, df, _ctx(closes[-1])) is None


# ─── candle_reversal: at a proven level, awaiting the reversal candle ───────

def _level_events(level: float, kind: str = "support") -> list[Event]:
    return [Event(date="2026-01-20", type="sr_level", payload={"kind": kind, "level": level})]


def _bars_touching(level: float, touches: int, last_close: float) -> pd.DataFrame:
    """A series whose lows come back to `level` exactly `touches` times."""
    closes, lows = [], []
    for i in range(30):
        if i < touches:
            closes.append(level * 1.05)
            lows.append(level)              # a test of the level
        else:
            closes.append(level * 1.30)
            lows.append(level * 1.25)       # well away from it
    closes[-1] = last_close
    lows[-1] = last_close * 0.999
    df = _frame(closes)
    df["low"] = lows
    return df


def test_candle_setup_when_price_tests_a_proven_level_without_a_candle():
    det = CandleReversal()
    df = _bars_touching(100.0, touches=4, last_close=100.5)   # 0.5% above
    events = _level_events(100.0)

    assert det.detect(events, df, _ctx(100.5)) is None, "no reversal candle yet"
    sm = det.proximity(events, df, _ctx(100.5))
    assert sm is not None
    assert "candela di inversione" in sm.missing
    assert "testato" in sm.missing, "the level's history is the point"


def test_candle_setup_steps_aside_once_the_candle_prints():
    det = CandleReversal()
    df = _bars_touching(100.0, touches=4, last_close=100.5)
    events = _level_events(100.0) + [
        Event(date="2026-01-28", type="candle_reversal", direction="bull",
              magnitude=0.9, payload={"pattern": "hammer"}),
    ]
    assert det.proximity(events, df, _ctx(100.5)) is None


def test_candle_setup_ignores_a_level_touched_only_once():
    """A single pivot is the swing that defined the level, not a level being
    respected. Emitting on it is how a setup list becomes the whole market."""
    det = CandleReversal()
    df = _bars_touching(100.0, touches=1, last_close=100.5)
    assert det.proximity(_level_events(100.0), df, _ctx(100.5)) is None


def test_candle_setup_is_stricter_than_the_trigger_it_anticipates():
    """detect() fires within 3% of a level — a band a large slice of the
    universe sits in at any time. The setup must be tighter, or it recreates
    the flood that made the first production run unusable (1214 setups)."""
    det = CandleReversal()
    at = _bars_touching(100.0, touches=4, last_close=100.5)    # 0.5% away
    loose = _bars_touching(100.0, touches=4, last_close=102.5)  # 2.5% — inside
                                                               # the trigger band
    assert det.proximity(_level_events(100.0), at, _ctx(100.5)) is not None
    assert det.proximity(_level_events(100.0), loose, _ctx(102.5)) is None


def test_a_more_tested_level_ranks_higher():
    det = CandleReversal()
    many = det.proximity(_level_events(100.0), _bars_touching(100.0, 8, 100.5), _ctx(100.5))
    few = det.proximity(_level_events(100.0), _bars_touching(100.0, 2, 100.5), _ctx(100.5))
    assert many.factors["level_strength"] > few.factors["level_strength"]
