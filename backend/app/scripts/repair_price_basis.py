"""Find — and optionally repair — unrepaired splits in the stored OHLCV.

WHY THIS EXISTS
---------------
`ohlcv_service._check_price_basis` compares the incoming overlap bar against
the stored one, so it only ever sees a discontinuity at the EDGE of a fetch
window. A break already inside the stored history is invisible to it by
construction: from the next day on, stored and incoming are both on the new
basis, the ratio is 1.0, and it reports "basis OK" forever. It was added on
2026-07-04, so every split spliced before that date was never repaired and
never would be.

Measured on the live catalogue on 2026-09-01, the damage was not cosmetic:

    TIT.MI  reverse 1:10, 15 May   ->  rel_strength 100.0, the HIGHEST in the
                                       entire universe, posture "Forte"
    KLAC    10:1, 18 May           ->  rel_strength 0.1, trend 0.9
    CRWD     4:1, 29 June          ->  rel_strength 0.3, trend 0.0
    SOXS    20:1, 26 May           ->  rel_strength 0.0
    8053.T   4:1,  1 June

Three real companies sat at the bottom of the technical ranking and one
artifact sat at the very top. It contaminates breadth, ATR, the 52-week range,
the Tecnico lens, and every detector whose lookback crosses the date.

USAGE
-----
    # report only, safe, read-only
    cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.repair_price_basis

    # repair: wipes and re-downloads 10y for each affected stock
    ... -m app.scripts.repair_price_basis --apply
    ... -m app.scripts.repair_price_basis --apply --ticker KLAC --ticker CRWD

STOP UVICORN FIRST on SQLite (single writer). `--apply` is destructive per
stock: `_rebase_full_history` deletes the whole series and re-downloads it on
the authoritative basis. That is safe by construction — a failed refetch
raises and the per-stock transaction rolls back, so it never destroys what it
cannot replace — but it is a decision, which is why it is not automatic and
never runs inside a scan.

The detector reports CANDIDATES, not certainties: it is calibrated to catch
3:1 and larger (see `_SPLIT_MIN_RATIO`), and a couple of the older hits are
data glitches rather than splits — INDV falls 6x and recovers 7x five days
later, which is not a corporate action. Read the table before passing
--apply, and use --ticker when in doubt.
"""
from __future__ import annotations

import argparse

from loguru import logger
from sqlalchemy import text

from app.core.db import SessionLocal
from app.models import Stock
from app.services.ohlcv_service import _rebase_full_history, find_basis_breaks


def scan(db, only: set[str] | None = None) -> list[tuple[Stock, list]]:
    q = "SELECT id, ticker FROM stocks ORDER BY ticker"
    out: list[tuple[Stock, list]] = []
    for sid, ticker in db.execute(text(q)).all():
        if only and ticker not in only:
            continue
        rows = db.execute(
            text(
                "SELECT date, close, volume FROM ohlcv_daily "
                "WHERE stock_id = :sid ORDER BY date"
            ),
            {"sid": sid},
        ).all()
        if len(rows) < 30:
            continue
        breaks = find_basis_breaks(
            [r[0] for r in rows],
            [float(r[1]) if r[1] is not None else None for r in rows],
            [float(r[2]) if r[2] is not None else None for r in rows],
        )
        if breaks:
            out.append((db.get(Stock, sid), breaks))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="repair (destructive refetch)")
    ap.add_argument("--ticker", action="append", help="limit to these tickers")
    args = ap.parse_args()

    only = set(args.ticker) if args.ticker else None
    db = SessionLocal()
    try:
        found = scan(db, only)
        if not found:
            print("nessuna discontinuita' di base trovata.")
            return

        print(f"{len(found)} titoli con una discontinuita' sospetta:\n")
        print(f"{'ticker':<10}{'data':<12}{'prezzo':>10}{'volume':>10}{'~split':>9}")
        for stock, breaks in found:
            for b in breaks:
                vr = f"x{b.volume_ratio:.2f}" if b.volume_ratio else "n/d"
                print(
                    f"{stock.ticker:<10}{str(b.date):<12}"
                    f"{'x' + format(b.price_ratio, '.3f'):>10}{vr:>10}"
                    f"{format(b.matched_ratio, '.0f') + ':1':>9}"
                )

        if not args.apply:
            print("\nsola lettura. Ripassa con --apply per riparare.")
            return

        print(f"\nriparazione di {len(found)} titoli (wipe + refetch 10y)...")
        ok = failed = 0
        for stock, _ in found:
            try:
                rows = _rebase_full_history(db, stock)
                db.commit()
                ok += 1
                print(f"  ok      {stock.ticker:<10} {rows} barre riscaricate")
            except Exception as exc:  # noqa: BLE001 - one bad ticker must not stop the rest
                db.rollback()
                failed += 1
                logger.warning(f"[repair] {stock.ticker} non riparato: {exc}")
                print(f"  FALLITO {stock.ticker:<10} {str(exc)[:70]}")
        print(f"\nriparati {ok}, falliti {failed}.")
        if ok:
            print("Ricalcola i punteggi tecnici: i vecchi restano sulla base sbagliata.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
