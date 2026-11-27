"""Rendimenti per periodo, volatilita' e distanza dai massimi (FA-184).

Proprietario unico di queste misure per la pagina Mercati (panoramica e
statistiche di un simbolo) e per lo Studio: due viste dello stesso numero
devono dare lo stesso numero.

Tutto su chiusure GIORNALIERE, ordinate per data. Un periodo che la storia non
copre rende None, mai zero: «sconosciuto» non e' «fermo».
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date, timedelta

#: I periodi, in giorni di calendario all'indietro dalla data dell'ultima
#: chiusura. YTD a parte: dall'ultima chiusura dell'anno precedente.
PERIODI: dict[str, int] = {"1s": 7, "1m": 30, "3m": 91, "6m": 182, "1a": 365, "3a": 365 * 3, "5a": 365 * 5}
#: I periodi pluriennali si dicono anche annualizzati.
ANNUALIZZATI = {"3a": 3, "5a": 5}


def _ultima_chiusura_entro(date_: Sequence[date], chiusure: Sequence[float], limite: date) -> float | None:
    """L'ultima chiusura con data <= limite (ricerca binaria)."""
    lo, hi = 0, len(date_)
    while lo < hi:
        m = (lo + hi) // 2
        if date_[m] <= limite:
            lo = m + 1
        else:
            hi = m
    i = lo - 1
    if i < 0:
        return None
    c = chiusure[i]
    return c if c > 0 else None


def rendimenti_per_periodo(date_: Sequence[date], chiusure: Sequence[float]) -> dict[str, float | None]:
    """{"1s","1m","3m","6m","ytd","1a","3a","5a","3a_ann","5a_ann"} come
    frazioni (0,05 = +5%). Il punto di partenza e' l'ultima chiusura ALLA data
    d'inizio del periodo: per un periodo che comincia di sabato, quella del
    venerdi'. None se la storia non arriva fin li'."""
    out: dict[str, float | None] = {k: None for k in [*PERIODI, "ytd", *(f"{k}_ann" for k in ANNUALIZZATI)]}
    if not date_ or chiusure[-1] <= 0:
        return out
    ultimo, oggi = chiusure[-1], date_[-1]
    for k, giorni in PERIODI.items():
        inizio = oggi - timedelta(days=giorni)
        if date_[0] > inizio:
            continue  # la storia comincia dopo l'inizio del periodo
        base = _ultima_chiusura_entro(date_, chiusure, inizio)
        if base:
            out[k] = ultimo / base - 1.0
    fine_anno_prec = date(oggi.year - 1, 12, 31)
    if date_[0] <= fine_anno_prec:
        base = _ultima_chiusura_entro(date_, chiusure, fine_anno_prec)
        if base:
            out["ytd"] = ultimo / base - 1.0
    for k, anni in ANNUALIZZATI.items():
        r = out[k]
        if r is not None and r > -1:
            out[f"{k}_ann"] = (1.0 + r) ** (1.0 / anni) - 1.0
    return out


def volatilita_annua(chiusure: Sequence[float], sedute: int, giorni_anno: int = 252) -> float | None:
    """Deviazione standard campionaria dei rendimenti logaritmici delle
    ultime `sedute`, annualizzata con `sqrt(giorni_anno)`. Le cripto scambiano
    tutti i giorni e usano 365: il chiamante lo sceglie e lo dichiara."""
    if len(chiusure) < sedute + 1 or sedute < 2:
        return None
    coda = chiusure[-(sedute + 1):]
    r = [math.log(b / a) for a, b in zip(coda, coda[1:], strict=False) if a > 0 and b > 0]
    if len(r) < 2:
        return None
    m = sum(r) / len(r)
    var = sum((x - m) ** 2 for x in r) / (len(r) - 1)
    return math.sqrt(var) * math.sqrt(giorni_anno)


def distanza_dal_massimo(
    date_: Sequence[date], chiusure: Sequence[float], sedute: int | None = None,
) -> dict | None:
    """Il massimo di chiusura nelle ultime `sedute` (None = tutta la storia),
    la sua data e quanto l'ultima chiusura ne dista (<= 0)."""
    if not chiusure:
        return None
    da = 0 if sedute is None else max(0, len(chiusure) - sedute)
    i = max(range(da, len(chiusure)), key=lambda k: chiusure[k])
    massimo = chiusure[i]
    if massimo <= 0:
        return None
    return {"valore": massimo, "data": date_[i].isoformat(),
            "distanza": chiusure[-1] / massimo - 1.0, "sedute_da": len(chiusure) - 1 - i}


def distanza_dal_minimo(
    date_: Sequence[date], chiusure: Sequence[float], sedute: int | None = None,
) -> dict | None:
    """Il gemello di `distanza_dal_massimo`: distanza >= 0 dal minimo."""
    if not chiusure:
        return None
    da = 0 if sedute is None else max(0, len(chiusure) - sedute)
    i = min(range(da, len(chiusure)), key=lambda k: chiusure[k])
    minimo = chiusure[i]
    if minimo <= 0:
        return None
    return {"valore": minimo, "data": date_[i].isoformat(),
            "distanza": chiusure[-1] / minimo - 1.0, "sedute_da": len(chiusure) - 1 - i}


def ema_ultima(chiusure: Sequence[float], periodo: int) -> float | None:
    """L'ultimo valore della EMA, da `app.indicators.ema` (proprietario unico
    della definizione). None sotto `periodo` chiusure: una EMA200 su 50 barre
    non e' una EMA200."""
    if len(chiusure) < periodo:
        return None
    import pandas as pd  # noqa: PLC0415

    from app.indicators.ema import ema  # noqa: PLC0415

    return float(ema(pd.Series(list(chiusure), dtype=float), periodo).iloc[-1])
