"""Health probes stop re-asking an endpoint the plan does not include.

`/stock/upgrade-downgrade` is not in Finnhub's free tier. Measured in the
retained log window: 147 identical 403s and not one success, for a question
whose answer cannot change between two scheduler ticks.

The cause is subtle. Every probe elides on `seconds_since_last_success`, which
does nothing for a call that has NEVER succeeded — with no success to measure
against, the guard is always False and the probe fires at full rate forever.
The condition needed is the symmetric one, on the last FAILURE.
"""
import pytest

from app.services import data_source_metrics as dsm
from app.services import probes


@pytest.fixture(autouse=True)
def _clean():
    dsm.reset()
    yield
    dsm.reset()


class TestIsPlanGated:
    def test_all_403s_is_plan_gated(self):
        for _ in range(3):
            dsm.record_failure("finnhub", "upgrades", reason="HTTP 403")
        assert dsm.is_plan_gated("finnhub", "upgrades") is True

    def test_one_non_403_breaks_the_pattern(self):
        """A timeout among the 403s means something else is also wrong, and
        the source goes back to being a normal incident rather than a
        configuration fact."""
        dsm.record_failure("finnhub", "upgrades", reason="HTTP 403")
        dsm.record_failure("finnhub", "upgrades", reason="ReadTimeout")
        assert dsm.is_plan_gated("finnhub", "upgrades") is False

    def test_an_untouched_source_is_not_plan_gated(self):
        assert dsm.is_plan_gated("finnhub", "upgrades") is False

    def test_a_healthy_source_is_not_plan_gated(self):
        dsm.record_success("finnhub", "news")
        assert dsm.is_plan_gated("finnhub", "news") is False

    def test_the_ui_classifier_agrees(self):
        """The predicate is shared with `_classify` on purpose — the two had
        drifted, so the Salute page already knew the source was plan-gated
        while the probe kept calling it."""
        for _ in range(3):
            dsm.record_failure("finnhub", "upgrades", reason="HTTP 403")
        row = next(m for m in dsm.snapshot() if m.source == "finnhub" and m.op == "upgrades")
        assert row.health == "unavailable"


class TestSecondsSinceLastFailure:
    def test_none_when_nothing_ever_failed(self):
        assert dsm.seconds_since_last_failure("finnhub", "upgrades") is None

    def test_measures_a_recent_failure(self):
        dsm.record_failure("finnhub", "upgrades", reason="HTTP 403")
        age = dsm.seconds_since_last_failure("finnhub", "upgrades")
        assert age is not None and age < 5


class TestSkipGuard:
    def test_skips_a_freshly_confirmed_plan_gated_endpoint(self):
        dsm.record_failure("finnhub", "upgrades", reason="HTTP 403")
        assert probes._skip_plan_gated("finnhub", "upgrades") is True

    def test_rechecks_once_the_window_has_passed(self, monkeypatch):
        dsm.record_failure("finnhub", "upgrades", reason="HTTP 403")
        monkeypatch.setattr(
            dsm, "seconds_since_last_failure",
            lambda *_: probes._PLAN_GATED_RECHECK_SECONDS + 1,
        )
        # A plan CAN be upgraded; the guard throttles, it does not disable.
        assert probes._skip_plan_gated("finnhub", "upgrades") is False

    def test_does_not_skip_a_source_that_merely_failed_once(self):
        """The guard must not silence a real outage — a 500 or a timeout is an
        incident and the probe has to keep watching it."""
        dsm.record_failure("finnhub", "news", reason="HTTP 503")
        assert probes._skip_plan_gated("finnhub", "news") is False
