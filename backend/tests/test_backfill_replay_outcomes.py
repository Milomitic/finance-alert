"""Tests for the historical-replay outcome backfill (B4-5).

The script's replay loop calls the REAL `detect_signals` in production; here
we monkeypatch it (module seam `bro.detect_signals`) with a deterministic fake
that fires on chosen bar dates — the tests exercise the script's own logic:

  - outcome math (abs hit, market-neutral hit vs universe mean, avg forward
    return, regime at the trigger bar) on a seeded mini-universe;
  - NO-LOOK-AHEAD sanity: a signal on the last bars, whose forward window
    doesn't fully exist in stored history, produces NOTHING;
  - detector filtering (matches outside --detectors are discarded);
  - the --years observation cutoff;
  - source labeling ('replay') + params echo in the artifact payload;
  - determinism given the same DB;
  - artifact write vs --dry-run.

The detector horizon is monkeypatched to 5 bars so fixtures stay small (the
real 63d horizon would need 100+ bars per stock for no benefit here).
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import OhlcvDaily, Stock
from app.scripts import backfill_replay_outcomes as bro
from app.signals.detectors.base import SignalMatch

# --------------------------------------------------------------------------- #
# Fixtures / helpers                                                          #
# --------------------------------------------------------------------------- #

_START = date(2026, 1, 1)
_N_BARS = 40
_H = 5          # monkeypatched detector horizon
_WINDOW = 5
_MIN_BARS = 30


def _bar_date(i: int, start: date = _START) -> str:
    return (start + timedelta(days=i)).isoformat()


def _seed_stock(
    db: Session, *, ticker: str = "AAA", n_bars: int = _N_BARS,
    start: date = _START, base: float = 100.0,
) -> Stock:
    """One stock with `n_bars` daily bars, closes strictly increasing
    (base + i) — every bull signal is an abs hit by construction."""
    stock = Stock(ticker=ticker, exchange="TST", name=ticker)
    db.add(stock)
    db.flush()
    for i in range(n_bars):
        c = base + i
        db.add(OhlcvDaily(
            stock_id=stock.id, date=start + timedelta(days=i),
            open=c, high=c + 1, low=c - 1, close=c, volume=1_000,
        ))
    db.commit()
    return stock


def _fake_detect(fire_dates: set[str], *, name: str = "trend_pullback",
                 tone: str = "bull", strength: int = 80):
    """detect_signals stand-in: fires one match when the window's LAST bar
    date is in `fire_dates` (i.e. the signal is knowable at that obs bar)."""
    def _detect(win, **_kw):
        last = str(win.iloc[-1]["date"])[:10]
        if last in fire_dates:
            return [SignalMatch(
                name=name, tone=tone, signal_date=last, chain=[],
                invalidation=None, strength=strength, probability=55,
            )]
        return []
    return _detect


@pytest.fixture(autouse=True)
def _short_horizon(monkeypatch: pytest.MonkeyPatch):
    """5-bar horizon for every detector — keeps fixtures small."""
    monkeypatch.setattr(bro, "_detector_horizon", lambda _name: _H)


def _compute(db: Session, **overrides) -> dict:
    kw = dict(
        detectors=bro.DEFAULT_DETECTORS, years=None,
        step=1, window=_WINDOW, min_bars=_MIN_BARS,
    )
    kw.update(overrides)
    return bro.compute_replay_summary(db, **kw)


# --------------------------------------------------------------------------- #
# Outcome math on a deterministic mini-universe                               #
# --------------------------------------------------------------------------- #

def test_deterministic_outcomes_and_aggregates(db: Session, monkeypatch):
    """Two fires on a rising series: both abs hits; with a 1-stock universe
    the market benchmark equals the stock's own return → excess 0 → mkt-
    neutral hit-rate 0. Regime bull (close above the lagging EMA)."""
    _seed_stock(db)
    fires = {_bar_date(10), _bar_date(20)}
    monkeypatch.setattr(bro, "detect_signals", _fake_detect(fires))

    out = _compute(db)
    assert out["n_signals"] == 2
    assert out["date_min"] == _bar_date(10)
    assert out["date_max"] == _bar_date(20)
    block = out["detectors"]["trend_pullback"]
    total = block["total"]
    assert total == {
        "key": "totale",
        "n": 2,
        "abs_hit_rate": 100.0,
        # dir_excess is exactly 0 (single-stock universe) → not a hit.
        "mkt_neutral_hit_rate": 0.0,
        # fwd = 5/110 and 5/120 → mean 4.3561% → 4.36.
        "avg_fwd_return": 4.36,
    }
    tones = {c["key"]: c for c in block["by_tone"]}
    assert tones["bull"]["n"] == 2
    bands = {c["key"]: c for c in block["by_strength"]}
    assert bands[">=75"]["n"] == 2
    regimes = {c["key"]: c for c in block["by_regime"]}
    assert regimes["bull"]["n"] == 2


def test_deterministic_given_same_db(db: Session, monkeypatch):
    _seed_stock(db)
    monkeypatch.setattr(
        bro, "detect_signals", _fake_detect({_bar_date(10), _bar_date(20)})
    )
    a = _compute(db)
    b = _compute(db)
    # Identical modulo the generation timestamp.
    a.pop("generated_at")
    b.pop("generated_at")
    assert a == b


# --------------------------------------------------------------------------- #
# No look-ahead                                                               #
# --------------------------------------------------------------------------- #

def test_signal_without_full_forward_window_produces_nothing(
    db: Session, monkeypatch,
):
    """Fires on the LAST bar (39) and on bar 35 (whose 5-bar forward close
    would be the non-existent bar 40): neither has a stored forward close →
    zero occurrences. The forward return is the ONLY thing that looks past
    the obs bar, and it must already exist in history."""
    _seed_stock(db)
    monkeypatch.setattr(
        bro, "detect_signals",
        _fake_detect({_bar_date(_N_BARS - 1), _bar_date(_N_BARS - _H)}),
    )
    out = _compute(db)
    assert out["n_signals"] == 0
    assert out["detectors"] == {}
    assert out["date_min"] is None and out["date_max"] is None


def test_bar_with_exactly_one_full_horizon_counts(db: Session, monkeypatch):
    """Boundary: bar n-1-H is the LAST obs bar whose forward close exists."""
    _seed_stock(db)
    monkeypatch.setattr(
        bro, "detect_signals", _fake_detect({_bar_date(_N_BARS - 1 - _H)})
    )
    assert _compute(db)["n_signals"] == 1


# --------------------------------------------------------------------------- #
# Filters                                                                     #
# --------------------------------------------------------------------------- #

def test_matches_outside_requested_detectors_are_discarded(
    db: Session, monkeypatch,
):
    _seed_stock(db)
    monkeypatch.setattr(
        bro, "detect_signals",
        _fake_detect({_bar_date(10)}, name="candle_reversal"),
    )
    out = _compute(db)  # DEFAULT_DETECTORS: the four 63d ones
    assert out["n_signals"] == 0

    out = _compute(db, detectors=("candle_reversal",))
    assert out["n_signals"] == 1
    assert set(out["detectors"]) == {"candle_reversal"}


def test_years_cutoff_excludes_old_observation_bars(db: Session, monkeypatch):
    """Bars end today; a fire 29 days back falls outside a ~20-day cutoff
    while a fire 14 days back stays in."""
    start = date.today() - timedelta(days=_N_BARS - 1)
    _seed_stock(db, start=start)
    fires = {_bar_date(10, start), _bar_date(25, start)}  # 29 and 14 days ago
    monkeypatch.setattr(bro, "detect_signals", _fake_detect(fires))

    out = _compute(db, years=20 / 365.25)  # cutoff ≈ 20 days back
    assert out["n_signals"] == 1
    assert out["date_min"] == _bar_date(25, start)


# --------------------------------------------------------------------------- #
# Artifact payload + write / dry-run                                          #
# --------------------------------------------------------------------------- #

def test_payload_is_labeled_replay_with_params(db: Session, monkeypatch):
    _seed_stock(db)
    monkeypatch.setattr(bro, "detect_signals", _fake_detect({_bar_date(10)}))
    out = _compute(db)
    assert out["source"] == "replay"
    assert out["generated_by"] == "app.scripts.backfill_replay_outcomes"
    assert out["params"]["detectors"] == sorted(bro.DEFAULT_DETECTORS)
    assert out["params"]["step"] == 1
    assert out["params"]["window"] == _WINDOW
    assert out["universe_stocks"] == 1
    # Cells do NOT embed low_confidence — the endpoint stamps it vs min_n.
    assert "low_confidence" not in out["detectors"]["trend_pullback"]["total"]


def test_run_writes_artifact_and_dry_run_does_not(
    db: Session, monkeypatch, tmp_path,
):
    _seed_stock(db)
    monkeypatch.setattr(bro, "detect_signals", _fake_detect({_bar_date(10)}))
    target = tmp_path / "replay_outcomes_summary.json"
    monkeypatch.setattr(bro, "_ARTIFACT_PATH", target)

    kw = dict(years=None, step=1, window=_WINDOW, min_bars=_MIN_BARS)
    bro.run(dry_run=True, **kw)
    assert not target.exists()

    payload = bro.run(dry_run=False, **kw)
    assert target.exists()
    on_disk = json.loads(target.read_text(encoding="utf-8"))
    assert on_disk["source"] == "replay"
    assert on_disk["n_signals"] == payload["n_signals"] == 1
    assert list(on_disk["detectors"]) == ["trend_pullback"]
    # Atomic write: no .tmp leftover.
    assert list(tmp_path.glob("*.tmp")) == []
