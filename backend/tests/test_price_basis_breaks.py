"""Unrepaired splits already sitting inside the stored series.

`_check_price_basis` compares the incoming overlap bar against the stored one,
so it only ever sees a discontinuity at the EDGE of a fetch window. A break
already inside the history is invisible to it by construction: from the next
day on, stored and incoming are both on the new basis, the ratio is 1.0, and
it reports "basis OK" forever.

Measured on the live catalogue 2026-09-01: five names carried one, and the
damage was not cosmetic — TIT.MI held `rel_strength = 100.0`, the highest in
the entire universe, purely as an artifact of an unrepaired reverse split.
"""
from datetime import date, timedelta

import pytest

from app.services.ohlcv_service import _SPLIT_MIN_RATIO, find_basis_breaks


def _series(*steps):
    """steps: (price_ratio, volume_ratio) applied day by day from 100 / 1e6."""
    dates, closes, vols = [date(2026, 1, 1)], [100.0], [1_000_000.0]
    for pr, vr in steps:
        dates.append(dates[-1] + timedelta(days=1))
        closes.append(closes[-1] * pr)
        vols.append(vols[-1] * vr if vr is not None else None)
    return dates, closes, vols


class TestRealSplitsFromProduction:
    """The five actually found, with their measured price and volume ratios."""

    @pytest.mark.parametrize("name,pr,vr", [
        ("KLAC 10:1", 0.097, 9.66),
        ("SOXS 20:1", 0.054, 21.43),
        ("CRWD 4:1", 0.265, 6.93),
        ("8053.T 4:1", 0.246, 1.35),
        ("TIT.MI reverse 1:10", 10.003, 0.07),
    ])
    def test_is_detected(self, name, pr, vr):
        assert len(find_basis_breaks(*_series((pr, vr)))) == 1, name


class TestTheCovidLesson:
    """WHY THE MINIMUM RATIO IS 3.

    The first version of this detector started at 1.5 and returned 239 hits,
    dozens dated 9-18 March 2020. A 1.5 ratio means any single-day fall of
    ~30%: a market event, not a corporate action. Sweeping the parameters over
    the whole stored history gave min=3 / tol=0.08 → 14 hits, ZERO from the
    crash window, all five known splits still found.
    """

    @pytest.mark.parametrize("pr,vr", [
        (0.66, 2.7),   # OXY-shaped, 9 March 2020
        (0.70, 1.4),   # the typical crash bar of that week
        (0.62, 1.8),   # DVN-shaped
    ])
    def test_a_crash_is_not_a_split(self, pr, vr):
        assert find_basis_breaks(*_series((pr, vr))) == []

    def test_a_two_for_one_split_is_a_known_blind_spot(self):
        """Stated, not hidden. Tolerance cannot go below ~0.08 without losing
        true positives (real splits land 3-6% off the exact ratio because the
        price moves that day), and at 0.08 a minimum of 2.0 readmits the crash
        crowd. Constraining the 2-3 band by conserved dollar volume was tried
        and rejected: 3 crash rows returned and nothing new was found."""
        assert find_basis_breaks(*_series((0.5, 2.0))) == []
        assert _SPLIT_MIN_RATIO == 3.0


class TestVolumeIsTheDiscriminator:
    def test_price_and_volume_must_move_in_opposite_directions(self):
        """A split does not change the money traded, only the share count. A
        news move takes both up together — MDGL x3.68 with volume x10.8 on
        trial results, which the ratio test alone would have accepted."""
        assert find_basis_breaks(*_series((3.68, 10.83))) == []

    def test_a_forward_split_keeps_its_shape(self):
        b = find_basis_breaks(*_series((0.25, 4.0)))
        assert len(b) == 1 and b[0].matched_ratio == 4.0

    def test_missing_volume_does_not_block_detection(self):
        """Volume corroborates; it is not required. Some catalogue rows carry
        none, and a 10:1 price step is evidence enough on its own."""
        assert len(find_basis_breaks(*_series((0.1, None)))) == 1


class TestOrdinarySessions:
    @pytest.mark.parametrize("pr", [1.0, 1.05, 0.95, 1.30, 0.78])
    def test_a_normal_day_is_never_a_break(self, pr):
        assert find_basis_breaks(*_series((pr, 1.1))) == []

    def test_a_violent_move_that_is_not_a_split_ratio_is_ignored(self):
        """-70% is far beyond the band, but 1/0.30 = 3.33 sits 11% off 3:1 and
        so matches nothing. Written first with -85%, which FAILED: 1/0.15 =
        6.67 is within 8% of 7:1, and price-down-with-volume-up is the split
        signature — the detector was right and the expectation was wrong."""
        assert find_basis_breaks(*_series((0.30, 3.0))) == []

    def test_reports_every_break_in_a_long_series(self):
        breaks = find_basis_breaks(*_series((1.01, 1.0), (0.1, 10.0), (1.01, 1.0), (0.25, 4.0)))
        assert len(breaks) == 2


class TestNeverRaises:
    def test_empty_and_short_series(self):
        assert find_basis_breaks([], [], []) == []
        assert find_basis_breaks([date(2026, 1, 1)], [100.0], [1.0]) == []

    def test_zero_and_none_prices_are_skipped(self):
        dates = [date(2026, 1, i + 1) for i in range(3)]
        assert find_basis_breaks(dates, [100.0, 0.0, 10.0], [1.0, 1.0, 1.0]) == []
        assert find_basis_breaks(dates, [100.0, None, 10.0], [1.0, 1.0, 1.0]) == []

    def test_mismatched_lengths_do_not_crash(self):
        assert find_basis_breaks([date(2026, 1, 1)] * 3, [100.0, 10.0], [1.0]) == []
