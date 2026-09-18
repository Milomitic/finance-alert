"""Riempie `snapshot.first_price` sugli alert che precedono il campo.

    # rapporto, senza scrivere (default)
    cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.backfill_first_price
    # e poi
    ... -m app.scripts.backfill_first_price --applica

Perche'
=======
Un alert e' una riga VIVA: finche' il segnale persiste, ogni scansione lo
rivede e riscrive `trigger_price` con la chiusura corrente. Misurato in
produzione il 2026-09-18 su 8.736 alert: 80% ne ha almeno una revisione, uno
ne conta 103, e nel 18% dei casi il prezzo mostrato dista oltre il 2% dalla
chiusura della barra del segnale. Su FICO il box «prezzo trigger» diceva
985,39 — la chiusura dell'11 settembre — accanto a una data segnale del 4,
mentre la chiusura vera del 4 era 932,26.

`first_emitted_at` conservava gia' l'ISTANTE della prima emissione. Il PREZZO
di quel momento non era conservato da nessuna parte: una volta sovrascritto,
dall'alert non si recuperava piu'. Da adesso il motore lo fissa alla
creazione; questo script lo ricostruisce all'indietro per gli alert esistenti.

⚠️ E' una RICOSTRUZIONE, non un recupero, ed e' marcata
=======================================================
Il valore e' la chiusura dell'ultima barra non successiva alla prima
emissione. Combacia con quello che l'alert mostrava, TRANNE quando la
scansione girava prima della chiusura di quel giorno: li' l'alert mostrava la
chiusura del giorno precedente, e questa ricostruzione prende quella del
giorno stesso. Uno scarto di una barra, e non determinabile dall'alert.

Per questo ogni valore ricostruito porta `first_price_ricostruito: true` e
resta escludibile con un controllo per sempre. Una ricostruzione sbagliata e'
indistinguibile da una giusta finche' nessuno guarda il campo — la stessa
ragione per cui esiste `plan_outcomes.source`.

⚠️ NON si tocca `trigger_price`. Quello descrive il segnale VIVO ed e' giusto
che avanzi: sono due numeri diversi che fino a oggi erano lo stesso campo.
"""
from __future__ import annotations

import argparse
import json
from datetime import date

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models import Alert, OhlcvDaily

CHIAVE = "first_price"
MARCATORE = "first_price_ricostruito"


def _ancora(snap: dict, alert: Alert) -> date | None:
    grezzo = snap.get("first_emitted_at")
    if isinstance(grezzo, str) and len(grezzo) >= 10:
        try:
            return date.fromisoformat(grezzo[:10])
        except ValueError:
            pass
    # Ripiego dichiarato per i 116 alert (1,3%) che precedono anche quel campo.
    return alert.triggered_at.date() if alert.triggered_at else None


def riempi(db: Session) -> tuple[int, int]:
    """Rende (riempiti, saltati). Non fa commit: lo decide il chiamante."""
    riempiti = saltati = 0
    # Ordinati per titolo: la cache delle chiusure ne tiene uno alla volta.
    candidati = db.execute(select(Alert).order_by(Alert.stock_id, Alert.id)).scalars().all()
    chiusure: dict[int, list[tuple[str, float]]] = {}
    for a in candidati:
        try:
            snap = json.loads(a.snapshot) if a.snapshot else {}
        except (ValueError, TypeError):
            saltati += 1
            continue
        if not isinstance(snap, dict) or CHIAVE in snap:
            continue
        ancora = _ancora(snap, a)
        if ancora is None:
            saltati += 1
            continue
        if a.stock_id not in chiusure:
            chiusure.clear()
            chiusure[a.stock_id] = [
                (str(d)[:10], float(c)) for d, c in db.execute(
                    select(OhlcvDaily.date, OhlcvDaily.close)
                    .where(OhlcvDaily.stock_id == a.stock_id)
                    .order_by(OhlcvDaily.date)
                )
            ]
        prezzo = None
        limite = ancora.isoformat()
        for giorno, chiusura in chiusure[a.stock_id]:
            if giorno > limite:
                break
            prezzo = chiusura
        if prezzo is None or prezzo <= 0:
            saltati += 1
            continue
        snap[CHIAVE] = prezzo
        snap[MARCATORE] = True
        a.snapshot = json.dumps(snap)
        riempiti += 1
    return riempiti, saltati


def run(applica: bool = False) -> None:
    db = SessionLocal()
    try:
        riempiti, saltati = riempi(db)
        logger.info(f"da riempire: {riempiti}   senza una barra utile: {saltati}")
        if applica:
            db.commit()
            logger.info("scritti.")
        else:
            # Rollback esplicito: senza, le modifiche resterebbero in sessione
            # e il primo commit di qualcun altro le scriverebbe comunque,
            # mentre chi ha letto il rapporto crede di non aver toccato niente.
            db.rollback()
            logger.info("sola lettura: niente e' stato scritto. Usa --applica.")
    finally:
        db.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--applica", action="store_true",
                    help="scrive davvero (default: solo rapporto)")
    run(applica=ap.parse_args().applica)


if __name__ == "__main__":
    main()
