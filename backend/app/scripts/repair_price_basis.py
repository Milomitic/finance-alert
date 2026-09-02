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
from app.models import OhlcvDaily, Stock
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


def _truncate(db, found) -> None:
    """Delete every bar strictly before the break, keeping the newer basis.

    WHEN TO USE THIS INSTEAD OF --apply. `--apply` wipes and re-downloads, so it
    only helps when the SOURCE is right and our stored copy drifted. If a fresh
    download reproduces the same break, refetching destroys the series and
    rebuilds it identically broken - strictly worse than doing nothing.

    Why not rescale the old bars by the ratio? Because the ratio would be OURS,
    not the source's. SOXS (established 2026-09-02) is the case this exists for:

      - exactly one discontinuity, 2026-05-26: price x0.054, volume x21.4;
      - yfinance DECLARES splits on 2026-03-05 (1:20) and 2026-07-15 (1:10),
        and both are correctly adjusted - no discontinuity on either date;
      - so the May break matches NO declared corporate action, and the "20:1"
        the detector prints is a pattern match, not a fact;
      - a fresh 10y download reproduces it to the cent, so --apply cannot help.

    Dividing ten years of prices by an inferred 20 would look perfectly healthy
    and be silently wrong if the true ratio were 18 or 25. Truncating invents
    nothing: what remains sits on ONE consistent basis, and a ticker left under
    200 bars simply fails `has_full_data`, which already keeps it out of
    EMA200-dependent signals and out of breadth (CLAUDE.md). It self-heals as
    real bars accrue.

    The cost is explicit and one-way: the pre-break history for that ticker is
    gone. Prefer --apply whenever a fresh download IS clean.
    """
    print()
    print(f"troncamento di {len(found)} titoli (elimina le barre PRIMA della rottura)...")
    for stock, breaks in found:
        cut = min(b.date for b in breaks)
        try:
            n = db.query(OhlcvDaily).filter(
                OhlcvDaily.stock_id == stock.id, OhlcvDaily.date < cut,
            ).delete(synchronize_session=False)
            left = db.query(OhlcvDaily).filter(
                OhlcvDaily.stock_id == stock.id,
            ).count()
            db.commit()
            flag = "  <- sotto 200: fuori dai segnali EMA200" if left < 200 else ""
            print(f"  ok  {stock.ticker:<10} -{n} barre prima del {cut}, restano {left}{flag}")
        except Exception as exc:  # noqa: BLE001 - one bad ticker must not stop the rest
            db.rollback()
            logger.warning(f"[repair] {stock.ticker} non troncato: {exc}")
            print(f"  FALLITO {stock.ticker:<10} {str(exc)[:70]}")
    print()
    print("Ricalcola i punteggi tecnici: i vecchi restano sulla base sbagliata.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="repair (destructive refetch)")
    ap.add_argument(
        "--truncate", action="store_true",
        help="drop every bar BEFORE the break instead of refetching - for a "
             "break the source itself reproduces (see SOXS in _truncate)",
    )
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

        if args.truncate:
            _truncate(db, found)
            return

        if not args.apply:
            print()
            print("sola lettura.")
            print("  --apply    riscarica da capo - SOLO se un download fresco e' pulito")
            print("  --truncate elimina le barre prima della rottura - quando non lo e'")
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
