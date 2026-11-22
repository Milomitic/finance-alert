"""Ricalcola le variazioni trimestrali dei 13F SEC, ora corrette per gli split.

    python -m app.scripts.ricalcola_qoq_13f            # solo il rapporto
    python -m app.scripts.ricalcola_qoq_13f --applica  # riscrive

Uno split fra due dichiarazioni si leggeva come un acquisto: CRWD (4:1,
giugno 2026) risultava +322% per BlackRock e «aumento» per ogni grande fondo.
`compute_qoq_deltas` ora riporta le quote di prima sulla base di dopo; questo
script lo riapplica alle dichiarazioni gia' in archivio, in ordine
cronologico, dopo aver tolto le righe «uscita» che il calcolo stesso aveva
aggiunto (altrimenti rifarlo le leggerebbe come posizioni).

Tocca solo campi DERIVATI (variazione, azione, righe d'uscita): le quote e i
valori dichiarati non cambiano.
"""
from __future__ import annotations

import argparse
from collections import Counter

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Institutional, InstitutionalFiling, InstitutionalHolding
from app.services import institutional_service as svc


def _stato(db: Session, filing_id: int) -> dict[str, tuple[str | None, float | None]]:
    return {
        t: (a, q)
        for t, a, q in db.execute(
            select(InstitutionalHolding.ticker, InstitutionalHolding.action, InstitutionalHolding.qoq_change_pct)
            .where(InstitutionalHolding.filing_id == filing_id, InstitutionalHolding.shares > 0)
        ).all()
    }


def ricalcola(db: Session, *, applica: bool) -> Counter:
    """Rende quante righe cambiano, per (azione prima -> azione dopo)."""
    cambi: Counter = Counter()
    fondi = db.execute(select(Institutional).where(Institutional.source == "sec_13f")).scalars().all()
    for fondo in fondi:
        depositi = db.execute(
            select(InstitutionalFiling)
            .where(InstitutionalFiling.institutional_id == fondo.id)
            .order_by(InstitutionalFiling.period_end_date)
        ).scalars().all()
        for dep in depositi[1:]:
            prima = _stato(db, dep.id)
            db.execute(delete(InstitutionalHolding).where(
                InstitutionalHolding.filing_id == dep.id,
                InstitutionalHolding.action == "sold_out",
                InstitutionalHolding.shares == 0,
            ))
            svc.compute_qoq_deltas(db, fondo, dep)
            for t, (a, q) in _stato(db, dep.id).items():
                pa, pq = prima.get(t, (None, None))
                if pa != a or (pq is None) != (q is None) or (q is not None and abs(q - pq) > 0.01):
                    cambi[(pa, a)] += 1
    if applica:
        db.commit()
    else:
        db.rollback()
    return cambi


def main() -> None:
    from app.core.db import SessionLocal  # noqa: PLC0415

    ap = argparse.ArgumentParser()
    ap.add_argument("--applica", action="store_true")
    args = ap.parse_args()
    with SessionLocal() as db:
        cambi = ricalcola(db, applica=args.applica)
    for (a, b), n in cambi.most_common():
        print(f"{a} -> {b}: {n}")
    print("applicato" if args.applica else "solo rapporto: --applica per scrivere")


if __name__ == "__main__":
    main()
