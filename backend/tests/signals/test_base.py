from app.signals.events import Event
from app.signals.detectors.base import find_after, SignalMatch


def test_find_after_respects_order_and_window():
    evs = [
        Event("2026-05-01", "breakout", "bull"),
        Event("2026-05-02", "volume_spike", None),
        Event("2026-05-10", "volume_spike", None),
    ]
    # volume spike within 3 bars of the breakout date -> the 05-02 one
    hit = find_after(evs, "volume_spike", after="2026-05-01", within_days=3)
    assert hit is not None and hit.date == "2026-05-02"
    # nothing within 1 day
    assert find_after(evs, "volume_spike", after="2026-05-01", within_days=0) is None


def test_signalmatch_is_constructible():
    m = SignalMatch(name="x", tone="bull", strength=70, signal_date="2026-05-02",
                    chain=[{"date": "2026-05-01", "label": "Breakout", "detail": ""}],
                    invalidation=None, factors={"f": 1.0})
    assert m.strength == 70
