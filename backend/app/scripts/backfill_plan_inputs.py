"""Riempie gli ingressi del piano — `first_atr`, `first_invalidation`,
`first_horizon` — sugli alert che precedono i campi.

    # rapporto, senza scrivere (default)
    cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.backfill_plan_inputs
    # e poi
    ... -m app.scripts.backfill_plan_inputs --applica

Perche'
=======
Il PREZZO d'ingresso era gia' fissato alla prima emissione
(`backfill_first_price`), gli altri ingressi della geometria no: `atr`,
`invalidation` e `horizon` vengono sostituiti a OGNI revisione insieme al
resto dello snapshot, e quattro alert su cinque ne hanno almeno una. Il piano
leggeva quindi un prezzo di un giorno e una volatilita' di un altro.

Misurato in produzione il 2026-09-22 su MRNA (alert 18192, rottura di
struttura del 12 agosto a 63,67): il 19 agosto il titolo ha fatto +177% in una
seduta, l'alert e' rimasto vivo fino al 21, e l'ATR e' passato da 3,96 a
14,89. Lo stop del piano finiva a 26,46 — il 58% sotto un ingresso che nessuno
avrebbe piu' potuto prendere — e i due target collassavano entrambi sul tetto
del +95%. Con l'ATR del 12 agosto: stop 53,76, target 83,48 e 93,39, entrambi
toccati dal gap del 19. Su 7.296 alert rivisti, 296 hanno uno scarto di ATR
oltre il 25% e 37 oltre il doppio.

Due rami
========
- **Alert mai rivisti**: lo snapshot corrente E' quello della prima emissione,
  quindi i tre valori si copiano.
- **Alert rivisti**: l'ATR si ricalcola dalle barre — ATR(14) di Wilder sulla
  barra d'ingresso, la stessa funzione che lo scan usa.

  ⚠️ Invalidazione e orizzonte non si ricavano dalle barre. Il livello e' un
  fatto del detector, e l'orizzonte si calcola dalla catena ORIGINALE, che la
  revisione ha sovrascritto: dedurli e riapplicarli all'indietro darebbe
  numeri plausibili e in parte inventati — la lezione SOXS di questo repo.
  Restano assenti, e il piano ripiega sui correnti
  (`trade_plan.ingressi_del_piano`).

⚠️ Quanto vale il ricalcolo, misurato dallo script stesso
==========================================================
Il rapporto stampa il controllo sugli alert MAI rivisti, dove la verita' si
conosce: si ricalcola l'ATR e lo si confronta con quello conservato. Lo scarto
tipico e' di pochi punti percentuali e viene dalle scansioni girate prima
della chiusura, che vedevano una barra ancora in formazione — due ordini di
grandezza sotto il difetto che questo script chiude.
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
from app.indicators.atr import atr
from app.models import Alert, OhlcvDaily

CHIAVE = "first_atr"


def _ancora(snap: dict, alert: Alert) -> date | None:
    """La data della prima emissione, col ripiego su `triggered_at` per gli
    alert che precedono anche quel campo."""
    grezzo = snap.get("first_emitted_at")
    if isinstance(grezzo, str) and len(grezzo) >= 10:
        try:
            return date.fromisoformat(grezzo[:10])
        except ValueError:
            pass
    return alert.triggered_at.date() if alert.triggered_at else None


def _atr_per_titolo(db: Session, stock_id: int) -> list[tuple[str, float]]:
    """(data, ATR(14)) per ogni barra del titolo, nell'ordine."""
    righe = db.execute(
        select(OhlcvDaily.date, OhlcvDaily.high, OhlcvDaily.low, OhlcvDaily.close)
        .where(OhlcvDaily.stock_id == stock_id)
        .order_by(OhlcvDaily.date)
    ).all()
    if not righe:
        return []
    df = pd.DataFrame(righe, columns=["date", "high", "low", "close"])
    df[["high", "low", "close"]] = df[["high", "low", "close"]].astype(float)
    serie = atr(df, 14)
    return [(str(d)[:10], float(v)) for d, v in zip(df["date"], serie, strict=True)
            if v == v]


def _alla_barra(valori: list[tuple[str, float]], limite: date) -> float | None:
    """L'ultimo valore non successivo alla data: la barra che l'alert aveva
    sotto gli occhi quando e' comparso."""
    trovato = None
    iso = limite.isoformat()
    for giorno, v in valori:
        if giorno > iso:
            break
        trovato = v
    return trovato


def riempi(db: Session) -> dict[str, object]:
    """Rende il rapporto. Non fa commit: lo decide il chiamante."""
    esatti = ricalcolati = saltati = 0
    scarti: list[float] = []
    candidati = db.execute(select(Alert).order_by(Alert.stock_id, Alert.id)).scalars().all()
    cache: dict[int, list[tuple[str, float]]] = {}
    for a in candidati:
        try:
            snap = json.loads(a.snapshot) if a.snapshot else {}
        except (ValueError, TypeError):
            saltati += 1
            continue
        if not isinstance(snap, dict) or CHIAVE in snap:
            continue
        rivisto = bool(snap.get("amend_count"))
        atr_corrente = snap.get("atr")
        atr_corrente = (float(atr_corrente)
                        if isinstance(atr_corrente, (int, float))
                        and not isinstance(atr_corrente, bool) and atr_corrente > 0
                        else None)
        if not rivisto:
            # Lo snapshot corrente E' quello della prima emissione.
            if atr_corrente is None:
                saltati += 1
                continue
            snap[CHIAVE] = atr_corrente
            if snap.get("invalidation") is not None:
                snap["first_invalidation"] = snap["invalidation"]
            if snap.get("horizon") is not None:
                snap["first_horizon"] = snap["horizon"]
            a.snapshot = json.dumps(snap)
            esatti += 1
            continue

        ancora = _ancora(snap, a)
        if ancora is None:
            saltati += 1
            continue
        if a.stock_id not in cache:
            # Una voce alla volta: le barre di mille titoli sarebbero mezzo giga.
            cache.clear()
            cache[a.stock_id] = _atr_per_titolo(db, a.stock_id)
        valore = _alla_barra(cache[a.stock_id], ancora)
        if valore is None or valore <= 0:
            saltati += 1
            continue
        snap[CHIAVE] = valore
        a.snapshot = json.dumps(snap)
        ricalcolati += 1

    # Il controllo: sugli alert mai rivisti la verita' si conosce, quindi il
    # ricalcolo si puo' MISURARE invece di dichiararlo buono.
    for a in candidati:
        try:
            snap = json.loads(a.snapshot) if a.snapshot else {}
        except (ValueError, TypeError):
            continue
        if not isinstance(snap, dict) or snap.get("amend_count"):
            continue
        vero = snap.get("atr")
        if not isinstance(vero, (int, float)) or isinstance(vero, bool) or vero <= 0:
            continue
        ancora = _ancora(snap, a)
        if ancora is None:
            continue
        if a.stock_id not in cache:
            cache.clear()
            cache[a.stock_id] = _atr_per_titolo(db, a.stock_id)
        stimato = _alla_barra(cache[a.stock_id], ancora)
        if stimato:
            scarti.append(abs(stimato / float(vero) - 1.0))

    scarti.sort()
    mediana = scarti[len(scarti) // 2] if scarti else None
    return {
        "copiati_esatti": esatti,
        "atr_ricalcolato": ricalcolati,
        "saltati": saltati,
        "controllo_n": len(scarti),
        "controllo_scarto_mediano_pct": round(mediana * 100, 2) if mediana is not None else None,
        "controllo_oltre_il_5pct": sum(1 for s in scarti if s > 0.05),
    }


def run(applica: bool = False) -> None:
    db = SessionLocal()
    try:
        rapporto = riempi(db)
        logger.info(f"ingressi del piano: {rapporto}")
        if applica:
            db.commit()
            logger.info("scritti.")
        else:
            # Rollback esplicito: senza, le modifiche resterebbero in sessione e
            # il primo commit di qualcun altro le scriverebbe comunque, mentre
            # chi ha letto il rapporto crede di non aver toccato niente.
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
