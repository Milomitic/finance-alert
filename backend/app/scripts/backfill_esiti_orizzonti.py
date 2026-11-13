"""Riempimento di `esiti_orizzonti` su tutta la storia, con la prova di parita'.

Gli esiti si ricavano solo dalle barre, quindi il riempimento e' completo: non
c'e' niente che sia esistito soltanto al momento dell'emissione.

La prova di parita': all'orizzonte PROPRIO del detector, sugli alert la cui
ancora coincide con `signal_date` (mai spostati da una revisione) e maturati
col metodo corrente (prima del 2026-08-27 il riferimento era la media), la tabella
nuova deve dare lo stesso rendimento e lo stesso colpo sulla mediana di
`signal_outcomes`. E' la stessa aritmetica chiamata da due posti; se divergono
si e' rotta una delle due, e lo script esce 1.

Nel pod (Postgres) o in locale da `backend/`:
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


def parita(db) -> tuple[int, int, list[str]]:
    """(confrontati, discordi, esempi)."""
    nuovi = {
        (r.alert_id, r.orizzonte): r
        for r in db.execute(select(EsitoOrizzonte)).scalars()
    }
    confrontati = discordi = 0
    esempi: list[str] = []
    for o in db.execute(select(SignalOutcome).where(
        SignalOutcome.source == "live", SignalOutcome.method_version == OUTCOME_METHOD_VERSION,
    )).scalars():
        n = nuovi.get((o.alert_id, o.horizon_days))
        if n is None or n.ancora != o.signal_date:
            continue
        confrontati += 1
        stesso = abs(n.rendimento - o.fwd_return) < 1e-9 and n.colpo_mediana == o.mkt_neutral_hit
        if not stesso:
            discordi += 1
            if len(esempi) < 5:
                esempi.append(
                    f"alert {o.alert_id} h={o.horizon_days}: rend {n.rendimento:.6f} contro "
                    f"{o.fwd_return:.6f}, colpo {n.colpo_mediana} contro {o.mkt_neutral_hit}"
                )
    return confrontati, discordi, esempi


def main() -> int:
    with dbm.SessionLocal() as db:
        scritte = eo.matura(db, eta_massima_giorni=None)
        righe = db.execute(select(EsitoOrizzonte.orizzonte, EsitoOrizzonte.controlli_n)).all()
        confrontati, discordi, esempi = parita(db)

    per_h = Counter(h for h, _ in righe)
    con_ctrl = Counter(h for h, n in righe if n)
    print(f"righe scritte ora: {scritte}   totali: {len(righe)}")
    for h in eo.ORIZZONTI:
        tot = per_h.get(h, 0)
        print(f"  h={h:>2}: {tot:>6} righe, {con_ctrl.get(h, 0):>6} col controllo")
    print(f"parita' con signal_outcomes: {confrontati} confrontati, {discordi} discordi")
    for e in esempi:
        print("  ", e)
    return 1 if discordi else 0


if __name__ == "__main__":
    sys.exit(main())
