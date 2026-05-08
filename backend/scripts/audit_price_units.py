"""Audit price-unit consistency across the catalog.

Walks every stock with a ticker suffix that historically maps to a
minor-unit currency (.L = GBp, .JO = ZAc, .TA = ILA) and compares:
  - latest OHLCV close from the DB
  - latest live_quote price from yfinance (post-pence-to-pounds scaling
    in live_quote_service)

If the ratio (db_close / live_price) is ~100, the DB is in pence and
live_quote is in pounds -- mismatch confirmed.

Read-only: never writes to the DB.

Outputs a Markdown report to
docs/superpowers/audits/2026-05-08-price-units-audit.md
relative to the project root.
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import desc, func, select

from app.core.db import SessionLocal
from app.models import OhlcvDaily, Stock, StockScore
from app.services import live_quote_service


SUFFIX_REGIONS = {
    ".L":  ("GBp / pounds", "UK / LSE"),
    ".JO": ("ZAc / ZAR",   "South Africa / JSE"),
    ".TA": ("ILA / ILS",   "Israel / TASE"),
}


def _classify_ratio(ratio: float | None) -> str:
    if ratio is None:
        return "n/a"
    if 0.5 < ratio < 1.5:
        return "consistent"
    if 50 < ratio < 200:
        return "DB in pence, live in pounds (BUG)"
    if 0.005 < ratio < 0.02:
        return "DB in pounds, live in pence (inverse -- unlikely)"
    return f"unusual ratio {ratio:.4f}"


def main() -> int:
    out_lines: list[str] = []
    out_lines.append("# Price-units Audit -- 2026-05-08\n")
    out_lines.append("**Goal:** confirm the IAG.L bug is the LSE pence/pounds mismatch and "
                     "scope which other tickers are affected.\n")
    out_lines.append("Read-only walk: latest OHLCV close vs latest live_quote price (post-scaling).\n")

    with SessionLocal() as db:
        total = db.execute(select(func.count(Stock.id))).scalar()
        out_lines.append(f"**Catalog size:** {total} stocks total.\n")

        for suffix, (currency_label, region) in SUFFIX_REGIONS.items():
            stocks = db.execute(
                select(Stock).where(Stock.ticker.like(f"%{suffix}"))
            ).scalars().all()
            if not stocks:
                out_lines.append(f"\n## {region} ({suffix})\n\nNo stocks in catalog.\n")
                continue

            out_lines.append(f"\n## {region} ({suffix}) -- currency `{currency_label}`\n")
            out_lines.append(f"Stocks in catalog: **{len(stocks)}**.\n")
            out_lines.append("| Ticker | DB close | Live price | Ratio | Verdict |")
            out_lines.append("|---|---:|---:|---:|---|")

            buggy = 0
            checked = 0
            for stock in stocks:
                latest_bar = db.execute(
                    select(OhlcvDaily.close).where(OhlcvDaily.stock_id == stock.id)
                    .order_by(desc(OhlcvDaily.date)).limit(1)
                ).scalar()
                if latest_bar is None:
                    out_lines.append(f"| {stock.ticker} | -- | -- | -- | no OHLCV yet |")
                    continue
                quote = live_quote_service.get_quote(stock.ticker)
                live_price = quote.price
                if live_price is None:
                    out_lines.append(f"| {stock.ticker} | {float(latest_bar):.2f} | -- | -- | live unavailable |")
                    continue
                # ohlcv_daily.close is Decimal in some envs -- coerce to float
                ratio = float(latest_bar) / live_price if live_price else None
                verdict = _classify_ratio(ratio)
                checked += 1
                if "BUG" in verdict:
                    buggy += 1
                out_lines.append(
                    f"| {stock.ticker} | {float(latest_bar):.2f} | {live_price:.2f} | "
                    f"{ratio:.2f} | {verdict} |"
                )

            out_lines.append(f"\n**Affected tickers in {region}: {buggy}/{checked} checked "
                             f"({len(stocks)} total in catalog)**\n")

        # Score staleness check: any .L stock with a stock_scores row will
        # have stale composite scores after Phase 3 (since SMA-based components
        # were computed on pence-scale OHLCV).
        score_count = db.execute(
            select(func.count(StockScore.stock_id))
            .join(Stock, Stock.id == StockScore.stock_id)
            .where(Stock.ticker.like("%.L"))
        ).scalar()
        out_lines.append(
            f"\n## Score staleness\n\n.L stocks with a stock_scores row: **{score_count}**. "
            f"These will have stale composite scores after the migration -- the next "
            f"scan_alerts run rebuilds them.\n"
        )

    repo_root = Path(__file__).resolve().parents[2]
    out_path = repo_root / "docs" / "superpowers" / "audits" / "2026-05-08-price-units-audit.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"Audit report written to: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
