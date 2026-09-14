"""Find - and optionally remove - alert rows that are re-readings of one event.

WHY THIS EXISTS. Until 2026-09-14 `evaluate_signals` minted a new alert row on
every scan pass once an event's outcome had matured: the freeze-post-esito
guard dropped out of the WHOLE dedup block, so "don't amend" became "insert".
FA-051 closed the source; this clears the residue.

    668 excess rows across 9,034 alerts        7.4% of the warehouse
    596 of them identical to the cent          170 groups
    240 in July, 235 in August, 193 in September

The mechanism is visible in the dates: CPRX `candle_reversal` fired on
2026-07-09 and the first duplicate appeared on 2026-07-16 — five sessions
later, the day its 5-day outcome matured — then up to 8 rows in a single day,
because the rate tracked how often the scan ran, not the market. Only
`candle_reversal` and `gap_and_go` are affected: the only two detectors at a
5-day horizon, i.e. the only two that mature INSIDE their own recency window.

WHY IT DOES NOT JUST DELETE. Three tables point at `alerts`:

    signal_outcomes.alert_id        ON DELETE CASCADE   (and UNIQUE)
    positions.alert_id              ON DELETE SET NULL
    stock_setups.converted_alert_id ON DELETE SET NULL

CASCADE is loud. SET NULL is silent: a delete by resemblance would raise
nothing and leave positions with no signal provenance and setups "converted"
to nothing, `lead_days` included. So a group carrying either reference is
BLOCKED and printed, never resolved by this script.

The third blocker is subtler and is why the divergent outcomes were read one by
one instead of counted. Before the freeze guard existed, a cooldown refresh
could move an alert's `signal_date` forward AFTER its outcome had matured, so
the outcome describes a bar the alert no longer shows — 18 such rows, all
matured in June/July, none since August. In those groups the ORIGINAL carries
the stale measurement and an excess row carries the one matching the bar on
screen, so "keep the first, delete the rest" would keep the wrong number.

Read-only by default, like its neighbours.

    python -m app.scripts.repair_duplicate_alerts
    python -m app.scripts.repair_duplicate_alerts --apply
"""

from __future__ import annotations

import argparse

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models import Alert
from app.services.alert_service import find_duplicate_alert_groups


def main(argv: list[str] | None = None, db: Session | None = None) -> None:
    """`argv` and `db` are injectable so a test can actually RUN this.

    ⚠️ Not a convenience. The dead-code gate caught this script's `main` as a
    function no test ever executed, which is the exact "codice corretto contro
    codice che ha girato" gap this repo built eight presidi to close — and it
    matters more here than usual, because `--apply` deletes production rows.
    A repair path nobody has run is not a repair path.
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="delete the excess rows (outcomes follow by CASCADE)")
    ap.add_argument("--limit-print", type=int, default=15,
                    help="how many groups to list (default 15)")
    args = ap.parse_args(argv)

    nostra = db is None
    db = SessionLocal() if nostra else db
    try:
        groups = find_duplicate_alert_groups(db)
        if not groups:
            print("Nessun gruppo duplicato: il magazzino e' pulito.")
            return

        liberi = [g for g in groups if not g.blockers]
        bloccati = [g for g in groups if g.blockers]
        eccedenti = sum(len(g.excess_ids) for g in liberi)
        totale_alert = db.execute(select(Alert.id)).scalars().all()

        print(f"gruppi duplicati:        {len(groups)}")
        print(f"  bonificabili:          {len(liberi)}  ({eccedenti} righe eccedenti)")
        print(f"  bloccati:              {len(bloccati)}")
        print(f"alert totali:            {len(totale_alert)}")
        print()
        print(f"{'titolo':<10} {'detector':<18} {'barra':<12} {'tono':<6} "
              f"{'ecc.':>5}  blocchi")
        for g in groups[:args.limit_print]:
            print(f"{g.ticker:<10} {g.detector:<18} {str(g.signal_date):<12} "
                  f"{str(g.tone):<6} {len(g.excess_ids):>5}  "
                  f"{', '.join(g.blockers) or '-'}")
        if len(groups) > args.limit_print:
            print(f"... e altri {len(groups) - args.limit_print} gruppi")

        if bloccati:
            print()
            print("⚠️ I gruppi BLOCCATI non vengono toccati nemmeno con --apply.")
            print("   Portano un riferimento che una cancellazione azzererebbe in")
            print("   silenzio, o un esito che descrive una barra diversa da quella")
            print("   che l'alert mostra oggi. Vanno decisi da una persona.")

        if not args.apply:
            print()
            print("Sola lettura. Aggiungere --apply per cancellare le righe eccedenti")
            print("dei gruppi bonificabili (gli esiti seguono per CASCADE).")
            return

        ids = [i for g in liberi for i in g.excess_ids]
        if not ids:
            print("\nNiente da cancellare: ogni gruppo e' bloccato.")
            return
        res = db.execute(delete(Alert).where(Alert.id.in_(ids)))
        db.commit()
        logger.info(f"[dedup] cancellate {res.rowcount} righe eccedenti")
        print(f"\nCancellate {res.rowcount} righe eccedenti su {len(liberi)} gruppi.")
    finally:
        if nostra:
            db.close()


if __name__ == "__main__":
    main()
