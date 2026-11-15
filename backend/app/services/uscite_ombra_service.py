"""Le uscite alternative del piano, in prova silenziosa (FA-141).

Perche': sui piani a finestra chiusa 322 stop su 2.238 erano passati da +1R
prima di chiudere in perdita, e 808 «scaduti» su 5.021 anche. Una regola
d'uscita diversa forse avrebbe tenuto parte di quel guadagno — o forse lo
avrebbe pagato altrove, chiudendo a pareggio trade che poi andavano a
target. Non si sa, e qui si misura.

Le varianti corrono sulla STESSA geometria della riga di `plan_outcomes`:
stesso ingresso, stesso stop iniziale, stesso primo target, stesso
orizzonte. Cambia solo la regola d'uscita:

    attuale        quella di oggi, ricalcolata: e' il controllo di parita'
    pareggio_1r    dopo +1R di escursione favorevole lo stop va all'ingresso
    pareggio_05r   lo stesso dopo +0,5R
    uscita_meta    a meta' orizzonte si esce alla chiusura se sotto +0,25R

⚠️ Tre convenzioni pessimiste, tutte necessarie perche' le barre sono
giornaliere e non dicono l'ordine dentro la seduta:

1. Stop e target nella stessa barra: vince lo stop (come la gara di oggi).
2. Lo stop si sposta all'ingresso dalla barra SUCCESSIVA a quella che ha
   toccato la soglia: nella stessa barra il massimo puo' essere venuto dopo
   il minimo, e spostarlo subito trasformerebbe in pareggio uno stop vero.
3. L'uscita a meta' orizzonte e' alla CHIUSURA di quella barra, dopo aver
   guardato stop e target della barra stessa.

Solo righe a finestra CHIUSA: una variante si confronta con l'attuale solo
quando entrambe hanno visto tutto l'orizzonte (la lezione di
`plan_performance_service._chiusa`).

Nessun consumatore a schermo. Il criterio d'adozione e' scritto prima dei
dati in `docs/superpowers/specs/2026-11-15-uscite-in-ombra.md`.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PlanOutcome, PlanOutcomeOmbra
from app.services.plan_outcome_service import PLAN_METHOD_VERSION, Barra, _tutte_le_barre

#: Cambia quando cambia la regola di una variante: le righe si rimisurano.
VERSIONE_VARIANTI = "1"


@dataclass(frozen=True)
class Variante:
    nome: str
    #: Escursione favorevole, in R, dopo cui lo stop va all'ingresso.
    pareggio_dopo_r: float | None = None
    #: A meta' orizzonte si esce se il trade vale meno di tanti R.
    uscita_meta_sotto_r: float | None = None


VARIANTI: tuple[Variante, ...] = (
    Variante("attuale"),
    Variante("pareggio_1r", pareggio_dopo_r=1.0),
    Variante("pareggio_05r", pareggio_dopo_r=0.5),
    Variante("uscita_meta", uscita_meta_sotto_r=0.25),
)


@dataclass(frozen=True)
class EsitoVariante:
    esito: str
    r_multiplo: float
    barre: int


def corri_variante(
    *, lato: str, ingresso: float, stop: float, tp1: float, r: float,
    barre: Sequence[Barra], orizzonte: int, variante: Variante,
) -> EsitoVariante | None:
    """L'esito di una regola d'uscita sulle barre dopo l'ingresso. None se
    la finestra non e' ancora chiusa (meno barre dell'orizzonte). Pura."""
    if r <= 0 or orizzonte <= 0 or len(barre) < orizzonte:
        return None
    lungo = lato == "long"
    segno = 1.0 if lungo else -1.0
    rr1 = (tp1 - ingresso) * segno / r
    stop_ora = stop
    a_pareggio = False
    meta = orizzonte // 2 if variante.uscita_meta_sotto_r is not None else None
    finestra = barre[:orizzonte]
    for i, b in enumerate(finestra, 1):
        if lungo:
            colpo_stop, colpo_tp1 = b.basso <= stop_ora, b.alto >= tp1
            favorevole = (b.alto - ingresso) / r
        else:
            colpo_stop, colpo_tp1 = b.alto >= stop_ora, b.basso <= tp1
            favorevole = (ingresso - b.basso) / r
        if colpo_stop:
            r_stop = (stop_ora - ingresso) * segno / r
            if colpo_tp1:
                return EsitoVariante("ambigua", r_stop, i)
            return EsitoVariante("pareggio" if a_pareggio else "stop", r_stop, i)
        if colpo_tp1:
            return EsitoVariante("tp1", rr1, i)
        if meta and i == meta:
            valore = (b.chiusura - ingresso) * segno / r
            if valore < variante.uscita_meta_sotto_r:
                return EsitoVariante("uscita_meta", valore, i)
        # Dalla barra successiva (convenzione 2).
        if (variante.pareggio_dopo_r is not None and not a_pareggio
                and favorevole >= variante.pareggio_dopo_r):
            stop_ora, a_pareggio = ingresso, True
    ultima = finestra[-1]
    return EsitoVariante("scaduto", (ultima.chiusura - ingresso) * segno / r, len(finestra))


def versione() -> str:
    return f"{PLAN_METHOD_VERSION}.{VERSIONE_VARIANTI}"


def matura(db: Session, *, commit: bool = True) -> int:
    """Scrive le varianti per ogni piano a finestra chiusa che non le ha alla
    versione corrente. Rende le righe scritte."""
    ver = versione()
    gia = {
        (a, v) for a, v in db.execute(
            select(PlanOutcomeOmbra.alert_id, PlanOutcomeOmbra.variante)
            .where(PlanOutcomeOmbra.method_version == ver)
        ).all()
    }
    piani = db.execute(
        select(PlanOutcome)
        .where(PlanOutcome.method_version == PLAN_METHOD_VERSION,
               PlanOutcome.legs_window_complete.is_(True))
        .order_by(PlanOutcome.stock_id, PlanOutcome.alert_id)
    ).scalars().all()
    vecchie = {
        (a, v): riga for riga in db.execute(
            select(PlanOutcomeOmbra).where(PlanOutcomeOmbra.method_version != ver)
        ).scalars()
        for a, v in [(riga.alert_id, riga.variante)]
    }
    scritte = 0
    barre_titolo: tuple[int, list[Barra]] | None = None
    for p in piani:
        mancanti = [v for v in VARIANTI if (p.alert_id, v.nome) not in gia]
        if not mancanti:
            continue
        if barre_titolo is None or barre_titolo[0] != p.stock_id:
            barre_titolo = (p.stock_id, _tutte_le_barre(db, p.stock_id))
        dopo = [b for b in barre_titolo[1] if b.data > p.entry_date.isoformat()]
        lato = "long" if p.tone == "bull" else "short"
        for v in mancanti:
            e = corri_variante(lato=lato, ingresso=p.entry, stop=p.stop, tp1=p.tp1, r=p.r,
                               barre=dopo, orizzonte=p.horizon_days, variante=v)
            if e is None:
                continue
            valori = dict(detector=p.detector, esito=e.esito, r_multiple=e.r_multiplo,
                          bars_to_outcome=e.barre, method_version=ver,
                          matured_at=datetime.now(UTC))
            vecchia = vecchie.get((p.alert_id, v.nome))
            if vecchia is not None:
                for k, val in valori.items():
                    setattr(vecchia, k, val)
            else:
                db.add(PlanOutcomeOmbra(alert_id=p.alert_id, variante=v.nome, **valori))
            scritte += 1
    if scritte:
        db.flush()
        if commit:
            db.commit()
    return scritte
