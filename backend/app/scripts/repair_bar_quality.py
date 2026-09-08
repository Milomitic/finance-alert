"""Find - and optionally repair - bars that were never traded.

`repair_price_basis` next door answers "did the price basis change". This
answers the prior question it cannot: **was there a market here at all**. A
zero-volume bar means no trade happened, so whatever sits in `close` was
carried over from the last session that had one. It is a number, not a price
anyone paid, and every indicator downstream treats it as if it were.

WHY THIS EXISTS: INDV, and the repair it did NOT need. It carried two opposing
basis breaks three sessions apart (x0.159 on 2022-11-23, x6.719 on 2022-11-28)
and CLAUDE.md filed it as "a handful of corrupt bars wanting a bar-level repair
that does not exist yet". Building that repair meant first measuring how many
bars were corrupt. Against production:

    2016-2023   1,911 bars   36-89% with o==h==l==c   14-52% at zero volume
    2024-2026     672 bars              0%                       0%

Indivior moved its primary listing to Nasdaq in 2024. Everything before is a
thin secondary line, and the November 2022 pair is its most visible artifact
rather than the defect itself. The bar-level repair was the wrong instrument:
dropping those three days would have left 1,908 bars of the same provenance
and called the ticker fixed.

So this script offers BOTH repairs and refuses to choose blindly:

    --drop-untraded      delete the zero-volume bars themselves. Right when the
                         damage is scattered through an otherwise real series.
    --truncate-to-clean  delete everything before the trailing clean run. Right
                         when the damage is a PREFIX from a different regime.

The recommendation is printed with its reason, and bar COUNT is deliberately
not the objective. Dropping INDV's untraded bars costs 562 and truncating costs
1,911 - so the cheaper option loses nearly four times fewer bars and still
leaves 1,349 of them 39% flat. What matters is whether what remains is a
coherent record, not how much of it there is.

Read-only by default, like its neighbour.
"""

from __future__ import annotations

import argparse

from loguru import logger
from sqlalchemy import text

from app.core.db import SessionLocal
from app.models import OhlcvDaily, Stock
from app.services.ohlcv_service import BarQuality, as_date, assess_bar_quality

# A liquid name sits under 2% flat bars. Above this the stretch is not a thin
# market, it is a different data regime.
_PREFIX_FLAT_ALARM = 0.25
_TAIL_FLAT_OK = 0.05
# Under 200 bars `has_full_data` already keeps a ticker out of EMA200 signals
# and breadth, so truncating below that does not repair - it relocates.
_MIN_KEEPABLE = 200


def _flat_rate(rows, lo: int, hi: int) -> float:
    span = rows[lo:hi]
    if not span:
        return 0.0
    flat = sum(1 for r in span if r[1] is not None and r[1] == r[2] == r[3] == r[4])
    return flat / len(span)


def recommend(q: BarQuality, pre_flat: float, tail_flat: float) -> str:
    """What to do, and why - never a bare verdict.

    The two costs are printed beside it because on INDV they point opposite
    ways, which is exactly when a one-line answer would mislead.
    """
    if q.untraded == 0:
        return "niente da fare"
    if q.clean_bars < _MIN_KEEPABLE:
        return (
            f"coda pulita di sole {q.clean_bars} barre (<{_MIN_KEEPABLE}): "
            "troncare non riparerebbe -> --drop-untraded"
        )
    if pre_flat > _PREFIX_FLAT_ALARM and tail_flat < _TAIL_FLAT_OK:
        return (
            f"il prefisso e' {pre_flat:.0%} piatto contro {tail_flat:.0%} nella coda: "
            "altro regime di dati -> --truncate-to-clean"
        )
    return "danno sparso in una serie per il resto reale -> --drop-untraded"


def _as_float(x) -> float | None:
    return float(x) if x is not None else None


def scan(db, only: set[str] | None = None) -> list[tuple[Stock, BarQuality, float, float]]:
    out: list[tuple[Stock, BarQuality, float, float]] = []
    rows_q = text("SELECT id, ticker FROM stocks ORDER BY ticker")
    for sid, ticker in db.execute(rows_q).all():
        if only and ticker not in only:
            continue
        rows = db.execute(
            text(
                "SELECT date, open, high, low, close, volume FROM ohlcv_daily "
                "WHERE stock_id = :sid ORDER BY date"
            ),
            {"sid": sid},
        ).all()
        if len(rows) < 30:
            continue
        dates = [as_date(r[0]) for r in rows]
        q = assess_bar_quality(
            dates,
            [_as_float(r[1]) for r in rows],
            [_as_float(r[2]) for r in rows],
            [_as_float(r[3]) for r in rows],
            [_as_float(r[4]) for r in rows],
            [_as_float(r[5]) for r in rows],
        )
        if q.untraded == 0:
            continue
        cut = dates.index(q.clean_from) if q.clean_from else len(rows)
        out.append(
            (db.get(Stock, sid), q, _flat_rate(rows, 0, cut), _flat_rate(rows, cut, len(rows)))
        )
    return out


def _report_left(db, stock: Stock) -> tuple[int, str]:
    left = db.query(OhlcvDaily).filter(OhlcvDaily.stock_id == stock.id).count()
    flag = f"  <- sotto {_MIN_KEEPABLE}: fuori dai segnali EMA200" if left < _MIN_KEEPABLE else ""
    return left, flag


def _drop_untraded(db, found) -> None:
    print(f"\ncancellazione delle barre a volume zero su {len(found)} titoli...")
    for stock, _q, _pre, _tail in found:
        try:
            n = (
                db.query(OhlcvDaily)
                .filter(
                    OhlcvDaily.stock_id == stock.id,
                    (OhlcvDaily.volume.is_(None)) | (OhlcvDaily.volume == 0),
                )
                .delete(synchronize_session=False)
            )
            db.commit()
            left, flag = _report_left(db, stock)
            print(f"  ok  {stock.ticker:<10} -{n} barre, restano {left}{flag}")
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("drop-untraded failed for {}", stock.ticker)
            print(f"  FALLITO {stock.ticker:<10} {str(exc)[:70]}")
    print("\nRicalcola i punteggi tecnici: i vecchi sono usciti dalle barre finte.")


def _truncate_to_clean(db, found) -> None:
    print(f"\ntroncamento di {len(found)} titoli all'inizio della coda pulita...")
    for stock, q, _pre, _tail in found:
        if q.clean_from is None:
            print(f"  salto {stock.ticker:<10} nessuna coda pulita: l'ultima barra non e' scambiata")
            continue
        try:
            n = (
                db.query(OhlcvDaily)
                .filter(OhlcvDaily.stock_id == stock.id, OhlcvDaily.date < q.clean_from)
                .delete(synchronize_session=False)
            )
            db.commit()
            left, flag = _report_left(db, stock)
            print(f"  ok  {stock.ticker:<10} -{n} barre prima del {q.clean_from}, restano {left}{flag}")
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("truncate-to-clean failed for {}", stock.ticker)
            print(f"  FALLITO {stock.ticker:<10} {str(exc)[:70]}")
    print("\nRicalcola i punteggi tecnici: i vecchi sono usciti dalle barre finte.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ticker", action="append", help="limit to these tickers")
    ap.add_argument("--drop-untraded", action="store_true", help="delete the zero-volume bars")
    ap.add_argument(
        "--truncate-to-clean", action="store_true", help="delete everything before the clean tail"
    )
    args = ap.parse_args()

    if args.drop_untraded and args.truncate_to_clean:
        raise SystemExit("scegline una: --drop-untraded oppure --truncate-to-clean")

    db = SessionLocal()
    try:
        found = scan(db, set(args.ticker) if args.ticker else None)
        if not found:
            print("nessuna barra non scambiata trovata.")
            return

        print(f"{len(found)} titoli con barre mai scambiate:\n")
        for stock, q, pre, tail in found:
            print(
                f"{stock.ticker:<10}{q.total:>6} barre   "
                f"non scambiate {q.untraded} ({q.untraded / q.total:.1%})   "
                f"piatte {q.flat} ({q.flat / q.total:.1%})"
            )
            if q.clean_from:
                print(
                    f"{'':<10}coda pulita dal {q.clean_from}: {q.clean_bars} barre   "
                    f"(prima: {pre:.0%} piatte | coda: {tail:.0%} piatte)"
                )
            print(
                f"{'':<10}troncare costa {q.total - q.clean_bars} barre, "
                f"scartare le non scambiate ne costa {q.untraded}"
            )
            print(f"{'':<10}-> {recommend(q, pre, tail)}\n")

        if args.drop_untraded:
            _drop_untraded(db, found)
        elif args.truncate_to_clean:
            _truncate_to_clean(db, found)
        else:
            print("sola lettura.")
            print("  --drop-untraded      elimina le singole barre a volume zero")
            print("  --truncate-to-clean  elimina tutto prima della coda pulita")
    finally:
        db.close()


if __name__ == "__main__":
    main()
