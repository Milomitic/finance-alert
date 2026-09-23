"""Riempie le variabili dell'ingresso — `first_strength`, `first_factors`,
`first_provenance`, `first_contesto` — sugli alert che precedono i campi.

    # rapporto, senza scrivere (default)
    cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.backfill_variabili_emissione
    # e poi
    ... -m app.scripts.backfill_variabili_emissione --applica

Perche'
=======
Lo snapshot di un alert si sostituisce a ogni revisione, e quattro alert su
cinque ne hanno almeno una. La Forza del magazzino degli esiti coincideva con
quella dello snapshot ATTUALE nel 99,7% dei casi (misurato il 2026-09-23):
ogni variabile era misurata dopo il trade, e nessun modello si poteva
validare sugli esiti veri. Da qui in avanti lo scan le fissa alla creazione;
questo script fa la parte che si puo' fare all'indietro.

Due rami, e la differenza e' la parte importante
================================================
- **Alert mai rivisti**: lo snapshot corrente E' quello della prima emissione,
  quindi Forza, fattori e provenienza si copiano. Sono un fatto.
- **Alert rivisti**: Forza e fattori NON si ricavano. Sono l'uscita di un
  detector con le regole di allora, e ricalcolarli col codice di oggi darebbe
  numeri plausibili prodotti da un motore che allora non girava — la lezione
  SOXS di questo repo: un valore dedotto e applicato all'indietro sembra
  perfettamente sano ed e' silenziosamente sbagliato. Restano assenti, e il
  magazzino degli esiti ripiega sulla Forza corrente dichiarandolo
  (`signal_outcome_service._snapshot_fields`).

Il CONTESTO invece si calcola per tutti: e' la stessa funzione
(`contesto_emissione.contesto`) sulle stesse barre, sulla stessa finestra
dello scan (260 barre) che finisce alla barra della prima emissione — mai una
barra dopo. E' la stessa ragione per cui `backfill_plan_inputs` ricalcola
l'ATR: una funzione delle barre, non un fatto del detector.
"""
from __future__ import annotations

import argparse
import json
from datetime import date

import pandas as pd
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models import Alert, OhlcvDaily
from app.services.plan_outcome_service import _prima_emissione
from app.signals.contesto_emissione import contesto

#: La finestra che lo scan passa ai detector (`scan_service._load_ohlcv`). Fa
#: parte della definizione del contesto: con un'altra, gli stessi nomi
#: indicherebbero numeri diversi.
FINESTRA = 260


def _barre(db: Session, stock_id: int) -> pd.DataFrame:
    righe = db.execute(
        select(OhlcvDaily.date, OhlcvDaily.open, OhlcvDaily.high, OhlcvDaily.low,
               OhlcvDaily.close, OhlcvDaily.volume)
        .where(OhlcvDaily.stock_id == stock_id)
        .order_by(OhlcvDaily.date)
    ).all()
    df = pd.DataFrame(righe, columns=["date", "open", "high", "low", "close", "volume"])
    df["date"] = df["date"].astype(str).str.slice(0, 10)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _finestra(barre: pd.DataFrame, ancora: date) -> pd.DataFrame:
    """Le ultime `FINESTRA` barre non successive all'ancora: quello che lo scan
    aveva sotto gli occhi quando l'alert e' comparso, e niente di dopo."""
    fino = barre[barre["date"] <= ancora.isoformat()]
    return fino.iloc[-FINESTRA:].reset_index(drop=True)


def riempi(db: Session) -> dict[str, int]:
    """Rende il rapporto. Non fa commit: lo decide il chiamante."""
    copiati = contesti = rivisti_senza_forza = saltati = 0
    candidati = db.execute(select(Alert).order_by(Alert.stock_id, Alert.id)).scalars().all()
    barre_per_titolo: dict[int, pd.DataFrame] = {}
    for a in candidati:
        try:
            snap = json.loads(a.snapshot) if a.snapshot else {}
        except (ValueError, TypeError):
            saltati += 1
            continue
        if not isinstance(snap, dict):
            saltati += 1
            continue
        cambiato = False
        rivisto = bool(snap.get("amend_count"))

        if "first_strength" not in snap:
            forza = snap.get("strength")
            if rivisto:
                rivisti_senza_forza += 1
            elif isinstance(forza, (int, float)) and not isinstance(forza, bool):
                # Mai rivisto: lo snapshot corrente E' quello della nascita.
                snap["first_strength"] = forza
                snap["first_factors"] = dict(snap.get("factors") or {})
                if snap.get("provenance") is not None:
                    snap["first_provenance"] = snap["provenance"]
                copiati += 1
                cambiato = True

        if "first_contesto" not in snap:
            ancora = _prima_emissione(snap) or (
                a.triggered_at.date() if a.triggered_at else None)
            if ancora is not None:
                if a.stock_id not in barre_per_titolo:
                    # Una voce alla volta: le barre di mille titoli sarebbero
                    # mezzo giga, e i candidati sono ordinati per titolo.
                    barre_per_titolo.clear()
                    barre_per_titolo[a.stock_id] = _barre(db, a.stock_id)
                finestra = _finestra(barre_per_titolo[a.stock_id], ancora)
                if len(finestra) >= 2:
                    snap["first_contesto"] = contesto(finestra)
                    contesti += 1
                    cambiato = True

        if cambiato:
            a.snapshot = json.dumps(snap)
    return {
        "forza_fattori_copiati": copiati,
        "contesto_calcolato": contesti,
        # Dichiarati, non riempiti: vedi il docstring del modulo.
        "rivisti_senza_forza": rivisti_senza_forza,
        "saltati": saltati,
    }


def run(applica: bool = False) -> None:
    db = SessionLocal()
    try:
        rapporto = riempi(db)
        logger.info(f"variabili dell'ingresso: {rapporto}")
        if applica:
            db.commit()
            logger.info("scritti.")
        else:
            # Rollback esplicito: senza, le modifiche resterebbero in sessione e
            # il primo commit di qualcun altro le scriverebbe comunque.
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
