"""Conditional screen: the anti-look-ahead guarantee and the FDR arithmetic.

These two are worth testing precisely because a bug in either is INVISIBLE in
the output. A look-ahead in the tercile boundaries produces a beautiful,
confident, entirely fake result; a wrong FDR produces survivors that are pure
multiple-testing noise. Both would look exactly like a discovery.
"""
import csv
import gzip
import json
from datetime import date, timedelta

from app.scripts.conditional_screen_grid import (
    _bh,
    _mde,
    _two_proportion_p,
    _wilson,
)
from app.scripts.conditional_screen_replay import _BURN_IN, _ExpandingTercile


def _series(values: list[float], start: date = date(2000, 1, 3)):
    return [(start + timedelta(days=i), v) for i, v in enumerate(values)]


# ─── the look-ahead guarantee ─────────────────────────────────────────────


def test_a_label_never_changes_when_the_future_arrives():
    """THE defining property of a causal boundary.

    If appending later observations can change how an earlier date is
    labelled, then the label encodes the future and every result built on it
    is worthless. This is the single most important assertion in the study."""
    past = [10.0 + (i % 7) for i in range(_BURN_IN + 50)]
    asof = date(2000, 1, 3) + timedelta(days=_BURN_IN + 40)

    before = _ExpandingTercile(_series(past)).label_at(asof)
    # A violent regime shift AFTER the as-of date — the kind of thing that
    # would redraw whole-sample terciles (think 2020 vol).
    after = _ExpandingTercile(_series(past + [500.0] * 400)).label_at(asof)

    assert before == after != "na"


def test_boundaries_come_from_history_not_from_the_whole_sample():
    """A value that is high against what came BEFORE it must read 'high',
    even when the rest of the series later dwarfs it."""
    rising = [float(i) for i in range(_BURN_IN + 100)]
    t = _ExpandingTercile(_series(rising))
    # Late in the series, the newest value is by construction the largest seen
    # so far -> 'high'. A whole-sample cut would call the same point 'low',
    # because everything after it is bigger.
    asof = date(2000, 1, 3) + timedelta(days=_BURN_IN + 50)
    assert t.label_at(asof) == "high"


def test_no_label_before_the_burn_in():
    """With too little history a tercile is a guess dressed as a measurement."""
    t = _ExpandingTercile(_series([1.0, 2.0, 3.0] * 10))
    assert t.label_at(date(2000, 1, 20)) == "na"


def test_the_reading_is_never_same_day():
    """Publication lag: FRED posts late and revises. A same-day read would be
    a look-ahead on any series that lands after the close."""
    vals = [1.0] * (_BURN_IN + 10) + [999.0]
    s = _series(vals)
    spike_date = s[-1][0]
    t = _ExpandingTercile(s)
    # Asking ON the spike date must not see the spike: the last usable
    # observation is the previous one, which is flat.
    assert t.label_at(spike_date) != "high"
    assert t.label_at(spike_date + timedelta(days=1)) == "high"


def test_change_labels_are_also_causal():
    flat = [10.0] * (_BURN_IN + 60)
    asof = date(2000, 1, 3) + timedelta(days=_BURN_IN + 30)
    a = _ExpandingTercile(_series(flat)).change_label_at(asof)
    b = _ExpandingTercile(_series(flat + [1.0] * 300)).change_label_at(asof)
    assert a == b


# ─── the multiple-testing arithmetic ──────────────────────────────────────


def test_one_small_p_among_many_tests_does_not_survive():
    """The whole reason this script exists. p=0.002 is 'significant' alone and
    unremarkable among 300 tests — roughly what chance delivers."""
    pvals = [0.002] + [0.5] * 299
    qv, _ = _bh(pvals, 0.10)
    assert qv[0] > 0.10, f"q={qv[0]:.3f} — a lone p=0.002 must not clear FDR at m=300"


def test_a_genuinely_strong_effect_still_survives():
    """The correction must not be so blunt that nothing can ever pass."""
    pvals = [1e-8, 1e-7, 1e-7] + [0.5] * 297
    qv, _ = _bh(pvals, 0.10)
    assert qv[0] <= 0.10


def test_q_values_are_monotone_in_p():
    pvals = [0.001, 0.01, 0.02, 0.04, 0.2, 0.9]
    qv, _ = _bh(pvals, 0.10)
    ordered = [q for _, q in sorted(zip(pvals, qv, strict=True))]
    assert ordered == sorted(ordered), "BH q-values must not decrease as p grows"


def test_bh_matches_the_hand_computed_definition():
    """q_i = min over j>=i of (p_j * m / j) on the p-sorted list."""
    pvals = [0.01, 0.02, 0.03]
    qv, _ = _bh(pvals, 0.10)
    assert qv[0] == min(0.01 * 3 / 1, 0.02 * 3 / 2, 0.03 * 3 / 3)
    assert qv[2] == 0.03


def test_empty_grid_is_not_a_crash():
    assert _bh([], 0.1) == ([], None)


# ─── the per-cell statistics ──────────────────────────────────────────────


def test_identical_rates_are_not_a_difference():
    p, _ = _two_proportion_p(50, 100, 100, 200)
    assert p > 0.9


def test_a_large_separation_is_detected():
    p, z = _two_proportion_p(90, 100, 30, 100)
    assert p < 1e-10
    assert z > 0


def test_a_tiny_sample_cannot_claim_anything():
    p, _ = _two_proportion_p(1, 1, 0, 1)
    assert p == 1.0


def test_wilson_brackets_the_estimate_and_tightens_with_n():
    lo_s, hi_s = _wilson(30, 50)
    lo_l, hi_l = _wilson(3000, 5000)
    assert lo_s < 0.6 < hi_s
    assert (hi_l - lo_l) < (hi_s - lo_s)


def test_mde_shrinks_as_the_sample_grows():
    """The column that keeps 'no effect' apart from 'no power'."""
    assert _mde(50, 50) > _mde(500, 500) > _mde(5000, 5000)


# ─── end-to-end over the grid ─────────────────────────────────────────────


def _write_rows(path, rows):
    cols = ("detector", "tone", "date", "stock_id", "bar_i", "horizon",
            "hit", "excess", "period", "vix_level", "regime")
    with gzip.open(path, "wt", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        w.writerows(rows)


def test_overlapping_windows_collapse_into_one_episode(tmp_path):
    """Twenty observations three bars apart, all inside one 63-bar forward
    window of the same stock, are ONE independent look at the market — not
    twenty. If this collapse breaks, every interval in the study is too
    narrow and the survivors are manufactured."""
    from app.scripts import conditional_screen_grid as grid

    src = tmp_path / "rows.csv.gz"
    out = tmp_path / "rep.json"
    rows = []
    for i in range(0, 60, 3):          # bar_i 0..57 -> all //63 == 0
        rows.append(("d1", "bull", "2020-01-01", 1, i, 63, 1, "0.01", "train", "high", "bull"))
    for i in range(0, 60, 3):
        rows.append(("d1", "bull", "2020-01-01", 2, i, 63, 0, "-0.01", "train", "low", "bull"))
    _write_rows(src, rows)

    grid.run(src=str(src), out=str(out), q=0.10)
    report = json.loads(out.read_text(encoding="utf-8"))
    # 40 rows, but only 2 genuinely independent episodes (one per stock).
    assert report["rows"] == 40
    # Both cells fall under the episode floor, so nothing is testable —
    # which is the correct answer for two observations.
    assert report["cells_tested"] == 0


def test_a_missing_input_file_is_reported_not_raised(tmp_path, capsys):
    from app.scripts import conditional_screen_grid as grid

    grid.run(src=str(tmp_path / "nope.csv.gz"), out=str(tmp_path / "o.json"))
    assert "Run app.scripts.conditional_screen_replay first" in capsys.readouterr().out


# ─── the unit of analysis (the nine-false-survivors bug) ──────────────────


def test_the_t_distribution_is_stricter_than_the_normal_at_small_n():
    """The block test runs on a handful of observations. Using a normal there
    is exactly how a false finding gets born, so the t-tail must be fatter."""
    from app.scripts.conditional_screen_grid import _phi, _t_two_sided_p

    normal_p = 2 * (1 - _phi(2.5))
    assert _t_two_sided_p(2.5, df=4) > normal_p * 2


def test_t_p_values_match_known_values():
    from app.scripts.conditional_screen_grid import _t_two_sided_p

    # t(2.776, df=4) is the classic 95% two-sided critical value.
    assert abs(_t_two_sided_p(2.776, 4) - 0.05) < 0.001
    # t(2.228, df=10) likewise.
    assert abs(_t_two_sided_p(2.228, 10) - 0.05) < 0.001


def test_contiguous_months_group_into_one_block():
    from app.scripts.conditional_screen_grid import _blocks

    months = {"2020-01", "2020-02", "2020-03", "2021-06", "2021-07"}
    assert [len(b) for b in _blocks(months)] == [3, 2]


def test_a_market_wide_condition_is_not_credited_with_thousands_of_samples(tmp_path):
    """THE regression test for the nine false survivors.

    300 stocks all see the same VIX on the same day. A cell with tens of
    thousands of rows spread over three months is THREE-ish looks at that
    state, not tens of thousands — and a difference that large-n statistics
    would call overwhelming must not survive here."""
    from app.scripts import conditional_screen_grid as grid

    src = tmp_path / "rows.csv.gz"
    out = tmp_path / "rep.json"
    rows = []
    # One short 'high' episode where the detector happens to do very well,
    # and a long 'low' stretch where it does averagely. Row counts are huge.
    for stock in range(300):
        for k in range(8):
            rows.append(("d1", "bull", f"2020-0{1 + k % 3}-15", stock, k * 100, 5,
                         1, "0.05", "train", "high", "bull"))
        for k in range(8):
            rows.append(("d1", "bull", f"2021-0{1 + k % 6}-15", stock, k * 100, 5,
                         0, "-0.01", "train", "low", "bull"))
    _write_rows(src, rows)

    grid.run(src=str(src), out=str(out), q=0.10)
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["rows"] == 4800
    vix = [c for c in report["all_cells"] if c["condition"] == "vix_level"]
    for c in vix:
        assert c["unit"] == "time_block", "a market-wide condition must not use stock episodes"
    assert not [c for c in vix if c["survives"]], (
        "a 100pp difference across ~3 time blocks is not evidence — "
        "the market-wide clustering correction is not being applied"
    )
