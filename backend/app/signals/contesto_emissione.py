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
"""
from __future__ import annotations

import math

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
VERSIONE = "1"

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


def _num(x: float) -> float | None:
    """Un float finito arrotondato a 6 cifre significative, o None."""
    if x is None:
        return None
    x = float(x)
    if not math.isfinite(x):
        return None
    return float(f"{x:.6g}")


def contesto(ohlcv: pd.DataFrame) -> dict:
    """Le variabili del titolo all'ultima barra di `ohlcv`.

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

    pulito = {k: _num(x) for k, x in out.items()}
    return {"versione": VERSIONE, **{k: x for k, x in pulito.items() if x is not None}}
