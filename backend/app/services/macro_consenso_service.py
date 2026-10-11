"""L'archivio dei consensi macro (2026-10-11).

Forexfactory pubblica la sola settimana in corso: questo servizio la legge e la
CONSERVA, rilascio per rilascio, cosi' che domani si sappia quale fosse la
stima di oggi. Da qui vengono due cose a schermo:

- il colore di «Attuale» contro la stima DELLO STESSO rilascio;
- le colonne «Previsto» e «Attuale» dello storico.

Valori nell'unita' del consenso, con la stessa conversione di
`calendar_service.valori_nel_consenso`.

I rilasci PASSATI vengono da Nasdaq (`archivia_nasdaq`), il cui calendario
risponde per qualunque giorno: e' cosi' che l'archivio ha anche i previsti di
prima che esistesse.
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


def _variazioni_fred(db: Session, etichetta: str) -> list | None:
    """Le variazioni della serie FRED di un'etichetta, per riconoscere le righe
    di Nasdaq. None se l'etichetta non ha una serie."""
    from app.models.macro import MacroObservation, MacroSeries
    from app.services import macro_analisi_service as man

    serie = db.execute(select(MacroSeries).where(MacroSeries.label == etichetta).limit(1)).scalars().first()
    if serie is None:
        return None
    oss = db.execute(
        select(MacroObservation.date, MacroObservation.value)
        .where(MacroObservation.series_id == serie.id, MacroObservation.value.is_not(None))
        .order_by(MacroObservation.date.asc())
    ).all()
    return man.variazioni([(d, float(v)) for d, v in oss], serie.unit in man.UNITA_TASSO)


def _fred_prima(variazioni: list | None, giorno: date) -> tuple[float | None, float | None] | None:
    """(sul periodo, sull'anno) dell'ultima osservazione FRED prima del rilascio.

    Basta per riconoscere le due righe: se FRED non ha ancora il mese appena
    pubblicato, quella del mese prima ha comunque l'ordine di grandezza giusto.
    """
    prima = [v for v in (variazioni or []) if v.data < giorno]
    return (prima[-1].sul_periodo, prima[-1].sull_anno) if prima else None


def archivia_nasdaq(
    db: Session,
    giorni: list[date],
    *,
    leggi=None,
    adesso: datetime | None = None,
) -> tuple[int, list[date]]:
    """I consensi di Nasdaq per ciascuno dei `giorni`, nell'archivio.

    Rende (rilasci scritti o completati, giorni che la fonte non ha servito).
    Una riga gia' archiviata da Forexfactory resta sua: Nasdaq aggiunge solo
    cio' che manca, piu' la stima sull'anno che Forexfactory non porta. Una
    riga a un giorno di distanza e' lo stesso rilascio — le due fonti datano
    in fusi diversi le uscite asiatiche ed europee.
    """
    from app.services import calendar_service
    from app.services import forexfactory_consensus as ff
    from app.services import nasdaq_consensus as nq

    leggi = leggi or nq.eventi_del_giorno
    adesso = adesso or datetime.now(UTC)
    fred: dict[str, list | None] = {}
    n = 0
    mancanti: list[date] = []
    for giorno in giorni:
        try:
            eventi = leggi(giorno)
        except Exception:  # noqa: BLE001 — il giorno si dichiara mancante, gli altri vanno avanti
            mancanti.append(giorno)
            continue
        for etichetta, (paese, nome, misura) in nq.NASDAQ_MAP.items():
            righe = [e for e in eventi if e.paese == paese and e.nome == nome]
            if not righe:
                continue
            if etichetta not in fred:
                fred[etichetta] = _variazioni_fred(db, etichetta)
            principale, annuo = nq.assegna(righe, misura, _fred_prima(fred[etichetta], giorno))
            if principale is None or (principale.actual is None and principale.consensus is None):
                continue
            formato = calendar_service._formato(principale.consensus) or calendar_service._formato(principale.actual)                 or calendar_service._formato(principale.previous)
            scala = _scala(formato)

            def num(raw: str | None, scala: float = scala) -> float | None:
                v = ff.parse_numeric(raw)
                return None if v is None else v / scala

            vicine = db.execute(
                select(MacroConsenso).where(
                    MacroConsenso.etichetta == etichetta,
                    MacroConsenso.data >= giorno - timedelta(days=1),
                    MacroConsenso.data <= giorno + timedelta(days=1),
                )
            ).scalars().all()
            riga = next((r for r in vicine if r.data == giorno), vicine[0] if vicine else None)
            if riga is None:
                riga = MacroConsenso(etichetta=etichetta, data=giorno, titolo=f"Nasdaq · {nome}"[:128], formato=formato)
                db.add(riga)
            if riga.previsto is None:
                riga.previsto = num(principale.consensus)
            if riga.attuale is None:
                riga.attuale = num(principale.actual)
            if riga.precedente is None:
                riga.precedente = num(principale.previous)
            if not riga.formato:
                riga.formato = formato
            if annuo is not None:
                pa, aa = ff.parse_numeric(annuo.consensus), ff.parse_numeric(annuo.actual)
                riga.previsto_annuo = pa if pa is not None else riga.previsto_annuo
                riga.attuale_annuo = aa if aa is not None else riga.attuale_annuo
            riga.aggiornato_il = adesso
            n += 1
        db.commit()
    return n, mancanti


Esito = str  # "sopra" | "sotto" | "in_linea"


def misura(etichetta: str) -> str:
    """Quale variazione misura il consenso principale di un'etichetta. Senza
    una voce in `NASDAQ_MAP` vale «livello»: un livello sopra le attese e' una
    variazione sopra le attese, perche' il precedente e' lo stesso."""
    from app.services import nasdaq_consensus as nq

    voce = nq.NASDAQ_MAP.get(etichetta)
    return voce[2] if voce else "livello"


def esito(attuale: float | None, previsto: float | None) -> Esito | None:
    """Il dato contro la sua stima. Uguale e' «in linea»: la fonte pubblica i
    due numeri con gli stessi decimali, quindi l'uguaglianza e' quella che si
    legge a schermo."""
    if attuale is None or previsto is None:
        return None
    d = round(attuale - previsto, 6)
    return "sopra" if d > 0 else "sotto" if d < 0 else "in_linea"


def esiti(riga: MacroConsenso | None, misura_: str) -> tuple[Esito | None, Esito | None]:
    """(esito della variazione sul periodo, di quella sull'anno) di un rilascio.

    ⚠️ Il colore di una variazione e' il suo esito contro la stima, non il suo
    segno: un'inflazione al +0,2% contro un +0,4% atteso e' una sorpresa al
    ribasso anche se e' positiva. Ogni variazione si confronta con la stima
    DELLA SUA misura; dove non c'e', nessun esito.
    """
    if riga is None:
        return None, None
    principale = esito(riga.attuale, riga.previsto)
    if misura_ == "anno":
        return None, principale
    return principale, esito(riga.attuale_annuo, riga.previsto_annuo)


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
