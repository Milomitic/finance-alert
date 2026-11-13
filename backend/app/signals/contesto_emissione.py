"""Il contesto del titolo nel momento in cui un alert COMPARE.

Si fissa nello snapshot alla creazione (`first_contesto`) e non si tocca piu',
insieme a Forza e fattori (`first_strength`, `first_factors`).

⚠️ Perche' esiste. Lo snapshot di un alert si sostituisce a ogni revisione, e
l'80% degli alert ne ha almeno una: la Forza nel magazzino degli esiti
coincideva con quella dello snapshot ATTUALE nel 99,7% dei casi (misurato il
2026-09-23). Cioe' ogni variabile del magazzino era misurata DOPO l'ingresso,
spesso di settimane, e nessun modello — nemmeno la Forza stessa — si poteva
validare sugli esiti veri: e' informazione dal futuro rispetto al trade.

Le variabili sono quelle dello studio di taratura del 2026-09-23
(`backend/scripts/studio_taratura`), dove sono servite a misurare sia il
meta-modello sia la previsione di volatilita'. Tutte del SOLO titolo: quelle di
mercato (ampiezza, VIX, curva) sono una per data e si ricostruiscono dal
catalogo in qualunque momento, queste no — dipendono da barre che una
riparazione puo' riscrivere.

⚠️ La finestra e' parte della definizione. Lo scan passa le ultime 260 barre
(`scan_service._load_ohlcv`), e chi ricalcola all'indietro deve passare la
STESSA finestra. Per questo le distanze sono dalle medie SEMPLICI: una SMA200 e'
esatta su qualunque finestra di almeno 200 barre, una EMA200 su 260 barre
dipende da dove comincia la serie, e lo stesso numero ricalcolato sulla storia
intera sarebbe un altro.

Versione 2 (FA-150, 2026-11-14): quattro variabili che dipendono da fuori
dalla serie del titolo e che a posteriori NON si ricostruiscono fedelmente.

- `giorni_a_trimestrale`, `giorni_da_trimestrale`: giorni di calendario dalla
  barra alla prossima trimestrale e dall'ultima pubblicata, letti dalla cache
  dei fondamentali. Le date future si spostano e quelle vecchie escono dalla
  cache: e' il motivo per cui si fissano adesso.
- `beta_252`: contro il rendimento giornaliero MEDIANO del catalogo (solo
  societa'), sulle stesse barre della finestra. Non contro un indice: gli
  indici non stanno nel database, e il catalogo e' il mercato contro cui ogni
  esito di questo progetto e' gia' misurato.
- `rs_settore_63`: il rendimento a 63 sedute meno la mediana del suo settore
  nella stessa scansione. Il settore di un titolo puo' cambiare col catalogo.

Le variabili di ampiezza del mercato restano fuori, per la ragione scritta
sopra: sono una per data e si ricostruiscono dal catalogo.

Tutte e quattro mancano quando chi chiama non passa la loro fonte (la
rivalutazione manuale di un titolo, per esempio): chiave assente = non noto,
come per il resto.
"""
from __future__ import annotations

import math
from datetime import date, datetime

import numpy as np
import pandas as pd

from app.indicators.atr import atr as atr_serie
from app.indicators.periods import (
    FIXED_EMA_FAST,
    FIXED_EMA_MID,
    FIXED_EMA_SLOW,
    FIXED_RSI_PERIOD,
)
from app.indicators.rsi import rsi
from app.indicators.sma import sma

#: Cambia quando cambia una definizione qui sotto: un modello addestrato su una
#: versione non va nutrito con un'altra, e senza il numero le due popolazioni
#: sarebbero indistinguibili — la stessa ragione di `PLAN_METHOD_VERSION`.
VERSIONE = "2"

#: Le chiavi dello snapshot fissate alla prima emissione e conservate a ogni
#: revisione. Per chi le SCRIVE (lo scan) e per chi le riempie all'indietro:
#: un elenco copiato si dimentica della chiave successiva che si aggiunge —
#: la stessa ragione di `trade_plan.INGRESSI_CONGELATI`.
#:
#:   first_strength    la Forza di quel momento
#:   first_factors     i fattori del detector di quel momento
#:   first_contesto    le variabili del titolo qui sotto
#:   first_provenance  con quali regole e' stata prodotta quella prima analisi
#:   first_ombra       i punteggi dei modelli in prova silenziosa (`app.ml`),
#:                     presente solo se un modello esisteva a quell'emissione
VARIABILI_ALL_EMISSIONE: tuple[str, ...] = (
    "first_strength", "first_factors", "first_contesto", "first_provenance",
    "first_ombra",
)

_ANNO = 252

#: Sotto questo numero di rendimenti abbinati la beta non si dichiara.
_MIN_BETA = 120


def _giorno(x: object) -> date | None:
    # `datetime` (e il `Timestamp` di pandas) e' una sottoclasse di `date`.
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    try:
        return date.fromisoformat(str(x)[:10])
    except ValueError:
        return None


def beta(
    giorni: list[date | None], chiusure: np.ndarray, mercato: dict[date, float],
) -> float | None:
    """Beta dei rendimenti giornalieri del titolo su quelli del mercato, sulle
    ultime `_ANNO` coppie disponibili; None sotto `_MIN_BETA` coppie o con un
    mercato fermo."""
    xs: list[float] = []
    ys: list[float] = []
    for i in range(1, len(chiusure)):
        g = giorni[i]
        m = mercato.get(g) if g is not None else None
        if m is None or chiusure[i - 1] <= 0:
            continue
        xs.append(m)
        ys.append(chiusure[i] / chiusure[i - 1] - 1.0)
    xs, ys = xs[-_ANNO:], ys[-_ANNO:]
    if len(xs) < _MIN_BETA:
        return None
    x, y = np.asarray(xs), np.asarray(ys)
    var = float(np.var(x, ddof=1))
    if var <= 0:
        return None
    return float(np.cov(x, y, ddof=1)[0, 1] / var)


def _num(x: float) -> float | None:
    """Un float finito arrotondato a 6 cifre significative, o None."""
    if x is None:
        return None
    x = float(x)
    if not math.isfinite(x):
        return None
    return float(f"{x:.6g}")


def contesto(
    ohlcv: pd.DataFrame,
    *,
    rendimenti_mercato: dict[date, float] | None = None,
    rs63_settore: float | None = None,
    trimestrali: tuple[list[date], date | None] | None = None,
) -> dict:
    """Le variabili del titolo all'ultima barra di `ohlcv`.

    `rendimenti_mercato` ({giorno: rendimento mediano del catalogo}),
    `rs63_settore` (la mediana del rendimento a 63 sedute del settore) e
    `trimestrali` (date pubblicate, prossima) sono le fonti delle variabili
    della versione 2; senza, quelle chiavi mancano.

    Una chiave manca quando la storia non basta a calcolarla (un titolo con 100
    barre non ha un rendimento a un anno): una chiave assente dice «non noto»,
    uno zero direbbe un valore.
    """
    c = ohlcv["close"].astype(float).reset_index(drop=True)
    n = len(c)
    out: dict[str, float] = {}
    if n < 2:
        return {"versione": VERSIONE}
    h = ohlcv["high"].astype(float).reset_index(drop=True)
    lo = ohlcv["low"].astype(float).reset_index(drop=True)
    o = ohlcv["open"].astype(float).reset_index(drop=True)
    v = ohlcv["volume"].astype(float).reset_index(drop=True)
    ultimo = c.iloc[-1]

    for k in (1, 5, 21, 63, 126, _ANNO):
        if n > k and c.iloc[-1 - k] > 0:
            out[f"ret_{k}"] = ultimo / c.iloc[-1 - k] - 1

    a = atr_serie(ohlcv.reset_index(drop=True), 14)
    a_ult = a.iloc[-1]
    if a_ult == a_ult and a_ult > 0 and ultimo > 0:
        out["atr_pct"] = a_ult / ultimo
        for p in (FIXED_EMA_FAST, FIXED_EMA_MID, FIXED_EMA_SLOW):
            if n >= p:
                out[f"dist_sma{p}"] = (ultimo - sma(c, p).iloc[-1]) / a_ult
        pct = (a / c).iloc[-_ANNO:].dropna()
        if len(pct) >= 120:
            out["atr_rank"] = float((pct <= pct.iloc[-1]).mean())

    r = rsi(c, FIXED_RSI_PERIOD).iloc[-1]
    if r == r:
        out["rsi14"] = r
    if n >= _ANNO:
        out["dist_hi252"] = ultimo / h.iloc[-_ANNO:].max() - 1
        out["dist_lo252"] = ultimo / lo.iloc[-_ANNO:].min() - 1
    if n >= 21:
        media_vol = v.iloc[-21:-1].mean()
        if media_vol > 0:
            out["vol_ratio"] = v.iloc[-1] / media_vol
        out["vol20"] = c.pct_change().iloc[-20:].std()
        turnover = (c * v).iloc[-20:].mean()
        if turnover > 0:
            out["log_dollar_vol"] = math.log(turnover)
        mn, mx = c.iloc[-20:].min(), c.iloc[-20:].max()
        if mx > mn:
            out["range_pos20"] = (ultimo - mn) / (mx - mn)
    if c.iloc[-2] > 0:
        out["gap"] = o.iloc[-1] / c.iloc[-2] - 1

    giorni = [_giorno(g) for g in ohlcv["date"]] if "date" in ohlcv else []
    if rendimenti_mercato and giorni:
        b = beta(giorni, c.to_numpy(dtype=float), rendimenti_mercato)
        if b is not None:
            out["beta_252"] = b
    if rs63_settore is not None and "ret_63" in out:
        out["rs_settore_63"] = out["ret_63"] - rs63_settore
    ultimo_giorno = giorni[-1] if giorni else None
    if trimestrali is not None and ultimo_giorno is not None:
        passate, prossima = trimestrali
        if prossima is not None and prossima >= ultimo_giorno:
            out["giorni_a_trimestrale"] = (prossima - ultimo_giorno).days
        prima = [d for d in passate if d <= ultimo_giorno]
        if prima:
            out["giorni_da_trimestrale"] = (ultimo_giorno - max(prima)).days

    pulito = {k: _num(x) for k, x in out.items()}
    return {"versione": VERSIONE, **{k: x for k, x in pulito.items() if x is not None}}
