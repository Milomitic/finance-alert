"""I numeri della pagina di dettaglio di un indicatore macro (2026-10-11).

Tutto si calcola dai dati che l'app ha gia': le osservazioni FRED, le date dei
rilasci passati, le barre giornaliere dello SPY. Nessuna fonte nuova.

⚠️ Due regole che reggono ogni numero di questa pagina:

- **L'unita' della variazione segue la serie.** Su un indice o un livello e' una
  variazione in %; su un tasso (`pct`, `yield`) e' una differenza in PUNTI: un
  tasso che passa da 3,75 a 4,00 non e' salito del 6,7%, e' salito di 0,25 pp.
- **Ogni statistica porta il suo campione.** Sedici rilasci e quaranta mesi sono
  pochi: la pagina li mostra, e una correlazione e' una coincidenza misurata,
  non una causa.
"""
from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OhlcvDaily, Stock
from app.models.macro import MacroObservation, MacroReleaseDate, MacroSeries

UNITA_TASSO = ("pct", "yield")
#: Sotto questi campioni una statistica non si calcola: la pagina dice perche'.
MIN_VARIAZIONI = 12
MIN_RILASCI = 6
MIN_MESI_CORRELAZIONE = 18


@dataclass
class Variazione:
    data: date
    valore: float
    #: Sul periodo prima: % su un indice/livello, punti su un tasso.
    sul_periodo: float | None
    #: Sull'anno prima, nella stessa unita'.
    sull_anno: float | None


@dataclass
class Reazione:
    n: int
    #: Movimento assoluto medio dello SPY nei giorni di rilascio e negli altri, in %.
    medio_rilascio: float
    medio_altri: float
    #: Gli ultimi rilasci: (data, rendimento dello SPY quel giorno in %).
    ultimi: list[tuple[date, float]] = field(default_factory=list)


@dataclass
class Correlazione:
    n: int
    r: float
    dal: date
    al: date


@dataclass
class Analisi:
    unita_variazione: str  # "%" | "pp"
    variazioni: list[Variazione]
    ultima: float | None = None
    media: float | None = None
    dev_std: float | None = None
    zscore: float | None = None
    #: Quota delle variazioni storiche PIU' BASSE dell'ultima, 0-100.
    percentile: float | None = None
    annualizzata_3m: float | None = None
    #: Quanti periodi di fila nello stesso verso, col segno (+3 = tre rialzi).
    serie: int = 0
    massimo: tuple[date, float] | None = None
    minimo: tuple[date, float] | None = None
    reazione: Reazione | None = None
    correlazione: Correlazione | None = None


def _variazione(nuovo: float, vecchio: float | None, tasso: bool) -> float | None:
    if vecchio is None:
        return None
    if tasso:
        return nuovo - vecchio
    if vecchio == 0:
        return None
    return (nuovo / vecchio - 1.0) * 100.0


def _mensile(date_: list[date]) -> bool:
    coda = date_[-13:]
    salti = sorted((b - a).days for a, b in zip(coda, coda[1:], strict=False) if b > a)
    return bool(salti) and 27 <= salti[len(salti) // 2] <= 32


def variazioni(osservazioni: list[tuple[date, float]], tasso: bool) -> list[Variazione]:
    """Ogni osservazione con la variazione sul periodo prima e sull'anno prima.

    `osservazioni` in ordine di data. Per una serie giornaliera di tassi che
    cambia solo agli annunci (DFEDTARU) il «periodo prima» e' il valore
    precedente DIVERSO: trenta righe di «3,75%» non sono trenta variazioni.
    L'anno prima e' l'ultimo valore noto a un anno di distanza, cosi' vale per
    qualunque cadenza.
    """
    date_ = [d for d, _ in osservazioni]
    valori = [v for _, v in osservazioni]
    out: list[Variazione] = []
    precedente: float | None = None
    for d, v in osservazioni:
        if out and precedente is not None and v == precedente and tasso:
            continue
        i = bisect_right(date_, d - timedelta(days=365)) - 1
        un_anno_fa = valori[i] if i >= 0 else None
        out.append(Variazione(d, v, _variazione(v, precedente, tasso), _variazione(v, un_anno_fa, tasso)))
        precedente = v
    return out


def _statistiche(a: Analisi, osservazioni: list[tuple[date, float]], tasso: bool) -> None:
    storiche = [x.sul_periodo for x in a.variazioni if x.sul_periodo is not None]
    if not storiche:
        return
    a.ultima = storiche[-1]
    if len(storiche) >= MIN_VARIAZIONI:
        media = sum(storiche) / len(storiche)
        dev = math.sqrt(sum((x - media) ** 2 for x in storiche) / (len(storiche) - 1))
        a.media, a.dev_std = media, dev
        a.zscore = (a.ultima - media) / dev if dev > 0 else None
        a.percentile = 100.0 * sum(1 for x in storiche[:-1] if x < a.ultima) / (len(storiche) - 1)
    segno = (a.ultima > 0) - (a.ultima < 0)
    if segno:
        for x in reversed(storiche):
            if (x > 0) - (x < 0) != segno:
                break
            a.serie += segno
    valori = [v for _, v in osservazioni]
    if valori:
        i_max = max(range(len(valori)), key=valori.__getitem__)
        i_min = min(range(len(valori)), key=valori.__getitem__)
        a.massimo = (osservazioni[i_max][0], valori[i_max])
        a.minimo = (osservazioni[i_min][0], valori[i_min])
    # Il ritmo degli ultimi tre mesi riportato a un anno: dice se la tendenza
    # recente e' piu' forte o piu' debole di quella annua.
    if not tasso and _mensile([d for d, _ in osservazioni]) and len(valori) >= 4 and valori[-4] > 0:
        a.annualizzata_3m = ((valori[-1] / valori[-4]) ** 4 - 1.0) * 100.0


def _chiusure_spy(db: Session, dal: date) -> list[tuple[date, float]]:
    spy = db.execute(select(Stock.id).where(Stock.ticker == "SPY").limit(1)).scalar()
    if spy is None:
        return []
    return [(d, float(c)) for d, c in db.execute(
        select(OhlcvDaily.date, OhlcvDaily.close)
        .where(OhlcvDaily.stock_id == spy, OhlcvDaily.date >= dal)
        .order_by(OhlcvDaily.date)
    ).all() if c]


def _reazione(db: Session, serie_id: int, oggi: date) -> Reazione | None:
    """Quanto si muove lo SPY nei giorni di rilascio, contro gli altri giorni.

    Si misura il movimento ASSOLUTO di chiusura su chiusura: un dato sopra o
    sotto le attese muove il mercato in versi opposti, e la media col segno si
    annullerebbe proprio dove il dato conta. Un rilascio in un giorno senza
    seduta non si conta."""
    rilasci = sorted({d for (d,) in db.execute(
        select(MacroReleaseDate.date).where(MacroReleaseDate.series_id == serie_id, MacroReleaseDate.date < oggi)
    ).all()})
    if len(rilasci) < MIN_RILASCI:
        return None
    chiusure = _chiusure_spy(db, rilasci[0] - timedelta(days=10))
    rendimenti = {chiusure[i][0]: (chiusure[i][1] / chiusure[i - 1][1] - 1.0) * 100.0 for i in range(1, len(chiusure))}
    giorni = [(d, rendimenti[d]) for d in rilasci if d in rendimenti]
    if len(giorni) < MIN_RILASCI:
        return None
    nei_rilasci = {d for d, _ in giorni}
    altri = [abs(r) for d, r in rendimenti.items() if d >= rilasci[0] and d not in nei_rilasci]
    if not altri:
        return None
    return Reazione(
        n=len(giorni),
        medio_rilascio=sum(abs(r) for _, r in giorni) / len(giorni),
        medio_altri=sum(altri) / len(altri),
        ultimi=giorni[-6:],
    )


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / (sx * sy)


def _correlazione(db: Session, a: Analisi, osservazioni: list[tuple[date, float]]) -> Correlazione | None:
    """La variazione del mese contro il rendimento dello SPY nello STESSO mese.

    Solo per le serie mensili, dove il mese e' un'unita' comune ai due. E'
    contemporanea, non predittiva: il dato di un mese esce il mese DOPO, quindi
    questa r dice se economia e borsa si sono mosse insieme, non se il dato
    anticipa la borsa."""
    if not _mensile([d for d, _ in osservazioni]):
        return None
    chiusure = _chiusure_spy(db, osservazioni[0][0] - timedelta(days=40))
    if not chiusure:
        return None
    fine_mese: dict[tuple[int, int], float] = {}
    for d, c in chiusure:
        fine_mese[(d.year, d.month)] = c  # l'ultima chiusura del mese vince
    xs, ys, giorni = [], [], []
    for v in a.variazioni:
        if v.sul_periodo is None:
            continue
        mese = (v.data.year, v.data.month)
        prima = (v.data.year - 1, 12) if v.data.month == 1 else (v.data.year, v.data.month - 1)
        if mese in fine_mese and prima in fine_mese:
            xs.append(v.sul_periodo)
            ys.append((fine_mese[mese] / fine_mese[prima] - 1.0) * 100.0)
            giorni.append(v.data)
    if len(xs) < MIN_MESI_CORRELAZIONE:
        return None
    r = _pearson(xs, ys)
    return None if r is None else Correlazione(n=len(xs), r=r, dal=giorni[0], al=giorni[-1])


def analisi(db: Session, serie: MacroSeries, *, oggi: date | None = None) -> Analisi:
    oggi = oggi or date.today()
    tasso = serie.unit in UNITA_TASSO
    osservazioni = [(d, float(v)) for d, v in db.execute(
        select(MacroObservation.date, MacroObservation.value)
        .where(MacroObservation.series_id == serie.id, MacroObservation.value.is_not(None))
        .order_by(MacroObservation.date)
    ).all()]
    a = Analisi(unita_variazione="pp" if tasso else "%", variazioni=variazioni(osservazioni, tasso))
    if not osservazioni:
        return a
    _statistiche(a, osservazioni, tasso)
    a.reazione = _reazione(db, serie.id, oggi)
    a.correlazione = _correlazione(db, a, osservazioni)
    return a
