"""Historical-replay outcome backfill for the zero-coverage 63d detectors (B4-5).

WHY AN ARTIFACT AND NOT `signal_outcomes` ROWS
══════════════════════════════════════════════
The engine-quality spec promised a historical-replay population of the
`signal_outcomes` warehouse, and the `source` column ('live' | 'replay')
already exists for it. But `signal_outcomes.alert_id` is a NON-NULLABLE FK
onto `alerts` (idempotency anchor of the live maturation path) — a replayed
historical signal has no alert row to point at, and relaxing the column would
need a migration. So, no-migration design: this script COMPUTES the replay
outcomes and emits them as a versioned artifact
(`app/data/replay_outcomes_summary.json`) with per-detector × regime × tone ×
strength-band aggregates — the exact cube `detector_performance_service`
serves for live rows — which that service merges as a SEPARATE `replay`
block (labeled `source='replay'`, never mixed into the live hit rates).
If a future migration makes `alert_id` nullable, the per-signal observations
this script walks can be persisted directly and the artifact retired.

METHOD (mirrors app.scripts.signal_detector_outcomes — same replay machinery)
══════════════════════════════════════════════════════════════════════════════
  • Reuses `_load_universe` / `_universe_mean_fwd` (signal_factor_outcomes)
    and `_detector_horizon` (signal_detector_outcomes) — no re-implementation
    of the detector iteration beyond the windowed observation loop itself.
  • For each stock and each observation bar (every `--step` bars), the real
    `detect_signals()` runs on a `--window`-bar TRAILING window ending at the
    obs bar; matches outside `--detectors` are discarded.
  • Outcome labels replicate `signal_outcome_service.mature_outcomes`:
    close-to-close forward return at the detector's natural horizon,
    absolute directional hit, market-neutral hit vs the universe mean forward
    return on the same date, and the causal regime (close vs EMA200) at the
    trigger bar.
  • No look-ahead is structural: the detect window ends at the obs bar and an
    occurrence is counted ONLY when its forward close already exists in
    stored history — a signal on the last bars of a series produces nothing.
  • Deterministic given the same DB: no sampling randomness, no wall-clock
    dependence beyond the optional `--years` cutoff (stamped into `params`).

Run with uvicorn STOPPED (sole SQLite writer — the read here is heavy):
    cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.backfill_replay_outcomes
      --detectors a,b   comma-separated detector names
                        (default: the four most-fired 63d ones)
      --years N         only observation bars in the last N years (default 10)
      --dry-run         compute + print, do NOT write the artifact
      --sample N        use first N eligible stocks (default: all)
      --step N          bars between observation dates (default 42, the same
                        grid the calibration harness uses)
      --window N        trailing window bars fed to detect_signals (default 500)
      --min-bars N      require >= N bars of history (default 1000)
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
from loguru import logger

from app.scripts.signal_detector_outcomes import _detector_horizon
from app.scripts.signal_factor_outcomes import _load_universe, _universe_mean_fwd
from app.services.detector_performance_service import (
    _REGIME_ORDER,
    _STRENGTH_ORDER,
    _TONE_ORDER,
    _strength_band,
)
from app.services.signal_outcome_service import _REGIME_EMA, _ema
from app.signals.runner import detect_signals

# The four most-fired 63d detectors — the ones with ZERO live warehouse rows
# (first live maturations ~mid-August 2026). The replay fills exactly that gap.
DEFAULT_DETECTORS: tuple[str, ...] = (
    "trend_pullback", "adx_confirmation", "high52_momentum", "structure_break",
)

# Artifact destination (next to signal_calibration.json — the other generated
# study artifact). Module-level so tests can monkeypatch it to a tmp path.
_ARTIFACT_PATH = Path(__file__).resolve().parents[1] / "data" / "replay_outcomes_summary.json"

_PROGRESS_EVERY = 25  # stocks between progress log lines


@dataclass
class _ReplayObs:
    """One replayed historical signal occurrence with its labeled outcome."""
    detector: str
    tone: str                 # "bull" | "bear"
    strength: int | None
    regime: str | None        # "bull" | "bear" | None (EMA not computable)
    abs_hit: int              # 1/0 — close moved the signalled way
    mkt_hit: int | None       # 1/0 vs universe mean; None when no benchmark
    fwd_return: float         # close-to-close ratio over the horizon
    obs_date: str             # ISO date of the observation bar


def _cell(key: str, obs: list[_ReplayObs]) -> dict:
    """One aggregate cell, matching the live cube's shape (rates in %, return
    in %). `low_confidence` is deliberately NOT stored — the read endpoint
    stamps it against its own min_n, exactly like the live cells."""
    n = len(obs)
    abs_rate = sum(o.abs_hit for o in obs) / n * 100.0
    mkt_labels = [o.mkt_hit for o in obs if o.mkt_hit is not None]
    mkt_rate = (sum(mkt_labels) / len(mkt_labels) * 100.0) if mkt_labels else None
    avg_fwd = sum(o.fwd_return for o in obs) / n * 100.0
    return {
        "key": key,
        "n": n,
        "abs_hit_rate": round(abs_rate, 1),
        "mkt_neutral_hit_rate": round(mkt_rate, 1) if mkt_rate is not None else None,
        "avg_fwd_return": round(avg_fwd, 2),
    }


def _breakdown(obs: list[_ReplayObs], key_fn, order: tuple[str, ...]) -> list[dict]:
    groups: dict[str, list[_ReplayObs]] = defaultdict(list)
    for o in obs:
        groups[key_fn(o)].append(o)
    return [_cell(k, groups[k]) for k in order if k in groups]


def compute_replay_summary(
    db,
    *,
    detectors: tuple[str, ...] | list[str] = DEFAULT_DETECTORS,
    years: float | None = 10.0,
    step: int = 42,
    window: int = 500,
    min_bars: int = 1000,
    sample: int | None = None,
) -> dict:
    """Walk stored ohlcv_daily and build the replay-outcome artifact payload.

    Pure computation over the given Session — no writes, no network. The
    caller (main / tests) decides whether to persist the returned payload."""
    want = set(detectors)
    logger.info(f"[replay-outcomes] loading universe (min_bars={min_bars}, sample={sample}) ...")
    universe = _load_universe(db, min_bars=min_bars, sample=sample)
    logger.info(f"[replay-outcomes] {len(universe)} stocks")

    cutoff_iso: str | None = None
    if years is not None and years > 0:
        cutoff_iso = (date.today() - timedelta(days=round(years * 365.25))).isoformat()

    obs: list[_ReplayObs] = []
    n_calls = 0
    if universe:
        umean = _universe_mean_fwd(universe)
        date_to_idx = umean["_date_to_idx"]
        for sidx, s in enumerate(universe):
            c = s.closes
            n = len(c)
            # Causal regime series (same anchor mature_outcomes uses): one
            # EMA200 per stock, sampled at the obs bar.
            ema_arr = _ema(c, _REGIME_EMA) if n else np.array([])
            for i in range(window, n, step):
                if cutoff_iso is not None and s.dates[i] < cutoff_iso:
                    continue
                win = s.df.iloc[i - window:i + 1].reset_index(drop=True)
                n_calls += 1
                try:
                    matches = detect_signals(win)
                except Exception:  # noqa: BLE001 — one bad window must not kill the run
                    continue
                for m in matches:
                    if m.name not in want or m.tone not in ("bull", "bear"):
                        continue
                    h = _detector_horizon(m.name)
                    # No look-ahead: count the occurrence ONLY when the forward
                    # close already exists — a signal on the last bars of the
                    # series produces nothing.
                    if i + h >= n or c[i] <= 0:
                        continue
                    fwd = float(c[i + h] / c[i] - 1.0)
                    abs_hit = 1 if ((m.tone == "bull" and fwd > 0)
                                    or (m.tone == "bear" and fwd < 0)) else 0
                    # Market-neutral label vs the universe mean fwd return on
                    # the same date; None when the benchmark is missing (same
                    # nullable convention as the warehouse).
                    mkt_hit = None
                    di = date_to_idx.get(s.dates[i])
                    mh = umean.get(h)
                    mean = mh[di] if (mh is not None and di is not None) else np.nan
                    if np.isfinite(mean):
                        excess = fwd - float(mean)
                        dir_excess = excess if m.tone == "bull" else -excess
                        mkt_hit = 1 if dir_excess > 0 else 0
                    regime = None
                    if i < len(ema_arr) and ema_arr[i] > 0:
                        regime = "bull" if c[i] > ema_arr[i] else "bear"
                    obs.append(_ReplayObs(
                        detector=m.name, tone=m.tone,
                        strength=int(m.strength) if m.strength is not None else None,
                        regime=regime, abs_hit=abs_hit, mkt_hit=mkt_hit,
                        fwd_return=fwd, obs_date=s.dates[i],
                    ))
            if (sidx + 1) % _PROGRESS_EVERY == 0:
                logger.info(f"[replay-outcomes] {sidx + 1}/{len(universe)} stocks, "
                            f"{len(obs):,} occurrences so far")

    logger.info(f"[replay-outcomes] {n_calls:,} detect calls, {len(obs):,} occurrences")

    by_det: dict[str, list[_ReplayObs]] = defaultdict(list)
    for o in obs:
        by_det[o.detector].append(o)
    det_blocks: dict[str, dict] = {}
    for name in sorted(by_det, key=lambda k: (-len(by_det[k]), k)):
        rows = by_det[name]
        det_blocks[name] = {
            "total": _cell("totale", rows),
            "by_regime": _breakdown(rows, lambda o: o.regime or "n/d", _REGIME_ORDER),
            "by_tone": _breakdown(rows, lambda o: o.tone, _TONE_ORDER),
            "by_strength": _breakdown(
                rows, lambda o: _strength_band(o.strength), _STRENGTH_ORDER
            ),
        }

    dates = [o.obs_date for o in obs]
    return {
        "version": "1",
        "generated_by": "app.scripts.backfill_replay_outcomes",
        # Provenance marker: consumers must surface these aggregates as a
        # SEPARATE replay segment, never blended into live hit rates (the
        # replay has no emission-gate survivorship of the live path).
        "source": "replay",
        "generated_at": datetime.now(UTC).isoformat(),
        "params": {
            "detectors": sorted(want),
            "years": years,
            "step": step,
            "window": window,
            "min_bars": min_bars,
            "sample": sample,
        },
        "universe_stocks": len(universe),
        "n_signals": len(obs),
        "date_min": min(dates) if dates else None,
        "date_max": max(dates) if dates else None,
        "detectors": det_blocks,
    }


def write_artifact(payload: dict) -> Path:
    """Atomically persist the payload (tmp + rename, indent=2 like the
    calibration artifact so the git diff stays readable)."""
    out = _ARTIFACT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(out)
    return out


def _print_report(payload: dict) -> None:
    print(f"\n{'#'*78}\n#  REPLAY OUTCOME BACKFILL (source='replay')")
    print(f"#  universe={payload['universe_stocks']}  occurrences={payload['n_signals']:,}"
          f"  span={payload['date_min']}..{payload['date_max']}\n{'#'*78}")
    print(f"\n{'detector':<24}{'n':>7}{'absHit%':>9}{'mnHit%':>8}{'avgFwd%':>9}")
    print("-" * 60)
    for name, block in payload["detectors"].items():
        t = block["total"]
        mn = f"{t['mkt_neutral_hit_rate']:>8.1f}" if t["mkt_neutral_hit_rate"] is not None else f"{'n/a':>8}"
        print(f"{name:<24}{t['n']:>7}{t['abs_hit_rate']:>9.1f}{mn}{t['avg_fwd_return']:>+9.2f}")
    print()


def run(*, detectors: tuple[str, ...] | list[str] = DEFAULT_DETECTORS,
        years: float | None = 10.0, step: int = 42, window: int = 500,
        min_bars: int = 1000, sample: int | None = None,
        dry_run: bool = False) -> dict:
    """CLI entrypoint body. Returns the computed payload (tests inspect it)."""
    import app.core.db as dbm  # noqa: PLC0415 — test monkeypatch seam (conftest swaps SessionLocal)

    with dbm.SessionLocal() as db:
        payload = compute_replay_summary(
            db, detectors=detectors, years=years, step=step,
            window=window, min_bars=min_bars, sample=sample,
        )
    _print_report(payload)
    if dry_run:
        print("  [dry-run] artifact NOT written\n")
    else:
        out = write_artifact(payload)
        print(f"  wrote {out} ({len(payload['detectors'])} detectors, "
              f"{payload['n_signals']:,} occurrences)\n")
    return payload


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--detectors", type=str, default=",".join(DEFAULT_DETECTORS),
                    help="comma-separated detector names")
    ap.add_argument("--years", type=float, default=10.0,
                    help="observation-bar cutoff in years back from today (0 = all history)")
    ap.add_argument("--dry-run", action="store_true",
                    help="compute + print, do not write the artifact")
    ap.add_argument("--sample", type=int, default=None)
    ap.add_argument("--step", type=int, default=42)
    ap.add_argument("--window", type=int, default=500)
    ap.add_argument("--min-bars", type=int, default=1000)
    args = ap.parse_args()
    run(
        detectors=tuple(d.strip() for d in args.detectors.split(",") if d.strip()),
        years=(args.years if args.years > 0 else None),
        step=args.step, window=args.window, min_bars=args.min_bars,
        sample=args.sample, dry_run=args.dry_run,
    )
