"""Local, synthetic benchmark; never connects to the configured application DB.

Run from backend: python scripts/benchmark_security_performance.py
The baseline is the two-query sector_rank implementation at cloud 34159dd.
Do not interpret SQLite timings as PostgreSQL/OCI latency measurements.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.db import Base
from app.models import Stock, TechnicalScore
from app.services.technical_sector_rank import sector_rank


def baseline(db, stock_id, sector, composite):
    peers = db.scalar(
        select(func.count()).select_from(TechnicalScore)
        .join(Stock, Stock.id == TechnicalScore.stock_id).where(Stock.sector == sector)
    ) or 0
    stronger = db.scalar(
        select(func.count()).select_from(TechnicalScore)
        .join(Stock, Stock.id == TechnicalScore.stock_id)
        .where(Stock.sector == sector, TechnicalScore.composite > composite,
               TechnicalScore.stock_id != stock_id)
    ) or 0
    return stronger + 1, peers


def main():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    queries = 0

    def counted(*_):
        nonlocal queries
        queries += 1

    with Session(engine) as db:
        for i in range(1000):
            stock = Stock(ticker=f"BENCH{i}", name="Synthetic", exchange="TEST",
                          sector=f"sector{i % 5}")
            db.add(stock)
            db.flush()
            db.add(TechnicalScore(stock_id=stock.id, composite=i % 101,
                                  posture="Neutro", breakdown="{}", computed_at=datetime.now(UTC)))
        db.commit()
        event.listen(engine, "before_cursor_execute", counted)
        timings = {"before": [], "after": []}
        counts = {"before": 0, "after": 0}
        for _ in range(20):
            assert baseline(db, 1, "sector0", 0) == sector_rank(db, 1, "sector0", 0)
        for i in range(300):
            # Alternate measurement order to reduce systematic warmup bias.
            functions = [("before", baseline), ("after", sector_rank)]
            if i % 2:
                functions.reverse()
            for name, fn in functions:
                queries = 0
                start = time.perf_counter_ns()
                result = fn(db, 1, "sector0", 0)
                timings[name].append((time.perf_counter_ns() - start) / 1_000_000)
                counts[name] += queries
                assert result == (199, 200)
        output = {
            "scope": "Synthetic SQLite, 1000 stocks / 5 sectors; no provider or cloud latency",
            "iterations_per_variant": 300,
            "results": {
                name: {"p50_ms": round(statistics.median(values), 4),
                       "p95_ms": round(sorted(values)[int(len(values) * .95)], 4),
                       "sql_statements_per_call": counts[name] / len(values)}
                for name, values in timings.items()
            },
        }
        print(json.dumps(output, indent=2))
    engine.dispose()


if __name__ == "__main__":
    main()
