"""Serialize the current persisted stock-ranking to JSON for the
non-regression gate (see tests/test_ranking_regression.py).

Usage:
    python -m scripts.rank_snapshot <out_path>

Reads the `stock_scores` table AS-IS (one row per stock, written by the
last recompute_all) — it does NOT recompute. The caller is responsible
for running recompute_all before snapshotting so the DB reflects the
code under test.

Output shape:
    {
      "<TICKER>": {
        "composite": float,
        "profitability": float|null, "sustainability": ...,
        "growth": ..., "value": ..., "momentum": ..., "sentiment": ...,
        "risk_tier": str,
        "coverage": float|null   # from breakdown._meta_global (QW5+)
      },
      ...
    }
Ticker collisions (the catalog has ~59 duplicate logical tickers) keep
the highest-composite row so the snapshot is deterministic.
"""
from __future__ import annotations

import json
import sys

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Stock, StockScore


def build_snapshot() -> dict[str, dict]:
    db = SessionLocal()
    try:
        rows = db.execute(
            select(Stock.ticker, StockScore).join(
                StockScore, StockScore.stock_id == Stock.id
            )
        ).all()
    finally:
        db.close()

    out: dict[str, dict] = {}
    for ticker, sc in rows:
        coverage = None
        try:
            bd = json.loads(sc.breakdown or "{}")
            mg = bd.get("_meta_global")
            if isinstance(mg, dict):
                coverage = mg.get("coverage")
        except (json.JSONDecodeError, TypeError):
            pass
        rec = {
            "composite": sc.composite,
            "profitability": sc.profitability,
            "sustainability": sc.sustainability,
            "growth": sc.growth,
            "value": sc.value,
            "momentum": sc.momentum,
            "sentiment": sc.sentiment,
            "risk_tier": sc.risk_tier,
            "coverage": coverage,
        }
        # Deterministic dedupe: keep the highest-composite row per ticker.
        prev = out.get(ticker)
        if prev is None or rec["composite"] > prev["composite"]:
            out[ticker] = rec
    return out


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python -m scripts.rank_snapshot <out_path>", file=sys.stderr)
        raise SystemExit(2)
    snap = build_snapshot()
    with open(sys.argv[1], "w", encoding="utf-8") as fh:
        json.dump(snap, fh, sort_keys=True, separators=(",", ":"))
    print(f"snapshot: {len(snap)} tickers -> {sys.argv[1]}")


if __name__ == "__main__":
    main()
