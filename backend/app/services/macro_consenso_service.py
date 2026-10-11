"""L'archivio dei consensi macro (2026-10-11).

Forexfactory pubblica la sola settimana in corso: questo servizio la legge e la
CONSERVA, rilascio per rilascio, cosi' che domani si sappia quale fosse la
stima di oggi. Da qui vengono due cose a schermo:

- il colore di «Attuale» contro la stima DELLO STESSO rilascio;
- le colonne «Previsto» e «Attuale» dello storico.

Valori nell'unita' del consenso, con la stessa conversione di
`calendar_service.valori_nel_consenso`.
"""
from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.macro import MacroConsenso

#: Quanto dopo la fine del periodo puo' cadere il suo rilascio: il CPI di
#: agosto esce a meta' settembre, il PIL di un trimestre fino a due mesi dopo.
_RILASCIO_ENTRO = timedelta(days=75)


def _scala(formato: str) -> float:
    return {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}.get(formato, 1.0)


def archivia(db: Session, *, adesso: datetime | None = None) -> int:
    """Conserva i consensi della settimana di Forexfactory. Rende quanti
    rilasci ha scritto o aggiornato. Un dato uscito non torna mai vuoto: la
    settimana dopo il feed non lo porta piu', e la riga resta com'era."""
    from app.services import calendar_service
    from app.services import forexfactory_consensus as ff

    adesso = adesso or datetime.now(UTC)
    eventi = ff._get_events()
    n = 0
    visti: set[tuple[str, date]] = set()
    for etichetta, (paese, schema) in ff._FF_LABEL_MAP.items():
        titolo_re = re.compile(schema, re.IGNORECASE)
        for ev in eventi:
            if ev.country != paese or not titolo_re.search(ev.title):
                continue
            # ⚠️ Un rilascio, un evento: il PRIMO che combacia, come fa
            # `consensus_for_label` per il calendario. Una regola che ne prende
            # due nello stesso giorno («Retail Sales» e «Core Retail Sales»)
            # violava il vincolo e faceva cadere l'intero giro (2026-10-11).
            if (etichetta, ev.date) in visti:
                continue
            visti.add((etichetta, ev.date))
            formato = calendar_service._formato(ev.forecast) or calendar_service._formato(ev.previous) \
                or calendar_service._formato(ev.actual)
            scala = _scala(formato)

            def num(raw: str | None, scala: float = scala) -> float | None:
                v = ff.parse_numeric(raw)
                return None if v is None else v / scala

            riga = db.execute(
                select(MacroConsenso).where(MacroConsenso.etichetta == etichetta, MacroConsenso.data == ev.date)
            ).scalars().first()
            if riga is None:
                riga = MacroConsenso(etichetta=etichetta, data=ev.date, titolo=ev.title[:128])
                db.add(riga)
            previsto, attuale, precedente = num(ev.forecast), num(ev.actual), num(ev.previous)
            if previsto is not None:
                riga.previsto = previsto
            if attuale is not None:
                riga.attuale = attuale
            if precedente is not None:
                riga.precedente = precedente
            if formato or riga.formato is None:
                # Un feed che non porta piu' i valori non cancella il formato.
                riga.formato = formato
            riga.aggiornato_il = adesso
            n += 1
    db.commit()
    return n


def ultimo_prima(db: Session, etichetta: str, giorno: date) -> MacroConsenso | None:
    """Il rilascio archiviato piu' recente PRIMA di `giorno`."""
    return db.execute(
        select(MacroConsenso)
        .where(MacroConsenso.etichetta == etichetta, MacroConsenso.data < giorno)
        .order_by(MacroConsenso.data.desc())
        .limit(1)
    ).scalars().first()


def _passo(periodi: list[date]) -> int:
    """La cadenza della serie in giorni: la mediana degli ultimi intervalli."""
    coda = periodi[-7:]
    salti = sorted((b - a).days for a, b in zip(coda, coda[1:], strict=False) if b > a)
    return salti[len(salti) // 2] if salti else 30


def _dopo(periodo: date, passo: int) -> date:
    """Il periodo successivo: un mese esatto per le serie mensili, altrimenti
    lo stesso passo in giorni."""
    if 27 <= passo <= 32:
        anno, mese = (periodo.year + 1, 1) if periodo.month == 12 else (periodo.year, periodo.month + 1)
        return periodo.replace(year=anno, month=mese, day=1) if periodo.day == 1 else periodo + timedelta(days=passo)
    return periodo + timedelta(days=passo)


def per_periodo(db: Session, etichetta: str, periodi: list[date]) -> dict[date, MacroConsenso]:
    """Ogni periodo di osservazione col rilascio che lo ha pubblicato.

    ⚠️ Conta la FINE del periodo, non l'inizio: per FRED il CPI di settembre ha
    data 1 settembre, e il rilascio dell'11 settembre — che pubblica AGOSTO —
    cadrebbe su settembre se si guardasse l'inizio. Un rilascio appartiene
    all'ultimo periodo gia' finito; la fine di un periodo e' l'inizio del
    successivo, e oltre l'ultima osservazione nota si prolunga la cadenza, cosi'
    che il rilascio di un mese che FRED non ha ancora non finisca sul mese prima.
    """
    if not periodi:
        return {}
    ordinati = sorted(set(periodi))
    passo = _passo(ordinati)
    tutti = list(ordinati)
    while len(tutti) < len(ordinati) + 4:
        tutti.append(_dopo(tutti[-1], passo))
    fine = {p: tutti[i + 1] for i, p in enumerate(tutti[:-1])}
    righe = db.execute(
        select(MacroConsenso)
        .where(MacroConsenso.etichetta == etichetta, MacroConsenso.data > ordinati[0])
        .order_by(MacroConsenso.data.asc())
    ).scalars().all()
    reali = set(ordinati)
    out: dict[date, MacroConsenso] = {}
    for r in righe:
        finiti = [p for p in tutti[:-1] if fine[p] <= r.data]
        if not finiti:
            continue
        periodo = finiti[-1]
        if periodo in reali and r.data - fine[periodo] <= _RILASCIO_ENTRO and periodo not in out:
            out[periodo] = r
    return out
