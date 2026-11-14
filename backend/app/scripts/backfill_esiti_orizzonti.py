"""Riempimento di `esiti_orizzonti` su tutta la storia, con la prova di parita'.

Gli esiti si ricavano solo dalle barre, quindi il riempimento e' completo: non
c'e' niente che sia esistito soltanto al momento dell'emissione.

La prova di parita': all'orizzonte PROPRIO del detector, sugli alert la cui
ancora coincide con `signal_date` (mai spostati da una revisione) e maturati
col metodo corrente (prima del 2026-08-27 il riferimento era la media), le due
tabelle si confrontano in tre gruppi.

- **Stessi ingressi** (rendimento e mediana dell'universo uguali): il colpo
  DEVE coincidere. Se no, una delle due aritmetiche si e' rotta e lo script
  esce 1.
- **Mediana diversa** e **rendimento diverso**: i dati sono cambiati dopo la
  maturazione di `signal_outcomes` (barre riparate, universo cambiato). Si
  contano e si stampano, ma non sono un difetto di questo codice.

⚠️ Misurato il 2026-11-14 alla prima esecuzione in produzione: 185 righe con
gli stessi ingressi e zero discordanze; 1.698 con la mediana diversa (0,39
punti di scarto medio, fino a 1,5) e 44 colpi opposti. La prova che non e'
questo codice: ricalcolata ADESSO con la funzione di `signal_outcome_service`,
la mediana coincide con quella nuova. E' `signal_outcomes` a portare valori
che i dati di oggi non riproducono (FA-164).

Nel pod, da `/app/backend`, o in locale da `backend/`:
    python -m app.scripts.backfill_esiti_orizzonti
"""
from __future__ import annotations

import sys
from collections import Counter

from sqlalchemy import select

import app.core.db as dbm
from app.core.provenance import OUTCOME_METHOD_VERSION
from app.models import EsitoOrizzonte, SignalOutcome
from app.services import esiti_orizzonti_service as eo


def parita(db) -> dict:
    """Conteggi del confronto. `discordi` conta solo le righe con gli stessi
    ingressi, cioe' i difetti di aritmetica."""
    nuovi = {
        (r.alert_id, r.orizzonte): r
        for r in db.execute(select(EsitoOrizzonte)).scalars()
    }
    out: dict = {"confrontati": 0, "discordi": 0, "deriva_mediana": 0, "deriva_rendimento": 0,
                 "colpi_cambiati_dalla_deriva": 0, "esempi": []}
    for o in db.execute(select(SignalOutcome).where(
        SignalOutcome.source == "live", SignalOutcome.method_version == OUTCOME_METHOD_VERSION,
    )).scalars():
        n = nuovi.get((o.alert_id, o.horizon_days))
        if n is None or n.ancora != o.signal_date:
            continue
        out["confrontati"] += 1
        stesso_colpo = n.colpo_mediana == o.mkt_neutral_hit
        mediana_diversa = (n.mediana_universo is None) != (o.universe_mean_fwd is None) or (
            n.mediana_universo is not None
            and abs(n.mediana_universo - o.universe_mean_fwd) > 1e-12
        )
        if abs(n.rendimento - o.fwd_return) > 1e-9:
            out["deriva_rendimento"] += 1
            out["colpi_cambiati_dalla_deriva"] += not stesso_colpo
        elif mediana_diversa:
            out["deriva_mediana"] += 1
            out["colpi_cambiati_dalla_deriva"] += not stesso_colpo
        elif not stesso_colpo:
            out["discordi"] += 1
            if len(out["esempi"]) < 5:
                out["esempi"].append(
                    f"alert {o.alert_id} h={o.horizon_days}: colpo {n.colpo_mediana} "
                    f"contro {o.mkt_neutral_hit} con gli stessi ingressi"
                )
    return out


def main() -> int:
    with dbm.SessionLocal() as db:
        scritte = eo.matura(db, eta_massima_giorni=None)
        righe = db.execute(select(EsitoOrizzonte.orizzonte, EsitoOrizzonte.controlli_n)).all()
        p = parita(db)

    per_h = Counter(h for h, _ in righe)
    con_ctrl = Counter(h for h, n in righe if n)
    print(f"righe scritte ora: {scritte}   totali: {len(righe)}")
    for h in eo.ORIZZONTI:
        print(f"  h={h:>2}: {per_h.get(h, 0):>6} righe, {con_ctrl.get(h, 0):>6} col controllo")
    print(f"parita' con signal_outcomes: {p['confrontati']} confrontati, "
          f"{p['discordi']} discordi a parita' di ingressi")
    print(f"  deriva dei dati dopo la maturazione: {p['deriva_mediana']} con la mediana diversa, "
          f"{p['deriva_rendimento']} col rendimento diverso, "
          f"{p['colpi_cambiati_dalla_deriva']} colpi cambiati")
    for e in p["esempi"]:
        print("  ", e)
    return 1 if p["discordi"] else 0


if __name__ == "__main__":
    sys.exit(main())
