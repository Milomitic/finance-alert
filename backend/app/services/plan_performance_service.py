"""Il magazzino degli esiti di piano, aggregato per il cruscotto.

⚠️ L'intestazione e' l'ATTESA IN R, non il tasso di successo, e non e' una
scelta estetica. TP1 sta a R:R fino a 4,0: per costruzione questo motore fa
piani a bassa frequenza di vincita e alto guadagno unitario, quindi un tasso
letto da solo sembrerebbe pessimo mentre il sistema guadagna. Un tasso del 35%
a 4:1 batte un 60% a 1:1, e solo l'attesa lo dice.

⚠️ E ogni numero porta il campione che lo regge — righe, FINESTRE INDIPENDENTI,
e un intervallo che le paga. Questo progetto ha gia' mostrato «100%» su sei
setup risolti e un detector con due soli valori di Forza distinti su 95 alert.
La regola che ne e' uscita: un numero senza il suo campione e' lo stesso
difetto di un numero sbagliato.

Sola lettura, calcolato su richiesta.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Alert, PlanOutcome, Stock
from app.models.plan_outcome import FONTE_RICOSTRUITO
from app.stats.media import mean_interval
from app.stats.sizing import independent_blocks

#: Sotto questa soglia di righe la cella e' marcata `low_confidence`. Stesso
#: pavimento del cubo dei detector e del monitor di deriva: tre numeri diversi
#: sullo stesso schermo per la stessa idea sarebbero peggio di nessuno.
_DEFAULT_MIN_N = 30


def _mediana(valori: Sequence[float]) -> float | None:
    """⚠️ Con `sorted` DENTRO: la correttezza di una mediana non puo' dipendere
    dal fatto che il chiamante si ricordi di ordinare. Un `_median` che lo
    dava per scontato e' gia' stato trovato da questo progetto."""
    if not valori:
        return None
    v = sorted(valori)
    meta = len(v) // 2
    return v[meta] if len(v) % 2 else (v[meta - 1] + v[meta]) / 2.0


def _cella(detector: str, righe: Sequence[PlanOutcome], min_n: int) -> dict:
    n = len(righe)
    erre = [r.r_multiple for r in righe]
    attesa = sum(erre) / n

    # Conservativo, come nel cubo: l'orizzonte piu' LARGO del gruppo detta la
    # sovrapposizione.
    orizzonte = max((r.horizon_days for r in righe), default=21)
    eff_n = independent_blocks([r.signal_date for r in righe], orizzonte)
    intervallo = mean_interval(erre, effective_n=eff_n)

    # ⚠️ L'ipotesi nulla qui e' lo ZERO, non il 50%: e' un'attesa in R, non una
    # percentuale. E il vocabolario e' diverso da quello di `quality_tag`
    # (coinflip/negative/edge) di proposito — stessa parola con una barra
    # diversa sullo stesso schermo sarebbe peggio di nessuna parola.
    if intervallo is None:
        verdetto = "inconclusive"
    elif intervallo[0] > 0:
        verdetto = "positive"
    elif intervallo[1] < 0:
        verdetto = "negative"
    else:
        verdetto = "inconclusive"

    conteggi: dict[str, int] = defaultdict(int)
    for r in righe:
        conteggi[r.esito] += 1

    vinte = [r for r in righe if r.esito == "tp1"]
    perse = [r for r in righe if r.esito in ("stop", "ambigua")]

    return {
        "detector": detector,
        "n": n,
        "effective_n": eff_n,
        "horizon_days": orizzonte,
        # L'intestazione.
        "expectancy_r": attesa,
        "expectancy_ci": list(intervallo) if intervallo else None,
        "verdict": verdetto,
        # Secondario, e mai da solo: vedi il docstring del modulo.
        "win_rate": len(vinte) / n * 100.0,
        "esiti": {k: conteggi.get(k, 0)
                  for k in ("tp1", "stop", "ambigua", "scaduto")},
        # ⚠️ Il numero che nessun altro magazzino sa dare: quante volte lo stop
        # e' stato colpito PRIMA di un target che poi e' arrivato lo stesso.
        # Non e' «entrambi toccati» — l'ORDINE e' tutta la diagnosi.
        "stop_too_tight": sum(
            1 for r in righe
            if r.stop_hit_date and r.tp1_hit_date and r.stop_hit_date < r.tp1_hit_date
        ),
        # Gli ingressi per tarare la geometria, continui e quindi con molta
        # piu' potenza per osservazione di un binario: quanto i VINTI sono
        # andati contro (lo stop poteva stringersi?) e quanto i PERSI erano
        # andati a favore (c'era qualcosa sul tavolo?).
        "mae_r_on_wins": _mediana([r.mae_r for r in vinte]),
        "mfe_r_on_losses": _mediana([r.mfe_r for r in perse]),
        "median_bars": _mediana([float(r.bars_to_outcome) for r in righe]),
        "low_confidence": n < min_n,
    }


def compute_plan_performance(db: Session, *, min_n: int = _DEFAULT_MIN_N) -> dict:
    """Una riga per detector, piu' un involucro `meta` che dichiara la
    COPERTURA.

    ⚠️ La copertura non e' un ornamento. Sei detector su diciassette non
    emettevano un livello di invalidazione, quindi non producevano piani: una
    classifica costruita su questi dati li avrebbe omessi IN SILENZIO, coprendo
    undici detector su diciassette e sembrando completa. Un elenco parziale che
    non si dichiara parziale e' la forma di difetto peggiore.
    """
    righe = db.execute(select(PlanOutcome)).scalars().all()

    per_detector: dict[str, list[PlanOutcome]] = defaultdict(list)
    for r in righe:
        per_detector[r.detector].append(r)

    celle = [_cella(d, rs, min_n) for d, rs in sorted(per_detector.items())]
    celle.sort(key=lambda c: c["expectancy_r"], reverse=True)

    # Copertura: per ogni detector che ha prodotto alert, quanti hanno un
    # esito di piano. Si legge dagli ALERT, non dalle righe di esito, perche'
    # e' proprio l'assenza che va mostrata.
    con_piano: dict[str, int] = {d: len(rs) for d, rs in per_detector.items()}
    copertura = []
    for detector, totale in db.execute(
        select(Alert.signal_name, func.count()).group_by(Alert.signal_name)
    ):
        nome = detector or "(senza nome)"
        copertura.append({
            "detector": nome,
            "alerts": totale,
            "with_plan": con_piano.get(nome, 0),
            "without_plan": totale - con_piano.get(nome, 0),
        })
    copertura.sort(key=lambda c: c["without_plan"], reverse=True)

    date_segnale = [r.signal_date for r in righe]
    return {
        "meta": {
            "rows": len(righe),
            "reconstructed": sum(1 for r in righe if r.source == FONTE_RICOSTRUITO),
            "detectors_present": len(per_detector),
            "date_range": {
                "from": min(date_segnale).isoformat() if date_segnale else None,
                "to": max(date_segnale).isoformat() if date_segnale else None,
            },
            "coverage": copertura,
            "min_n": min_n,
        },
        "rows": celle,
    }


# ─── L'elenco, un segnale per riga ─────────────────────────────────────────

def _riga(esito: PlanOutcome, ticker: str, nome: str | None) -> dict:
    """Una riga per lo schermo. ⚠️ Nessuna conclusione precalcolata qui: le
    tre date delle gambe escono grezze, e chi rende decide come raccontarle.
    Congelare «stop troppo stretto» in un booleano dentro l'API vorrebbe dire
    che la definizione vive in due posti il giorno che qualcuno la affina."""
    return {
        "alert_id": esito.alert_id,
        "ticker": ticker,
        "name": nome,
        "detector": esito.detector,
        "tone": esito.tone,
        "signal_date": esito.signal_date,
        "entry_date": esito.entry_date,
        "entry": esito.entry,
        "stop": esito.stop,
        "tp1": esito.tp1,
        "tp2": esito.tp2,
        "r": esito.r,
        "horizon_days": esito.horizon_days,
        "esito": esito.esito,
        "resolved_date": esito.resolved_date,
        "bars_to_outcome": esito.bars_to_outcome,
        "r_multiple": esito.r_multiple,
        "mae_r": esito.mae_r,
        "mfe_r": esito.mfe_r,
        "tp2_reached": esito.tp2_reached,
        "stop_hit_date": esito.stop_hit_date,
        "tp1_hit_date": esito.tp1_hit_date,
        "tp2_hit_date": esito.tp2_hit_date,
        "source": esito.source,
    }


def elenco_esiti_piano(
    db: Session,
    *,
    esito: str | None = None,
    detector: str | None = None,
    tone: str | None = None,
    ticker: str | None = None,
    limit: int = 50,
    offset: int = 0,
    min_n: int = _DEFAULT_MIN_N,
) -> dict:
    """Gli esiti di piano, uno per segnale, i piu' recenti per primi.

    ⚠️ Il riassunto e' calcolato sulla POPOLAZIONE FILTRATA, mai sulla pagina.
    Questo progetto ha gia' stampato «50 setup chiusi» sopra una lista di 795 e
    conteggi di chip presi dalle righe ricevute invece che dal server: un
    numero che cambia con la dimensione della pagina non e' un conteggio.

    ⚠️ E il riassunto passa da `_cella`, la stessa funzione che alimenta il
    pannello per detector, invece di rifare le medie qui. Due implementazioni
    della stessa aggregazione divergono al primo ritocco, e allora due schermi
    direbbero due numeri diversi sullo stesso magazzino.
    """
    stmt = (
        select(PlanOutcome, Stock.ticker, Stock.name)
        .join(Stock, Stock.id == PlanOutcome.stock_id)
    )
    if esito:
        stmt = stmt.where(PlanOutcome.esito == esito)
    if tone:
        stmt = stmt.where(PlanOutcome.tone == tone)
    if ticker:
        stmt = stmt.where(Stock.ticker == ticker.strip().upper())

    # ⚠️ `resolved_date` e non `signal_date`: la domanda di questa vista e'
    # «che cosa si e' chiuso di recente», e un segnale vecchio che ha toccato
    # il target ieri e' una notizia di ieri.
    righe = db.execute(
        stmt.order_by(PlanOutcome.resolved_date.desc(), PlanOutcome.id.desc())
    ).all()

    # ⚠️ I conteggi per condizione si calcolano PRIMA di applicare il filtro
    # per condizione, e non e' un dettaglio: sono il menu del filtro stesso.
    # Calcolati dopo, selezionare un detector farebbe sparire tutti gli altri
    # dall'elenco — cioe' il controllo si disabiliterebbe da solo al primo uso,
    # e tornare indietro richiederebbe di sapere che esiste un «tutte».
    per_detector: dict[str, int] = defaultdict(int)
    for e, _tick, _nome in righe:
        per_detector[e.detector] += 1
    if detector:
        righe = [r for r in righe if r[0].detector == detector]
    esiti = [r[0] for r in righe]

    riassunto = _cella("tutti", esiti, min_n) if esiti else None
    if riassunto is not None:
        riassunto.pop("detector", None)

    fetta = righe[offset: offset + limit] if limit > 0 else righe
    return {
        "items": [_riga(e, tick, nome) for e, tick, nome in fetta],
        "total": len(righe),
        "has_more": offset + len(fetta) < len(righe),
        "counts_by_detector": dict(per_detector),
        "summary": riassunto,
    }
