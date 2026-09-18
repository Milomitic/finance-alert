"""Ricalcolo storico del magazzino degli esiti di piano.

    # rapporto, senza scrivere niente (default)
    cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.backfill_plan_outcomes

    # e poi, per scrivere davvero
    ... -m app.scripts.backfill_plan_outcomes --applica

    # includendo la ricostruzione degli storici dove e' ESATTA
    ... -m app.scripts.backfill_plan_outcomes --applica --ricostruisci

Sola lettura per default, come `repair_price_basis`: un rapporto si legge, e
solo dopo si decide.

Che cosa fa
===========
Fa correre la gara stop-contro-target su ogni alert che non ha ancora una riga
in `plan_outcomes`. Non e' un percorso separato: chiama la STESSA
`mature_plan_outcomes` che gira a fine scansione, perche' due implementazioni
dello stesso calcolo divergono al primo ritocco e qui la divergenza
produrrebbe uno storico misurato con una regola e un incrementale misurato con
un'altra — indistinguibili una volta nella stessa tabella.

La ricostruzione, e perche' e' limitata
=======================================
Con `--ricostruisci` gli alert storici dei detector che NON emettevano un
livello ne ricevono uno, ma solo dove e' un FATTO delle barre:

    gap_and_go          la chiusura della barra precedente al gap
    le tre divergenze   l'estremo della barra del segnale, che e' l'ultimo
                        pivot per costruzione

⚠️ `adx_confirmation` e `squeeze_expansion` restano fuori. Ricostruirli
vorrebbe dire RICALCOLARE un livello Donchian o una finestra di compressione
con parametri che potrebbero essere cambiati, e il risultato sarebbe
indistinguibile da uno misurato. E' la lezione di SOXS: un fattore dedotto e
applicato all'indietro «sembra perfettamente sano ed e' silenziosamente
sbagliato».

Le righe ricostruite portano `source='ricostruito'` e restano escludibili con
un WHERE per sempre.
"""
from __future__ import annotations

import argparse

from loguru import logger
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.models import Alert, PlanOutcome
from app.services.plan_outcome_service import mature_plan_outcomes


def _rapporto(db) -> None:
    """Che cosa c'e' nel magazzino, per esito e per provenienza."""
    totale = db.execute(select(func.count()).select_from(PlanOutcome)).scalar_one()
    senza = db.execute(
        select(func.count()).select_from(Alert)
        .where(~Alert.id.in_(select(PlanOutcome.alert_id)))
    ).scalar_one()
    logger.info(f"righe in plan_outcomes: {totale}   alert ancora senza esito: {senza}")
    if not totale:
        return
    for esito, n, r_medio in db.execute(
        select(PlanOutcome.esito, func.count(), func.avg(PlanOutcome.r_multiple))
        .group_by(PlanOutcome.esito).order_by(func.count().desc())
    ):
        logger.info(f"   {esito:10s} {n:6d}   R medio {r_medio:+.2f}")
    for fonte, n in db.execute(
        select(PlanOutcome.source, func.count()).group_by(PlanOutcome.source)
    ):
        logger.info(f"   provenienza {fonte:12s} {n:6d}")
    # ⚠️ Il numero che questo magazzino esiste per produrre e che nessun altro
    # sa dare: quante volte lo stop e' stato colpito PRIMA di un target che poi
    # e' arrivato lo stesso. E' la misura di uno stop troppo stretto.
    stretti = db.execute(
        select(func.count()).select_from(PlanOutcome)
        .where(PlanOutcome.stop_hit_date.is_not(None),
               PlanOutcome.tp1_hit_date.is_not(None),
               PlanOutcome.stop_hit_date < PlanOutcome.tp1_hit_date)
    ).scalar_one()
    logger.info(f"   stop colpito PRIMA di un target poi raggiunto: {stretti}")


def run(applica: bool = False, ricostruisci: bool = False) -> None:
    db = SessionLocal()
    try:
        logger.info("prima:")
        _rapporto(db)
        scritte = mature_plan_outcomes(db, commit=False, ricostruisci=ricostruisci)
        logger.info(f"righe che la passata produce: {scritte}")
        if applica:
            db.commit()
            logger.info("scritte.")
            _rapporto(db)
        else:
            # ⚠️ Rollback esplicito: senza, la sessione porterebbe le righe in
            # memoria e un commit successivo di qualcun altro le scriverebbe
            # comunque — una modalita' «sola lettura» che scrive e' peggio di
            # nessuna modalita' sola lettura.
            db.rollback()
            logger.info("sola lettura: niente e' stato scritto. Usa --applica.")
    finally:
        db.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--applica", action="store_true",
                    help="scrive davvero (default: solo rapporto)")
    ap.add_argument("--ricostruisci", action="store_true",
                    help="ricostruisce il livello degli storici dove e' esatto")
    args = ap.parse_args()
    run(applica=args.applica, ricostruisci=args.ricostruisci)


if __name__ == "__main__":
    main()
