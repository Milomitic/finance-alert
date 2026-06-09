"""One-off backfill + parity check for the signal_outcomes warehouse.

Matures every elapsed signal alert into signal_outcomes (idempotent), then
prints a PARITY report: per-detector mean(abs_hit) from the table vs the
calibration artifact's base_rate, and mean(mkt_neutral_hit) vs mkt_neutral_hit.
They should agree within sampling noise (the table reproduces the same labels
the calibration harness measured — just persisted instead of re-replayed).

Run with uvicorn STOPPED (sole SQLite writer):
    cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.backfill_signal_outcomes
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select

import app.core.db as dbm
from app.models import SignalOutcome
from app.services.signal_outcome_service import mature_outcomes
from app.signals.calibration_map import get_calibration


def main() -> None:
    with dbm.SessionLocal() as db:
        added = mature_outcomes(db, commit=True)
        rows = db.execute(
            select(SignalOutcome.detector, SignalOutcome.abs_hit,
                   SignalOutcome.mkt_neutral_hit)
        ).all()

    by_det: dict[str, list[tuple[int, int | None]]] = defaultdict(list)
    for det, ah, mh in rows:
        by_det[det].append((ah, mh))

    cal = get_calibration()
    print(f"\nmatured this run: {added}   total outcome rows: {len(rows)}")
    print(f"\n{'detector':<22}{'n':>7}{'absHit%':>9}{'base':>6}{'Δ':>6}"
          f"{'mnHit%':>8}{'mnCal':>7}")
    print("-" * 66)
    for det in sorted(by_det, key=lambda k: -len(by_det[k])):
        arr = by_det[det]
        n = len(arr)
        abs_pct = 100.0 * sum(a for a, _ in arr) / n
        base = cal.base_rate(det)
        mn_vals = [m for _, m in arr if m is not None]
        mn_pct = (100.0 * sum(mn_vals) / len(mn_vals)) if mn_vals else float("nan")
        mn_cal = cal.skill(det)
        print(f"{det:<22}{n:>7}{abs_pct:>9.1f}{base:>6.0f}{abs_pct - base:>+6.1f}"
              f"{mn_pct:>8.1f}{(mn_cal if mn_cal is not None else float('nan')):>7.1f}")


if __name__ == "__main__":
    main()
