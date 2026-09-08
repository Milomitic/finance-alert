"""Bars that were never traded, and where a series starts being real.

INDV is why this exists. It carried two opposing basis breaks three sessions
apart (x0.159 on 2022-11-23, x6.719 on 2022-11-28), which read as a handful of
corrupt bars wanting a bar-level repair. Measured against production, it was
nothing of the kind:

    2016-2023   1,911 bars   36-89% with o==h==l==c   14-52% with zero volume
    2024-2026     672 bars              0%                       0%

Indivior moved its primary listing to Nasdaq in 2024. Everything before that is
a thin secondary line where the price was CARRIED rather than observed, and the
November 2022 pair is just its most visible artifact. Deleting those three days
would have left 1,908 bars of the same bad provenance and called it repaired.

THE DISCRIMINATOR IS VOLUME, and it must be zero volume rather than a flat bar.
A real illiquid session can print o==h==l==c with genuine volume — one price,
but trades happened. Zero volume means no trade occurred at all, so whatever
sits in `close` was carried over from before. In INDV's history every
zero-volume bar is also flat (562 of each), while 524 flat bars DO carry
volume; treating flatness as the marker would condemn those 524 on suspicion.
"""

from datetime import date, timedelta

from app.scripts.repair_bar_quality import recommend
from app.services.ohlcv_service import BarQuality, assess_bar_quality

D0 = date(2024, 1, 1)


def _series(rows):
    """rows: list of (close, volume) or (open, high, low, close, volume)."""
    dates, o, h, low, c, v = [], [], [], [], [], []
    for i, r in enumerate(rows):
        dates.append(D0 + timedelta(days=i))
        if len(r) == 2:
            close, vol = r
            o.append(close), h.append(close), low.append(close), c.append(close)
        else:
            a, b, x, close, vol = r
            o.append(a), h.append(b), low.append(x), c.append(close)
        v.append(vol)
    return assess_bar_quality(dates, o, h, low, c, v)


class TestUntradedBars:
    def test_a_fully_traded_series_is_clean_from_its_first_bar(self):
        q = _series([(10.0, 1000), (10.5, 900), (11.0, 1100)])
        assert q.untraded == 0
        assert q.clean_from == D0
        assert q.clean_bars == 3

    def test_zero_volume_is_untraded(self):
        q = _series([(10.0, 0), (10.5, 900)])
        assert q.untraded == 1

    def test_missing_volume_is_untraded_too(self):
        # A null is not "no trades" in the data's own words, but we cannot tell
        # it apart from one, and a price we cannot vouch for is not evidence.
        q = _series([(10.0, None), (10.5, 900)])
        assert q.untraded == 1

    def test_a_flat_bar_that_actually_traded_is_NOT_untraded(self):
        # 524 of INDV's flat bars carry real volume. One price with trades
        # behind it is an illiquid session, not a fabricated one.
        q = _series([(10.0, 10.0, 10.0, 10.0, 37500), (10.5, 10.6, 10.4, 10.5, 900)])
        assert q.untraded == 0
        assert q.flat == 1


class TestWhereTheSeriesBecomesReal:
    def test_a_bad_prefix_then_clean_gives_the_boundary(self):
        # The INDV shape.
        q = _series([(9.0, 0), (9.0, 0), (10.0, 500), (10.5, 900), (11.0, 800)])
        assert q.clean_from == D0 + timedelta(days=2)
        assert q.clean_bars == 3
        assert q.untraded == 2

    def test_the_run_is_the_TRAILING_one_not_the_longest(self):
        # A long clean stretch early is worthless if the recent data is broken:
        # what gets kept is the tail, so that is what must be measured.
        rows = [(10.0, 100)] * 8 + [(10.0, 0)] + [(10.0, 100)] * 2
        q = _series(rows)
        assert q.clean_bars == 2
        assert q.clean_from == D0 + timedelta(days=9)

    def test_an_untraded_last_bar_leaves_no_clean_suffix(self):
        q = _series([(10.0, 100), (10.0, 0)])
        assert q.clean_from is None
        assert q.clean_bars == 0

    def test_scattered_damage_leaves_a_short_tail(self):
        # This is the signature that says DROP BARS rather than truncate: the
        # damage is spread, so cutting at the boundary would throw away almost
        # everything while only a few bars are actually bad.
        rows = []
        for i in range(30):
            rows.append((10.0, 0) if i % 7 == 0 else (10.0, 500))
        q = _series(rows)
        assert q.untraded == 5
        assert q.clean_bars < 7  # a truncate here would be absurd
        assert q.total == 30


class TestWhichRepair:
    """The recommendation decides a DESTRUCTIVE action, so it is tested.

    Bar count is deliberately not the objective. On INDV, dropping the untraded
    bars costs 562 and truncating costs 1,911 — the cheaper option loses nearly
    four times fewer bars and leaves 1,349 of them 39% flat. The question is
    whether what remains is a coherent record, not how much of it there is.
    """

    def test_a_bad_prefix_and_a_real_tail_says_truncate(self):
        # The INDV shape: the damage is a regime, not a scatter.
        q = BarQuality(total=2583, untraded=562, flat=1086,
                       clean_from=date(2024, 1, 2), clean_bars=672)
        assert "truncate-to-clean" in recommend(q, pre_flat=0.57, tail_flat=0.0)

    def test_scattered_damage_in_a_real_series_says_drop(self):
        q = BarQuality(total=2500, untraded=12, flat=30,
                       clean_from=date(2024, 1, 2), clean_bars=900)
        assert "drop-untraded" in recommend(q, pre_flat=0.01, tail_flat=0.0)

    def test_a_short_clean_tail_never_says_truncate(self):
        # Cutting to 40 bars does not repair a ticker, it relocates the problem
        # below has_full_data.
        q = BarQuality(total=2500, untraded=900, flat=1200,
                       clean_from=date(2026, 7, 1), clean_bars=40)
        out = recommend(q, pre_flat=0.60, tail_flat=0.0)
        assert "drop-untraded" in out
        assert "truncate" not in out.replace("troncare", "")

    def test_a_flat_prefix_with_a_flat_tail_is_not_a_regime_change(self):
        # Both halves equally flat means one thin instrument throughout, and
        # cutting the first half would not make the second half better.
        q = BarQuality(total=2500, untraded=50, flat=1200,
                       clean_from=date(2024, 1, 2), clean_bars=900)
        assert "drop-untraded" in recommend(q, pre_flat=0.50, tail_flat=0.45)

    def test_a_clean_series_is_left_alone(self):
        q = BarQuality(total=2500, untraded=0, flat=3,
                       clean_from=date(2016, 1, 4), clean_bars=2500)
        assert recommend(q, 0.0, 0.0) == "niente da fare"
