"""L'andamento di un settore: rendimenti, ampiezza, chi traina (2026-10-11).

La pagina di dettaglio di un settore mostrava fondamentali e punteggi, ma
nemmeno un numero su come il settore si e' MOSSO. Qui si calcola dalle barre
giornaliere che l'app ha gia':

- un indice del settore a PESI UGUALI: ogni giorno la media dei rendimenti dei
  titoli che hanno scambiato, concatenata. Non e' l'indice ufficiale (pesato
  per capitalizzazione) e la pagina lo dice; accanto c'e' l'ETF settoriale
  quando il catalogo lo ha, che e' la versione pesata;
- i rendimenti su sei finestre per settore, ETF e S&P 500 (SPY);
- l'ampiezza: quanti titoli stanno sopra la media a 50 e a 200 sedute, quanti
  vicino ai massimi o ai minimi dell'anno, quanti hanno chiuso in rialzo;
- i rendimenti di ogni titolo, per vedere chi traina e chi frena.

⚠️ Tre scelte che reggono i numeri:

- **Le finestre sono di CALENDARIO, non di barre.** Nel settore convivono
  borse con festivita' diverse: venti barre di Hong Kong non sono venti barre
  di New York. «Un mese» e' l'ultima chiusura a un mese di calendario fa.
- **Un giorno conta solo se scambia almeno meta' del settore.** Il 7 settembre
  2026 (festa del lavoro USA) scambiavano 11 titoli tecnologici su 131, e il
  16 i 7 asiatici gia' aggiornati prima dell'apertura americana: presi per
  giorni pieni spostavano la media e fissavano l'«oggi» del settore su una
  mezza giornata. Gli altri titoli si confrontano fra un giorno valido e il
  successivo, quindi il loro movimento non si perde.
- **Un rendimento giornaliero oltre il 45% in valore assoluto si scarta.** E'
  quasi sempre uno split non assorbito (un 2:1 vale −50%, e
  `find_basis_breaks` non vede i 2:1 per scelta): dentro una media a pesi
  uguali un solo artefatto sposterebbe l'intero settore. Un vero −45% in una
  seduta esiste, ed e' il costo dichiarato.
- **Le medie mobili sono EMA 50/200**, le stesse di tutto il resto dell'app
  (`indicators.periods`), e la 200 si conta solo con 200 barre di storia, come
  `has_full_data` per l'ampiezza della home.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.indicators.ema import ema
from app.indicators.periods import FIXED_EMA_MID, FIXED_EMA_SLOW
from app.models import OhlcvDaily, Stock

#: Oltre questo rendimento giornaliero (in valore assoluto) la barra e' un
#: artefatto, non un movimento: vedi il docstring.
MAX_RENDIMENTO_GIORNALIERO = 0.45
#: Quanta storia si legge: un anno di grafico piu' il riscaldamento dell'EMA200.
GIORNI_STORIA = 640
#: Vicino al massimo o al minimo dell'anno: entro il 5%.
VICINO_ESTREMO = 0.05
#: Sotto questo numero di titoli che scambiano, un giorno non fa media.
MIN_TITOLI_GIORNO = 3
#: Un giorno fa media solo se scambia almeno questa quota del numero tipico.
QUOTA_GIORNO_PIENO = 0.5
#: Quante sedute si porta avanti l'ultima chiusura di un titolo fermo.
RIPORTO_MAX = 7

FINESTRE: tuple[tuple[str, int | None], ...] = (
    ("1s", 7), ("1m", 30), ("3m", 91), ("6m", 182), ("ytd", None), ("1a", 365),
)

_CACHE: dict[tuple, tuple[float, object]] = {}
_TTL = 30 * 60.0


@dataclass
class Titolo:
    ticker: str
    ultimo: date
    r_1g: float | None
    r_1m: float | None
    r_3m: float | None
    r_ytd: float | None
    r_1a: float | None
    sopra_ema50: bool | None
    sopra_ema200: bool | None
    #: Distanza dal massimo a un anno, in % (0 = sul massimo, negativa sotto).
    dal_massimo: float | None
    #: Distanza dal minimo a un anno, in % (0 = sul minimo, positiva sopra).
    dal_minimo: float | None = None


@dataclass
class Andamento:
    #: Indice a pesi uguali, base 100 un anno fa: [(data, valore)].
    indice: list[tuple[date, float]]
    #: Gli stessi giorni per i confronti, base 100 sulla stessa data.
    spy: list[tuple[date, float]] = field(default_factory=list)
    etf: list[tuple[date, float]] = field(default_factory=list)
    etf_ticker: str | None = None
    rendimenti: dict[str, float | None] = field(default_factory=dict)
    rendimenti_spy: dict[str, float | None] = field(default_factory=dict)
    rendimenti_etf: dict[str, float | None] = field(default_factory=dict)
    #: Ampiezza: conteggi e il denominatore di ciascuno.
    sopra_ema50: tuple[int, int] = (0, 0)
    sopra_ema200: tuple[int, int] = (0, 0)
    vicino_massimi: tuple[int, int] = (0, 0)
    vicino_minimi: tuple[int, int] = (0, 0)
    in_rialzo: tuple[int, int] = (0, 0)
    titoli: list[Titolo] = field(default_factory=list)


def _chiusure(db: Session, stock_ids: list[int], dal: date) -> pd.DataFrame:
    """Le chiusure per data x titolo. Una colonna per stock_id."""
    if not stock_ids:
        return pd.DataFrame()
    righe = db.execute(
        select(OhlcvDaily.stock_id, OhlcvDaily.date, OhlcvDaily.close)
        .where(OhlcvDaily.stock_id.in_(stock_ids), OhlcvDaily.date >= dal)
    ).all()
    if not righe:
        return pd.DataFrame()
    df = pd.DataFrame(righe, columns=["sid", "data", "close"])
    df["close"] = df["close"].astype(float)
    df = df[df["close"] > 0]
    return df.pivot_table(index="data", columns="sid", values="close", aggfunc="last").sort_index()


def giorni_pieni(px: pd.DataFrame) -> list[date]:
    """I giorni in cui scambia almeno meta' del settore (vedi il docstring)."""
    n = px.notna().sum(axis=1)
    if n.empty:
        return []
    soglia = max(MIN_TITOLI_GIORNO, QUOTA_GIORNO_PIENO * float(n.median()))
    return list(n.index[n >= soglia])


def _rendimenti_puliti(serie: pd.Series) -> pd.Series:
    r = serie.dropna().pct_change()
    return r.where(r.abs() <= MAX_RENDIMENTO_GIORNALIERO)


def _valore_a(indice: pd.Series, giorno: date) -> float | None:
    """L'ultimo valore della serie a `giorno` o prima."""
    prima = indice.loc[:giorno]
    return float(prima.iloc[-1]) if len(prima) else None


def _rendimento(indice: pd.Series, finestra: int | None) -> float | None:
    """Il rendimento in % sull'ultima finestra di calendario (None = da inizio anno)."""
    s = indice.dropna()
    if len(s) < 2:
        return None
    fine = s.index[-1]
    inizio = date(fine.year - 1, 12, 31) if finestra is None else fine - timedelta(days=finestra)
    if s.index[0] > inizio:
        return None
    base = _valore_a(s, inizio)
    if not base:
        return None
    return (float(s.iloc[-1]) / base - 1.0) * 100.0


def _indice_da_rendimenti(r: pd.Series) -> pd.Series:
    return (1.0 + r.fillna(0.0)).cumprod()


def _base_100(s: pd.Series, dal: date) -> list[tuple[date, float]]:
    s = s.dropna()
    s = s.loc[dal:]
    if s.empty or not s.iloc[0]:
        return []
    return [(d, round(float(v) / float(s.iloc[0]) * 100.0, 3)) for d, v in s.items()]


def _titolo(ticker: str, chiusure: pd.Series) -> Titolo | None:
    s = chiusure.dropna()
    if s.empty:
        return None
    r = _rendimenti_puliti(s)
    indice = _indice_da_rendimenti(r)
    ultimo = s.index[-1]
    anno = s.loc[ultimo - timedelta(days=365):]
    massimo = float(anno.max()) if len(anno) else None
    minimo = float(anno.min()) if len(anno) else None
    e50 = float(ema(s, FIXED_EMA_MID).iloc[-1]) if len(s) >= FIXED_EMA_MID else None
    e200 = float(ema(s, FIXED_EMA_SLOW).iloc[-1]) if len(s) >= FIXED_EMA_SLOW else None
    ultima = float(s.iloc[-1])
    r1g = r.iloc[-1] if len(r) else None
    return Titolo(
        ticker=ticker,
        ultimo=ultimo,
        r_1g=None if r1g is None or pd.isna(r1g) else float(r1g) * 100.0,
        r_1m=_rendimento(indice, 30),
        r_3m=_rendimento(indice, 91),
        r_ytd=_rendimento(indice, None),
        r_1a=_rendimento(indice, 365),
        sopra_ema50=None if e50 is None else ultima > e50,
        sopra_ema200=None if e200 is None else ultima > e200,
        dal_massimo=None if not massimo else (ultima / massimo - 1.0) * 100.0,
        dal_minimo=None if not minimo else (ultima / minimo - 1.0) * 100.0,
    )


def calcola(
    db: Session,
    titoli: dict[int, str],
    *,
    etf_ticker: str | None = None,
    oggi: date | None = None,
) -> Andamento:
    """L'andamento dei `titoli` (stock_id -> ticker) di un settore."""
    oggi = oggi or date.today()
    dal = oggi - timedelta(days=GIORNI_STORIA)
    riferimenti = {"SPY"} | ({etf_ticker} if etf_ticker else set())
    rif = dict(db.execute(select(Stock.ticker, Stock.id).where(Stock.ticker.in_(riferimenti))).all())
    ids = list(titoli) + [i for i in rif.values() if i not in titoli]
    px = _chiusure(db, ids, dal)
    if px.empty:
        return Andamento(indice=[])

    colonne = [sid for sid in titoli if sid in px.columns]
    if not colonne:
        return Andamento(indice=[])
    giorni = giorni_pieni(px[colonne])
    if len(giorni) < 2:
        return Andamento(indice=[])
    chiusure = px[colonne].ffill(limit=RIPORTO_MAX).loc[giorni]
    rendimenti = pd.DataFrame({sid: _rendimenti_puliti(chiusure[sid]) for sid in colonne}, index=chiusure.index)
    media = rendimenti.mean(axis=1, skipna=True)
    indice = _indice_da_rendimenti(media)
    inizio_grafico = giorni[-1] - timedelta(days=365)

    out = Andamento(indice=_base_100(indice, inizio_grafico))
    out.rendimenti = {k: _rendimento(indice, g) for k, g in FINESTRE}

    def confronto(ticker: str) -> tuple[list[tuple[date, float]], dict[str, float | None]]:
        sid = rif.get(ticker)
        if sid is None or sid not in px.columns:
            return [], {}
        idx = _indice_da_rendimenti(_rendimenti_puliti(px[sid])).loc[: giorni[-1]]
        return _base_100(idx, inizio_grafico), {k: _rendimento(idx, g) for k, g in FINESTRE}

    out.spy, out.rendimenti_spy = confronto("SPY")
    if etf_ticker and etf_ticker in rif:
        out.etf, out.rendimenti_etf = confronto(etf_ticker)
        out.etf_ticker = etf_ticker if out.etf else None

    for sid in colonne:
        t = _titolo(titoli[sid], px[sid])
        if t is not None:
            out.titoli.append(t)

    def quota(cond) -> tuple[int, int]:
        valori = [cond(t) for t in out.titoli]
        noti = [v for v in valori if v is not None]
        return sum(1 for v in noti if v), len(noti)

    out.sopra_ema50 = quota(lambda t: t.sopra_ema50)
    out.sopra_ema200 = quota(lambda t: t.sopra_ema200)
    out.vicino_massimi = quota(lambda t: None if t.dal_massimo is None else t.dal_massimo >= -VICINO_ESTREMO * 100)
    out.vicino_minimi = quota(lambda t: None if t.dal_minimo is None else t.dal_minimo <= VICINO_ESTREMO * 100)
    out.in_rialzo = quota(lambda t: None if t.r_1g is None else t.r_1g > 0)
    return out


def calcola_in_cache(db: Session, settore: str, titoli: dict[int, str], *, etf_ticker: str | None) -> Andamento:
    """`calcola` con mezz'ora di cache: le barre cambiano una volta al giorno."""
    chiave = (settore, etf_ticker, tuple(sorted(titoli)))
    trovato = _CACHE.get(chiave)
    if trovato and time.time() - trovato[0] < _TTL:
        return trovato[1]  # type: ignore[return-value]
    risultato = calcola(db, titoli, etf_ticker=etf_ticker)
    _CACHE[chiave] = (time.time(), risultato)
    return risultato
