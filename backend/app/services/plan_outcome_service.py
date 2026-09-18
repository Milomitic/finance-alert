"""La gara fra stop e target di un piano, barra per barra.

Risponde a «il piano mostrato a schermo avrebbe pagato?», che e' una domanda
DIVERSA da quella del magazzino `signal_outcomes` («il detector prevede la
deriva a orizzonte fisso?»). Le due convivono e non vanno mescolate: la
calibrazione, il monitor di deriva, il cubo dei detector e la curva di equity
sono tutti costruiti sulla chiusura a orizzonte fisso, e ridefinirla
cambierebbe in silenzio il significato di ogni numero d'efficacia a schermo.

⚠️ E' una GARA, non un «ha mai toccato il target». Una posizione con quelle
caratteristiche ha anche uno stop, e si sarebbe chiusa da sola in PERDITA se
lo stop arrivava prima. Contare i soli tocchi del target produce un tasso di
successo gonfiato per costruzione — quasi tutto tocca un target vicino, prima
o poi — ed e' il modo piu' comune di fabbricare una percentuale lusinghiera
che non corrisponde a nessun guadagno.

Questo modulo e' PURO: prende un piano e delle barre, non tocca il database.
La persistenza e la maturazione stanno altrove, cosi' la regola si prova da
sola e su numeri veri.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, NamedTuple

from sqlalchemy import exists, select

from app.models import Alert, OhlcvDaily, PlanOutcome
from app.models.plan_outcome import FONTE_EMESSO, FONTE_RICOSTRUITO
from app.signals.trade_plan import PianoDiTrade, costruisci_piano

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

#: Gli esiti che la gara sa produrre. ⚠️ Costanti e non stringhe sparse: la
#: colonna `plan_outcomes.esito` ha una lunghezza, e in questo repo una
#: costante piu' lunga della sua colonna ha gia' fermato ogni scansione per
#: ~19 ore — Postgres rifiuta il valore, SQLite lo accetta, quindi la suite
#: era verde. Un test le confronta con la lunghezza dichiarata sul modello.
ESITI: frozenset[str] = frozenset({"tp1", "stop", "ambigua", "scaduto"})


class Barra(NamedTuple):
    """Una seduta. `alto`/`basso` servono perche' la gara e' sul PERCORSO: una
    chiusura non dice se lo stop e' stato toccato durante la giornata."""
    data: str
    alto: float
    basso: float
    chiusura: float


@dataclass(frozen=True)
class EsitoGara:
    #: "tp1" | "stop" | "ambigua" | "scaduto"
    esito: str
    data: str
    barre: int
    #: Il guadagno in multipli di R. ⚠️ NON e' una costante per detector: i
    #: target sono tagliati a un multiplo di ATR, quindi l'R di un TP1 varia
    #: per segnale (misurato sui vettori: da 0,2 a 4,0).
    r_multiplo: float
    #: Massima escursione avversa e favorevole, in R, fino alla barra che
    #: RISOLVE. Sono gli ingressi per tarare stop e target, e valgono piu' di
    #: un binario per osservazione perche' sono continui.
    mae_r: float
    mfe_r: float
    #: Il secondo target e' stato toccato MENTRE LA POSIZIONE ERA APERTA.
    #: Tenuto a parte dall'esito: mescolarlo renderebbe incomparabili le righe.
    tp2_raggiunto: bool
    #: ⚠️ La data di PRIMO TOCCO di ciascuna gamba nell'orizzonte, a
    #: prescindere da chi ha vinto — anche quella toccata DOPO la chiusura
    #: della posizione.
    #:
    #: Serve a una domanda diversa dall'esito. «Stop il giorno 3, target il
    #: giorno 12» rende -1R ed e' giusto — la posizione era chiusa — ma dice
    #: anche che quello stop era troppo stretto e il trade aveva ragione. Quel
    #: fatto non e' ricavabile ne' dall'esito ne' da MAE/MFE, che si fermano
    #: alla risoluzione perche' misurano il TRADE e non la TARATURA.
    #:
    #: Da queste tre date l'ordine si deduce, «entrambe toccate» si deduce, e
    #: l'esito resta quello che era.
    data_stop: str | None
    data_tp1: str | None
    data_tp2: str | None


def corri_la_gara(
    piano: PianoDiTrade, barre: Sequence[Barra], orizzonte: int,
) -> EsitoGara | None:
    """L'esito del piano sulle barre SUCCESSIVE all'ingresso, o None.

    None quando non c'e' ancora un esito: nessuna barra, oppure niente e'
    stato toccato e l'orizzonte non e' ancora trascorso.

    ⚠️ Quel None e' importante quanto gli esiti. Etichettare un trade ancora
    aperto come «scaduto» vorrebbe dire scrivere un numero che il tempo puo'
    ancora smentire — lo stesso difetto che stiamo chiudendo, con il segno
    invertito.
    """
    if piano.r <= 0 or not barre or not piano.targets:
        return None

    lungo = piano.side == "long"
    tp1 = piano.targets[0].price
    tp2 = piano.targets[1].price if len(piano.targets) > 1 else None
    rr1 = piano.targets[0].rr

    # Oltre l'orizzonte non si guarda: un tocco alla trentesima seduta di un
    # detector etichettato a ventuno appartiene a un'altra domanda.
    finestra = list(barre[:orizzonte])

    peggio = migliore = piano.entry
    tp2_visto = False
    data_stop = data_tp1 = data_tp2 = None
    risolta: tuple[str, str, int] | None = None

    for i, b in enumerate(finestra, 1):
        if lungo:
            colpo_stop = b.basso <= piano.stop
            colpo_tp1 = b.alto >= tp1
            colpo_tp2 = tp2 is not None and b.alto >= tp2
        else:
            colpo_stop = b.alto >= piano.stop
            colpo_tp1 = b.basso <= tp1
            colpo_tp2 = tp2 is not None and b.basso <= tp2

        # Il censimento delle gambe continua per TUTTA la finestra: e' la
        # diagnosi, e vale anche dopo che la posizione si e' chiusa.
        if colpo_stop and data_stop is None:
            data_stop = b.data
        if colpo_tp1 and data_tp1 is None:
            data_tp1 = b.data
        if colpo_tp2 and data_tp2 is None:
            data_tp2 = b.data

        if risolta is not None:
            continue

        # ⚠️ Da qui in giu' solo finche' la posizione e' APERTA. L'escursione
        # oltre la chiusura non appartiene al trade: un crollo il giorno dopo
        # un target colpito non e' una perdita di nessuno.
        if lungo:
            peggio = min(peggio, b.basso)
            migliore = max(migliore, b.alto)
        else:
            peggio = max(peggio, b.alto)
            migliore = min(migliore, b.basso)
        if colpo_tp2 and not colpo_stop:
            tp2_visto = True

        if colpo_stop or colpo_tp1:
            # ⚠️ Stop e target nella STESSA barra: il dato giornaliero non dice
            # quale sia venuto prima. Si assegna lo stop (pessimista) ma
            # l'esito resta una categoria a se', cosi' dopo si puo' misurare
            # quanto costa questa convenzione invece di darla per buona. Le
            # DATE intanto dicono la verita' disponibile: entrambe quel giorno.
            if colpo_stop and colpo_tp1:
                risolta = ("ambigua", b.data, i)
            elif colpo_stop:
                risolta = ("stop", b.data, i)
            else:
                risolta = ("tp1", b.data, i)
            if colpo_stop:
                tp2_visto = False

    date = (data_stop, data_tp1, data_tp2)
    if risolta is not None:
        esito, quando, quante = risolta
        r_mult = rr1 if esito == "tp1" else -1.0
        return _esito(esito, quando, quante, r_mult, piano, peggio, migliore,
                      tp2_visto, date)

    # Nessun tocco. Se l'orizzonte e' trascorso si valorizza alla chiusura;
    # altrimenti il trade e' ancora aperto e non si etichetta.
    if len(barre) < orizzonte:
        return None
    ultima = finestra[-1]
    segno = 1.0 if lungo else -1.0
    r_mult = (ultima.chiusura - piano.entry) * segno / piano.r
    return _esito("scaduto", ultima.data, len(finestra), r_mult, piano,
                  peggio, migliore, tp2_visto, date)


def _esito(
    esito: str, data: str, barre: int, r_mult: float, piano: PianoDiTrade,
    peggio: float, migliore: float, tp2: bool,
    date: tuple[str | None, str | None, str | None],
) -> EsitoGara:
    if piano.side == "long":
        mae = (piano.entry - peggio) / piano.r
        mfe = (migliore - piano.entry) / piano.r
    else:
        mae = (peggio - piano.entry) / piano.r
        mfe = (piano.entry - migliore) / piano.r
    # `peggio`/`migliore` partono dall'ingresso, quindi entrambe sono gia' >= 0:
    # un trade mai andato contro ha escursione avversa ZERO, che e' la lettura
    # giusta — «massima escursione avversa» col segno meno sarebbe una
    # contraddizione, e zero dice la cosa vera, cioe' che lo stop non e' mai
    # stato avvicinato.
    data_stop, data_tp1, data_tp2 = date
    return EsitoGara(esito=esito, data=data, barre=barre, r_multiplo=r_mult,
                     mae_r=mae, mfe_r=mfe, tp2_raggiunto=tp2,
                     data_stop=data_stop, data_tp1=data_tp1, data_tp2=data_tp2)


# ─── La maturazione ────────────────────────────────────────────────────────

#: Versione della regola con cui una riga e' stata etichettata. Senza, una
#: modifica al metodo mescolerebbe in silenzio le popolazioni di prima e di
#: dopo — la stessa ragione per cui esiste `OUTCOME_METHOD_VERSION`.
PLAN_METHOD_VERSION = "1"


def _barre_dopo(db: Session, stock_id: int, dal: date) -> list[Barra]:
    """Le barre STRETTAMENTE successive a `dal`, in ordine.

    ⚠️ Strettamente: la barra dello scatto porta massimo e minimo dell'INTERA
    giornata, inclusa la parte precedente all'alert. Contarla attribuirebbe al
    piano un movimento avvenuto prima che l'alert esistesse — un target
    «colpito» da un massimo del mattino su un alert scattato nel pomeriggio —
    e lo farebbe in modo sistematico e invisibile.
    """
    righe = db.execute(
        select(OhlcvDaily.date, OhlcvDaily.high, OhlcvDaily.low, OhlcvDaily.close)
        .where(OhlcvDaily.stock_id == stock_id, OhlcvDaily.date > dal)
        .order_by(OhlcvDaily.date)
    ).all()
    return [Barra(str(d)[:10], float(hi), float(lo), float(cl))
            for d, hi, lo, cl in righe]


#: I detector il cui livello di invalidazione si RICOSTRUISCE in modo esatto
#: da un fatto delle barre, per gli alert storici che non ce l'hanno:
#:
#:   gap_and_go          la chiusura della barra precedente al gap
#:   le tre divergenze   l'estremo della barra del segnale, che e' l'ultimo
#:                       pivot per costruzione — l'evento porta
#:                       `date == pivot_dates[-1]` (verificato in events.py)
#:
#: ⚠️ `adx_confirmation` e `squeeze_expansion` sono ESCLUSI, e l'esclusione e'
#: la parte importante. Il primo vorrebbe ricalcolare un livello Donchian con
#: un parametro che potrebbe essere cambiato, il secondo una finestra di
#: compressione. Il risultato sarebbe indistinguibile da un livello misurato, e
#: questo repo ha gia' pagato quella lezione su SOXS: un fattore dedotto e
#: applicato all'indietro «sembra perfettamente sano ed e' silenziosamente
#: sbagliato».
RICOSTRUIBILI: frozenset[str] = frozenset({
    "gap_and_go", "rsi_divergence", "macd_divergence", "hidden_divergence",
})


def _invalidazione_ricostruita(
    db: Session, *, stock_id: int, detector: str, signal_date: date, tone: str,
) -> dict | None:
    """Il livello che quell'alert AVREBBE avuto, letto dalle barre.

    None quando il detector non e' fra i ricostruibili o la barra non c'e'.
    """
    if detector not in RICOSTRUIBILI:
        return None
    if detector == "gap_and_go":
        chiusura = db.execute(
            select(OhlcvDaily.close)
            .where(OhlcvDaily.stock_id == stock_id, OhlcvDaily.date < signal_date)
            .order_by(OhlcvDaily.date.desc()).limit(1)
        ).scalar()
        if chiusura is None:
            return None
        return {"level": float(chiusura),
                "reason": "gap colmato: ritorno alla chiusura precedente"}
    estremi = db.execute(
        select(OhlcvDaily.low, OhlcvDaily.high)
        .where(OhlcvDaily.stock_id == stock_id, OhlcvDaily.date == signal_date)
    ).first()
    if estremi is None:
        return None
    minimo, massimo = float(estremi[0]), float(estremi[1])
    if tone == "bull":
        return {"level": minimo,
                "reason": "prezzo sotto il minimo su cui poggia la divergenza"}
    return {"level": massimo,
            "reason": "prezzo sopra il massimo su cui poggia la divergenza"}


def mature_plan_outcomes(
    db: Session, *, commit: bool = True, ricostruisci: bool = False,
) -> int:
    """Scrive una riga di `plan_outcomes` per ogni alert il cui piano si e'
    risolto e che non ne ha ancora una. Rende il numero di righe scritte.

    Idempotente: gli alert che hanno gia' un esito non vengono riesaminati, e
    l'unicita' e' comunque imposta dal database.
    """
    from app.services.signal_drift_service import _horizon_days

    candidati = db.execute(
        select(Alert)
        .where(~exists().where(PlanOutcome.alert_id == Alert.id))
        .order_by(Alert.id)
    ).scalars().all()

    scritte = 0
    barre_per_titolo: dict[int, list[Barra]] = {}
    for a in candidati:
        # ⚠️ Un guasto per riga non deve costare la passata: e' la stessa
        # forma per cui `ohlcv_service` cattura per titolo dentro il ciclo,
        # cosi' un ticker morto non ferma gli altri.
        try:
            snap = json.loads(a.snapshot) if a.snapshot else {}
        except (ValueError, TypeError):
            continue
        if not isinstance(snap, dict):
            continue

        fonte = FONTE_EMESSO
        piano = costruisci_piano(snap, float(a.trigger_price), a.signal_name)
        if piano is None and ricostruisci and a.signal_date is not None:
            # ⚠️ Solo per gli alert che un livello non ce l'hanno: uno EMESSO
            # non viene mai scavalcato, altrimenti `source` smetterebbe di
            # dire la verita' proprio sulle righe di cui ci si fida di piu'.
            livello = _invalidazione_ricostruita(
                db, stock_id=a.stock_id, detector=a.signal_name or "",
                signal_date=a.signal_date, tone=snap.get("tone") or "")
            if livello is not None:
                piano = costruisci_piano({**snap, "invalidation": livello},
                                         float(a.trigger_price), a.signal_name)
                fonte = FONTE_RICOSTRUITO
        if piano is None:
            continue   # nessun livello strutturale: niente piano, niente gara

        scatto = a.triggered_at.date()
        if a.stock_id not in barre_per_titolo:
            barre_per_titolo[a.stock_id] = _barre_dopo(db, a.stock_id, scatto)
        barre = [b for b in barre_per_titolo[a.stock_id] if b.data > str(scatto)[:10]]

        orizzonte = _horizon_days(a.signal_name or "")
        esito = corri_la_gara(piano, barre, orizzonte)
        if esito is None:
            continue   # ancora aperto, o senza barre

        db.add(PlanOutcome(
            alert_id=a.id, stock_id=a.stock_id, detector=a.signal_name or "",
            signal_date=a.signal_date or scatto, tone=snap.get("tone") or "",
            horizon_days=orizzonte,
            entry_date=scatto, entry=piano.entry, stop=piano.stop,
            tp1=piano.targets[0].price,
            tp2=piano.targets[1].price if len(piano.targets) > 1 else None,
            r=piano.r,
            esito=esito.esito, resolved_date=date.fromisoformat(esito.data),
            bars_to_outcome=esito.barre, r_multiple=esito.r_multiplo,
            mae_r=esito.mae_r, mfe_r=esito.mfe_r,
            tp2_reached=esito.tp2_raggiunto,
            stop_hit_date=_giorno(esito.data_stop),
            tp1_hit_date=_giorno(esito.data_tp1),
            tp2_hit_date=_giorno(esito.data_tp2),
            source=fonte, method_version=PLAN_METHOD_VERSION,
            matured_at=datetime.now(UTC),
        ))
        scritte += 1

    if scritte:
        db.flush()
        if commit:
            db.commit()
    return scritte


def _giorno(iso: str | None) -> date | None:
    return date.fromisoformat(iso) if iso else None
