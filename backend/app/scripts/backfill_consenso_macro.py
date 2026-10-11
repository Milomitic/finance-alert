"""Riempie l'archivio dei consensi coi rilasci PASSATI, da Nasdaq (2026-10-11).

Una richiesta per giorno feriale, con una pausa fra l'una e l'altra: tre anni
sono ~800 richieste e una decina di minuti. Idempotente: un giorno gia'
archiviato si completa e non si duplica. Si lancia nel pod:

    kubectl exec -i -n finance-alert finance-alert-finance-alert-0 -- \
        python -m app.scripts.backfill_consenso_macro --dal 2023-01-01

Alla fine dice quanti giorni la fonte NON ha servito: si rilanciano con lo
stesso comando, e i giorni gia' presenti costano una richiesta e nient'altro.
"""
from __future__ import annotations

import argparse
import time
from datetime import UTC, date, datetime, timedelta

from loguru import logger

from app.core.db import SessionLocal
from app.services import macro_consenso_service


def giorni_feriali(dal: date, al: date) -> list[date]:
    out, g = [], dal
    while g <= al:
        if g.weekday() < 5:
            out.append(g)
        g += timedelta(days=1)
    return out


def run(dal: date, al: date, *, pausa: float = 0.3, leggi=None, db=None) -> tuple[int, list[date]]:
    """Rende (rilasci scritti o completati, giorni mancanti)."""
    if db is None:
        with SessionLocal() as sessione:
            return run(dal, al, pausa=pausa, leggi=leggi, db=sessione)
    totale, mancanti = 0, []
    for i, g in enumerate(giorni_feriali(dal, al)):
        n, m = macro_consenso_service.archivia_nasdaq(db, [g], leggi=leggi)
        totale += n
        mancanti += m
        if i % 50 == 0:
            logger.info(f"[backfill consenso] {g}: {totale} rilasci finora, {len(mancanti)} giorni mancanti")
        if pausa:
            time.sleep(pausa)
    return totale, mancanti


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dal", type=date.fromisoformat, default=date(2023, 1, 1))
    ap.add_argument("--al", type=date.fromisoformat, default=datetime.now(UTC).date())
    ap.add_argument("--pausa", type=float, default=0.3)
    a = ap.parse_args()
    n, mancanti = run(a.dal, a.al, pausa=a.pausa)
    print(f"{n} rilasci scritti o completati; {len(mancanti)} giorni senza risposta: {mancanti[:20]}")


if __name__ == "__main__":
    main()
